"""Publish committed payment outcomes with at-least-once delivery."""

import json
import logging
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select

from models import Payment, PaymentOutboxEvent, PaymentResult

logger = logging.getLogger(__name__)


def backfill_payment_outbox(db):
    """Recover pre-outbox results without inventing a new event identity."""
    from payment_handler import _result_event

    queued = 0
    results = db.query(PaymentResult).with_for_update().all()
    for result in results:
        if db.get(PaymentOutboxEvent, result.order_id) is not None:
            continue
        payment = db.query(Payment).filter_by(order_id=result.order_id).one_or_none()
        if payment is None:
            logger.error("Payment result %s has no payment row", result.order_id)
            continue
        topic, event = _result_event(payment, result)
        db.add(PaymentOutboxEvent(
            order_id=result.order_id, event_id=result.event_id,
            event_type=topic, event_data=event.model_dump_json(),
        ))
        queued += 1
    return queued


class PaymentOutboxPublisher:
    def __init__(self, session_factory, producer, poll_interval=2, lease_seconds=60):
        self.session_factory = session_factory
        self.producer = producer
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self._stop = threading.Event()
        self._thread = None

    def _claim_next(self):
        with self.session_factory.begin() as db:
            row = db.query(PaymentOutboxEvent).filter(
                PaymentOutboxEvent.published.is_(False),
                or_(PaymentOutboxEvent.claimed_until.is_(None),
                    PaymentOutboxEvent.claimed_until <= func.now()),
            ).order_by(PaymentOutboxEvent.created_at).with_for_update(skip_locked=True).first()
            if row is None:
                return None
            token = str(uuid4())
            now = db.execute(select(func.now())).scalar_one()
            row.claim_token = token
            row.claimed_until = now + timedelta(seconds=self.lease_seconds)
            row.attempts += 1
            return row.order_id, token, row.event_type, row.event_id, row.event_data

    def publish_once(self):
        claimed = self._claim_next()
        if claimed is None:
            return False
        order_id, token, topic, event_id, event_data = claimed
        try:
            payload = json.loads(event_data)
            if payload["event_id"] != event_id or payload["event_type"] != topic:
                raise ValueError(f"Invalid payment outbox payload for {order_id}")
            self.producer.publish(topic, payload)
            with self.session_factory.begin() as db:
                updated = db.query(PaymentOutboxEvent).filter_by(
                    order_id=order_id, claim_token=token, published=False,
                ).update({
                    PaymentOutboxEvent.published: True,
                    PaymentOutboxEvent.published_at: func.now(),
                    PaymentOutboxEvent.claim_token: None,
                    PaymentOutboxEvent.claimed_until: None,
                    PaymentOutboxEvent.last_error: None,
                }, synchronize_session=False)
                if updated != 1:
                    logger.warning("Payment outbox claim expired for %s", order_id)
        except Exception as error:
            logger.exception("Payment result publication failed for %s", order_id)
            try:
                with self.session_factory.begin() as db:
                    now = db.execute(select(func.now())).scalar_one()
                    db.query(PaymentOutboxEvent).filter_by(
                        order_id=order_id, claim_token=token, published=False,
                    ).update({
                        PaymentOutboxEvent.claim_token: None,
                        PaymentOutboxEvent.claimed_until: (
                            now + timedelta(seconds=self.poll_interval) if self.poll_interval else None
                        ),
                        PaymentOutboxEvent.last_error: str(error)[:4000],
                    }, synchronize_session=False)
            except Exception:
                logger.exception("Payment outbox lease will expire for %s", order_id)
        return True

    def _run(self):
        while not self._stop.is_set():
            try:
                self.publish_once()
            except Exception:
                logger.exception("Payment outbox polling failed")
            self._stop.wait(self.poll_interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="payment-outbox", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=35)
