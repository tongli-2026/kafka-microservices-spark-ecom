"""Persist a payment before publishing its replayable result."""

from uuid import uuid4

from events import PaymentFailedEvent, PaymentProcessedEvent
from models import PaymentResult
from payment_processor import PaymentProcessor
from repository import PaymentRepository
from shared.metrics import track_cache_hit, track_kafka_message, track_payment_status


def handle_payment_event(event, session_factory, producer, process_payment=None):
    """A redelivered order republishes the recorded payment outcome."""
    process_payment = process_payment or PaymentProcessor.process_payment
    db = session_factory()
    try:
        repo = PaymentRepository(db)
        payment = repo.get_payment_by_order(event.order_id)
        if payment:
            if payment.user_id != event.user_id or payment.amount != event.total_amount:
                raise ValueError(f"Conflicting payment request for order {event.order_id}")
            track_cache_hit("idempotency", "payment-service", hit=True)
            result_record = db.get(PaymentResult, event.order_id)
            if result_record is None:
                # Pre-upgrade payment records did not preserve the original
                # result ID. Replaying them with a new ID could repeat a saga.
                db.commit()
                return
        else:
            track_cache_hit("idempotency", "payment-service", hit=False)
            success, reason = process_payment(event.total_amount)
            payment = repo.create_payment(
                order_id=event.order_id,
                user_id=event.user_id,
                amount=event.total_amount,
                currency="USD",
                method="card",
                status="SUCCESS" if success else "FAILED",
                reason=None if success else reason,
            )
            result_record = PaymentResult(
                order_id=event.order_id,
                event_id=str(uuid4()),
                correlation_id=event.correlation_id,
            )
            db.add(result_record)
            track_payment_status("payment-service", "success" if success else "failed")

        # Copy values before commit because SQLAlchemy expires mapped objects.
        result = {
            "payment_id": payment.payment_id,
            "order_id": payment.order_id,
            "user_id": payment.user_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "method": payment.method,
            "status": payment.status,
            "reason": payment.reason,
            "event_id": result_record.event_id,
            "correlation_id": result_record.correlation_id,
        }
        db.commit()

        # Stable across redelivery, including one after a publish/offset failure.
        if result["status"] == "SUCCESS":
            topic = "payment.processed"
            payment_event = PaymentProcessedEvent(
                event_id=result["event_id"],
                payment_id=result["payment_id"],
                order_id=result["order_id"],
                user_id=result["user_id"],
                amount=result["amount"],
                currency=result["currency"],
                method=result["method"],
                correlation_id=result["correlation_id"],
            )
        elif result["status"] == "FAILED":
            topic = "payment.failed"
            payment_event = PaymentFailedEvent(
                event_id=result["event_id"],
                order_id=result["order_id"],
                user_id=result["user_id"],
                reason=result["reason"] or "Payment failed",
                correlation_id=result["correlation_id"],
            )
        else:
            raise ValueError(f"Unexpected payment status {result['status']}")

        producer.publish(topic, payment_event)
        track_kafka_message("payment-service", topic, published=True, success=True)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
