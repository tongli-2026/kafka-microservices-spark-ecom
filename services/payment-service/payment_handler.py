"""Serialize each order's payment and commit its result with an outbox row."""

import hashlib
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from events import PaymentFailedEvent, PaymentProcessedEvent
from models import PaymentOutboxEvent, PaymentResult
from payment_processor import PaymentProcessor
from repository import PaymentRepository
from shared.metrics import track_cache_hit, track_payment_status
from kafka_client import RetryableProcessingError


def _lock_order(db, order_id):
    """Lock an order before any external payment call, until transaction end.

    Hash collisions only serialize unrelated orders. SQLite unit tests use one
    worker; PostgreSQL integration tests exercise concurrent calls.
    """
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(order_id.encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _result_event(payment, result_record):
    if payment.status == "SUCCESS":
        return "payment.processed", PaymentProcessedEvent(
            event_id=result_record.event_id,
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            user_id=payment.user_id,
            amount=payment.amount,
            currency=payment.currency,
            method=payment.method,
            correlation_id=result_record.correlation_id,
        )
    if payment.status == "FAILED":
        return "payment.failed", PaymentFailedEvent(
            event_id=result_record.event_id,
            order_id=payment.order_id,
            user_id=payment.user_id,
            reason=payment.reason or "Payment failed",
            correlation_id=result_record.correlation_id,
        )
    raise ValueError(f"Unexpected payment status {payment.status}")


def handle_payment_event(event, session_factory, producer=None, process_payment=None):
    """Commit payment, stable result identity, and outgoing event together.

    The producer argument remains for callers on the previous interface;
    publication now belongs to PaymentOutboxPublisher.
    """
    process_payment = process_payment or PaymentProcessor.process_payment
    db = session_factory()
    try:
        _lock_order(db, event.order_id)
        repo = PaymentRepository(db)
        payment = repo.get_payment_by_order(event.order_id)
        if payment:
            if payment.user_id != event.user_id or payment.amount != event.total_amount:
                raise ValueError(f"Conflicting payment request for order {event.order_id}")
            track_cache_hit("idempotency", "payment-service", hit=True)
            result_record = db.get(PaymentResult, event.order_id)
            if result_record is None:
                # Legacy rows have no original result ID; inventing one could
                # restart an already completed Saga.
                db.commit()
                return
        else:
            track_cache_hit("idempotency", "payment-service", hit=False)
            try:
                success, reason = process_payment(event.total_amount)
            except Exception as error:
                raise RetryableProcessingError(
                    f"Payment processor did not return an outcome for {event.order_id}"
                ) from error
            payment = repo.create_payment(
                order_id=event.order_id, user_id=event.user_id,
                amount=event.total_amount, currency="USD", method="card",
                status="SUCCESS" if success else "FAILED",
                reason=None if success else reason,
            )
            result_record = PaymentResult(
                order_id=event.order_id, event_id=str(uuid4()),
                correlation_id=event.correlation_id,
            )
            db.add(result_record)
            track_payment_status("payment-service", "success" if success else "failed")

        if db.get(PaymentOutboxEvent, event.order_id) is None:
            topic, result_event = _result_event(payment, result_record)
            db.add(PaymentOutboxEvent(
                order_id=event.order_id, event_id=result_record.event_id,
                event_type=topic, event_data=result_event.model_dump_json(),
            ))
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise RetryableProcessingError("Payment database transaction failed") from error
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
