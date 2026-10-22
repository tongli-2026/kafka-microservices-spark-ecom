"""Durable inventory result delivery with short PostgreSQL claim leases."""

import json
import logging
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select

from events import InventoryDepletedEvent, InventoryReservedEvent
from models import InventoryOrder, InventoryOutboxEvent
from shared.metrics import track_kafka_message

logger = logging.getLogger(__name__)


def queue_result(db, order_id, topic, event):
    """Call before committing the inventory result; one result per order."""
    db.add(InventoryOutboxEvent(
        order_id=order_id,
        event_id=event.event_id,
        event_type=topic,
        event_data=event.model_dump_json(),
    ))


def backfill_result_outbox(db):
    """Queue recoverable results created before this table existed.

    Already released orders and legacy rows without an original result ID
    cannot safely be reconstructed. Existing result IDs are always preserved.
    """
    orders = db.query(InventoryOrder).filter(
        InventoryOrder.status.in_(("RESERVED", "DEPLETED")),
        InventoryOrder.result_event_id.is_not(None),
        InventoryOrder.result_correlation_id.is_not(None),
    ).with_for_update().all()
    queued = 0
    for order in orders:
        if db.query(InventoryOutboxEvent.id).filter_by(order_id=order.order_id).first():
            continue
        if order.status == "RESERVED":
            topic = "inventory.reserved"
            event = InventoryReservedEvent(
                event_id=order.result_event_id,
                order_id=order.order_id,
                items=json.loads(order.items_json),
                correlation_id=order.result_correlation_id,
            )
        else:
            topic = "inventory.depleted"
            event = InventoryDepletedEvent(
                event_id=order.result_event_id,
                order_id=order.order_id,
                product_id=order.failed_product_id,
                correlation_id=order.result_correlation_id,
            )
        queue_result(db, order.order_id, topic, event)
        queued += 1
    return queued


class InventoryOutboxPublisher:
    """Claim briefly, publish outside a DB transaction, then mark by token."""

    def __init__(self, session_factory, producer, poll_interval=2, lease_seconds=60):
        self.session_factory = session_factory
        self.producer = producer
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self._stop = threading.Event()
        self._thread = None

    def _claim_next(self):
        with self.session_factory.begin() as db:
            row = db.query(InventoryOutboxEvent).filter(
                InventoryOutboxEvent.published.is_(False),
                or_(
                    InventoryOutboxEvent.claimed_until.is_(None),
                    InventoryOutboxEvent.claimed_until <= func.now(),
                ),
            ).order_by(
                InventoryOutboxEvent.created_at, InventoryOutboxEvent.id,
            ).with_for_update(skip_locked=True).first()
            if row is None:
                return None
            token = str(uuid4())
            now = db.execute(select(func.now())).scalar_one()
            row.claim_token = token
            row.claimed_until = now + timedelta(seconds=self.lease_seconds)
            row.attempts += 1
            return row.id, token, row.order_id, row.event_type, row.event_id, row.event_data

    def _mark_published(self, row_id, token):
        with self.session_factory.begin() as db:
            updated = db.query(InventoryOutboxEvent).filter(
                and_(
                    InventoryOutboxEvent.id == row_id,
                    InventoryOutboxEvent.claim_token == token,
                    InventoryOutboxEvent.published.is_(False),
                )
            ).update({
                InventoryOutboxEvent.published: True,
                InventoryOutboxEvent.published_at: func.now(),
                InventoryOutboxEvent.claim_token: None,
                InventoryOutboxEvent.claimed_until: None,
                InventoryOutboxEvent.last_error: None,
            }, synchronize_session=False)
            if updated != 1:
                logger.warning("Outbox claim expired before marking event %s published", row_id)

    def _record_failure(self, row_id, token, error):
        # Keep the row pending. A short retry delay avoids a tight failure loop;
        # a crash before this update is recovered when the original lease ends.
        with self.session_factory.begin() as db:
            now = db.execute(select(func.now())).scalar_one()
            db.query(InventoryOutboxEvent).filter(
                InventoryOutboxEvent.id == row_id,
                InventoryOutboxEvent.claim_token == token,
                InventoryOutboxEvent.published.is_(False),
            ).update({
                InventoryOutboxEvent.claim_token: None,
                InventoryOutboxEvent.claimed_until: (
                    now + timedelta(seconds=self.poll_interval) if self.poll_interval else None
                ),
                InventoryOutboxEvent.last_error: str(error)[:4000],
            }, synchronize_session=False)

    def publish_once(self):
        """Attempt one pending record. Return False only when none is ready."""
        claimed = self._claim_next()
        if claimed is None:
            return False
        row_id, token, order_id, topic, event_id, event_data = claimed
        try:
            payload = json.loads(event_data)
            if payload["event_id"] != event_id or payload["event_type"] != topic:
                raise ValueError(f"Outbox payload mismatch for order {order_id}")
            # BaseKafkaProducer.publish waits for the delivery callback.
            self.producer.publish(topic, payload)
            self._mark_published(row_id, token)
            track_kafka_message("inventory-service", topic, published=True, success=True)
            logger.info("Published inventory outbox event %s for order %s", event_id, order_id)
        except Exception as error:
            logger.exception("Inventory outbox publication failed for order %s", order_id)
            try:
                self._record_failure(row_id, token, error)
            except Exception:
                logger.exception("Could not record outbox failure; lease will expire for %s", event_id)
        return True

    def _run(self):
        while not self._stop.is_set():
            try:
                self.publish_once()
            except Exception:
                logger.exception("Inventory outbox polling failed")
            self._stop.wait(self.poll_interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="inventory-outbox", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=35)
