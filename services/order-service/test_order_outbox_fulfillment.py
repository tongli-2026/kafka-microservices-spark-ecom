"""Stable fulfillment enqueueing and Order outbox recovery without Kafka."""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from fulfillment import queue_fulfillment_events
from models import Base, Order, OutboxEvent
from outbox import OutboxPublisher


class RecordingProducer:
    def __init__(self):
        self.events = []
        self.fail_once = False

    def publish(self, topic, payload):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("Kafka unavailable")
        self.events.append((topic, payload))


class OrderOutboxFulfillmentTest(unittest.TestCase):
    def setUp(self):
        self.database_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.database_dir.name}/order.db")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.now = datetime.now(ZoneInfo("America/Los_Angeles"))
        with self.SessionLocal.begin() as db:
            db.add(Order(
                order_id="order-1", user_id="user-1", correlation_id="corr-1",
                items=[{"product_id": "product-1", "quantity": 1}],
                total_amount=10, status="PAID",
                updated_at=self.now - timedelta(minutes=1),
            ))
        self.producer = RecordingProducer()
        self.publisher = OutboxPublisher(self.SessionLocal, self.producer, poll_interval=0)

    def tearDown(self):
        self.engine.dispose()
        self.database_dir.cleanup()

    def queue(self):
        return queue_fulfillment_events(self.SessionLocal, delay_seconds=5, now=self.now)

    def test_paid_order_is_queued_once_with_stable_payload(self):
        self.assertEqual(self.queue(), 1)
        self.assertEqual(self.queue(), 0)
        with self.SessionLocal() as db:
            rows = db.query(OutboxEvent).all()
            self.assertEqual(len(rows), 1)
            payload = json.loads(rows[0].event_data)
            self.assertEqual(payload["event_type"], "order.fulfilled")
            self.assertEqual(payload["order_id"], "order-1")
            original_id = payload["event_id"]
        self.assertTrue(self.publisher.publish_once())
        self.assertFalse(self.publisher.publish_once())
        self.assertEqual(self.producer.events[0][1]["event_id"], original_id)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(OutboxEvent).one().published, "Y")

    def test_publish_failure_retries_same_event_id(self):
        self.queue()
        self.producer.fail_once = True
        self.assertTrue(self.publisher.publish_once())
        with self.SessionLocal() as db:
            row = db.query(OutboxEvent).one()
            self.assertEqual(row.published, "N")
            original_id = json.loads(row.event_data)["event_id"]
        self.assertTrue(self.publisher.publish_once())
        self.assertEqual(self.producer.events[0][1]["event_id"], original_id)

    def test_claim_lease_prevents_second_publisher_and_stale_mark(self):
        self.queue()
        first_claim = self.publisher._claim_next()
        other = OutboxPublisher(self.SessionLocal, self.producer, poll_interval=0)
        self.assertFalse(other.publish_once())
        with self.SessionLocal.begin() as db:
            db.query(OutboxEvent).update({OutboxEvent.claimed_until: self.now - timedelta(minutes=1)})
        self.assertTrue(other.publish_once())
        self.publisher._mark_published(first_claim[0], first_claim[1])
        self.assertEqual(len(self.producer.events), 1)

    def test_enqueue_failure_rolls_back_and_can_retry(self):
        with patch("fulfillment.OrderRepository.add_outbox_event", side_effect=RuntimeError("db error")):
            with self.assertRaisesRegex(RuntimeError, "db error"):
                self.queue()
        with self.SessionLocal() as db:
            self.assertEqual(db.query(OutboxEvent).count(), 0)
        self.assertEqual(self.queue(), 1)

    def test_only_ready_paid_orders_are_queued(self):
        with self.SessionLocal.begin() as db:
            db.query(Order).update({Order.updated_at: self.now})
        self.assertEqual(self.queue(), 0)
        with self.SessionLocal.begin() as db:
            db.query(Order).update({Order.status: "CANCELLED",
                                    Order.updated_at: self.now - timedelta(minutes=1)})
        self.assertEqual(self.queue(), 0)


if __name__ == "__main__":
    unittest.main()
