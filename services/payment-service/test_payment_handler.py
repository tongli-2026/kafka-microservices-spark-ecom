"""Payment result replay and commit ordering without a Kafka broker."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from events import OrderReservationConfirmedEvent
from kafka_client import KafkaDeliveryError
from models import Base, Payment, PaymentResult
from payment_handler import handle_payment_event


class RecordingProducer:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.events = []
        self.fail_once = False

    def publish(self, topic, event):
        with self.session_factory() as db:
            assert db.query(Payment).filter_by(order_id=event.order_id).count() == 1
        if self.fail_once:
            self.fail_once = False
            raise KafkaDeliveryError("Kafka unavailable")
        self.events.append((topic, event))


class PaymentHandlerTest(unittest.TestCase):
    def setUp(self):
        self.database_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.database_dir.name}/payment.db")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.producer = RecordingProducer(self.SessionLocal)
        self.event = OrderReservationConfirmedEvent(
            order_id="order-1", user_id="user-1", total_amount=10,
            correlation_id="correlation-1",
        )

    def tearDown(self):
        self.engine.dispose()
        self.database_dir.cleanup()

    def test_success_commits_before_publish_and_replays_same_id(self):
        outcomes = []

        def process(_amount):
            outcomes.append(1)
            return True, None

        handle_payment_event(self.event, self.SessionLocal, self.producer, process)
        handle_payment_event(self.event, self.SessionLocal, self.producer, process)
        self.assertEqual(outcomes, [1])
        self.assertEqual([topic for topic, _ in self.producer.events], ["payment.processed"] * 2)
        self.assertEqual(self.producer.events[0][1].event_id, self.producer.events[1][1].event_id)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Payment).count(), 1)
            self.assertEqual(db.query(PaymentResult).count(), 1)

    def test_failed_payment_replays_failure(self):
        handle_payment_event(self.event, self.SessionLocal, self.producer, lambda _: (False, "declined"))
        handle_payment_event(self.event, self.SessionLocal, self.producer, lambda _: self.fail("charged twice"))
        self.assertEqual([topic for topic, _ in self.producer.events], ["payment.failed"] * 2)
        self.assertEqual(self.producer.events[0][1].event_id, self.producer.events[1][1].event_id)
        self.assertEqual(self.producer.events[1][1].reason, "declined")

    def test_publish_failure_replays_committed_outcome(self):
        self.producer.fail_once = True
        with self.assertRaises(KafkaDeliveryError):
            handle_payment_event(self.event, self.SessionLocal, self.producer, lambda _: (True, None))
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Payment).count(), 1)
        handle_payment_event(self.event, self.SessionLocal, self.producer, lambda _: self.fail("charged twice"))
        self.assertEqual(self.producer.events[0][0], "payment.processed")

    def test_commit_failure_never_publishes(self):
        from sqlalchemy.orm import Session

        with patch.object(Session, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                handle_payment_event(self.event, self.SessionLocal, self.producer, lambda _: (True, None))
        self.assertEqual(self.producer.events, [])
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Payment).count(), 0)
            self.assertEqual(db.query(PaymentResult).count(), 0)

    def test_legacy_payment_is_not_replayed_with_new_event_id(self):
        with self.SessionLocal.begin() as db:
            db.add(Payment(
                payment_id="PAY-LEGACY", order_id="order-1", user_id="user-1",
                amount=10, currency="USD", method="card", status="SUCCESS",
            ))
        handle_payment_event(self.event, self.SessionLocal, self.producer, lambda _: self.fail("charged twice"))
        self.assertEqual(self.producer.events, [])


if __name__ == "__main__":
    unittest.main()
