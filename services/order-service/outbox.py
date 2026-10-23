"""Publish Order outbox events with short PostgreSQL claim leases."""

import json
import logging
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select

from models import OutboxEvent

logger = logging.getLogger(__name__)


class OutboxPublisher:
    def __init__(self, session_factory, producer, poll_interval=2, lease_seconds=60):
        self.session_factory = session_factory
        self.producer = producer
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self._stop = threading.Event()
        self._thread = None

    def _claim_next(self):
        with self.session_factory.begin() as db:
            row = db.query(OutboxEvent).filter(
                OutboxEvent.published == "N",
                or_(OutboxEvent.claimed_until.is_(None),
                    OutboxEvent.claimed_until <= func.now()),
            ).order_by(OutboxEvent.created_at, OutboxEvent.id).with_for_update(skip_locked=True).first()
            if row is None:
                return None
            token = str(uuid4())
            now = db.execute(select(func.now())).scalar_one()
            row.claim_token = token
            row.claimed_until = now + timedelta(seconds=self.lease_seconds)
            row.attempts += 1
            return row.id, token, row.event_type, row.event_data

    def _mark_published(self, row_id, token):
        with self.session_factory.begin() as db:
            updated = db.query(OutboxEvent).filter_by(
                id=row_id, claim_token=token, published="N",
            ).update({
                OutboxEvent.published: "Y",
                OutboxEvent.published_at: func.now(),
                OutboxEvent.claim_token: None,
                OutboxEvent.claimed_until: None,
                OutboxEvent.last_error: None,
            }, synchronize_session=False)
            if updated != 1:
                logger.warning("Order outbox claim expired for %s", row_id)

    def _record_failure(self, row_id, token, error):
        with self.session_factory.begin() as db:
            now = db.execute(select(func.now())).scalar_one()
            db.query(OutboxEvent).filter_by(
                id=row_id, claim_token=token, published="N",
            ).update({
                OutboxEvent.claim_token: None,
                OutboxEvent.claimed_until: (
                    now + timedelta(seconds=self.poll_interval) if self.poll_interval else None
                ),
                OutboxEvent.last_error: str(error)[:4000],
            }, synchronize_session=False)

    def publish_once(self):
        """Attempt one available row; return False only when none is ready."""
        claimed = self._claim_next()
        if claimed is None:
            return False
        row_id, token, topic, event_data = claimed
        try:
            payload = json.loads(event_data)
            if payload["event_type"] != topic or not payload.get("event_id"):
                raise ValueError(f"Invalid Order outbox payload {row_id}")
            self.producer.publish(topic, payload)
            self._mark_published(row_id, token)
            logger.info("Published Order outbox event %s for %s", payload["event_id"], topic)
        except Exception as error:
            logger.exception("Order outbox publication failed for %s", row_id)
            try:
                self._record_failure(row_id, token, error)
            except Exception:
                logger.exception("Order outbox lease will expire for %s", row_id)
        return True

    def _run(self):
        while not self._stop.is_set():
            try:
                self.publish_once()
            except Exception:
                logger.exception("Order outbox polling failed")
            self._stop.wait(self.poll_interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="order-outbox", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=35)
