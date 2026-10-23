"""Payment result persistence and outbox delivery without Kafka."""

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
from kafka_client import KafkaDeliveryError, RetryableProcessingError
from models import Base, Payment, PaymentOutboxEvent, PaymentResult
from outbox import PaymentOutboxPublisher, backfill_payment_outbox
from payment_handler import handle_payment_event


class RecordingProducer:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.events = []
        self.fail_once = False

    def publish(self, topic, event):
        with self.session_factory() as db:
            assert db.query(Payment).filter_by(order_id=event["order_id"]).count() == 1
            assert db.query(PaymentOutboxEvent).filter_by(order_id=event["order_id"]).count() == 1
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
        self.publisher = PaymentOutboxPublisher(self.SessionLocal, self.producer, poll_interval=0)
        self.event = OrderReservationConfirmedEvent(
            order_id="order-1", user_id="user-1", total_amount=10,
            correlation_id="correlation-1",
        )

    def tearDown(self):
        self.engine.dispose()
        self.database_dir.cleanup()

    def handle(self, process):
        handle_payment_event(self.event, self.SessionLocal, self.producer, process)

    def test_success_commits_before_publish_and_replays_same_id(self):
        outcomes = []

        def process(_amount):
            outcomes.append(1)
            return True, None

        self.handle(process)
        self.handle(process)
        self.assertEqual(outcomes, [1])
        self.assertEqual(self.producer.events, [])
        self.assertTrue(self.publisher.publish_once())
        self.assertFalse(self.publisher.publish_once())
        self.assertEqual(self.producer.events[0][0], "payment.processed")
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Payment).count(), 1)
            self.assertEqual(db.query(PaymentResult).count(), 1)
            row = db.query(PaymentOutboxEvent).one()
            self.assertTrue(row.published)
            self.assertEqual(row.event_id, self.producer.events[0][1]["event_id"])

    def test_failed_payment_replays_failure(self):
        self.handle(lambda _: (False, "declined"))
        self.handle(lambda _: self.fail("charged twice"))
        self.publisher.publish_once()
        self.assertEqual(self.producer.events[0][0], "payment.failed")
        self.assertEqual(self.producer.events[0][1]["reason"], "declined")

    def test_publish_failure_recovers_without_input_redelivery(self):
        self.producer.fail_once = True
        self.handle(lambda _: (True, None))
        self.assertTrue(self.publisher.publish_once())
        with self.SessionLocal() as db:
            row = db.query(PaymentOutboxEvent).one()
            self.assertFalse(row.published)
            original_id = row.event_id
        self.assertTrue(self.publisher.publish_once())
        self.assertEqual(self.producer.events[0][1]["event_id"], original_id)
        self.handle(lambda _: self.fail("charged twice"))
        self.assertFalse(self.publisher.publish_once())

    def test_commit_failure_never_publishes_or_persists(self):
        from sqlalchemy.orm import Session

        with patch.object(Session, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                self.handle(lambda _: (True, None))
        self.assertEqual(self.producer.events, [])
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Payment).count(), 0)
            self.assertEqual(db.query(PaymentResult).count(), 0)
            self.assertEqual(db.query(PaymentOutboxEvent).count(), 0)

    def test_processor_error_does_not_acknowledge_an_unfinished_payment(self):
        def unavailable(_amount):
            raise RuntimeError("gateway unavailable")

        with self.assertRaises(RetryableProcessingError):
            self.handle(unavailable)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Payment).count(), 0)
            self.assertEqual(db.query(PaymentOutboxEvent).count(), 0)

    def test_existing_result_without_outbox_is_queued_with_original_id(self):
        with self.SessionLocal.begin() as db:
            db.add(Payment(
                payment_id="PAY-OLD", order_id="order-1", user_id="user-1",
                amount=10, currency="USD", method="card", status="SUCCESS",
            ))
            db.add(PaymentResult(
                order_id="order-1", event_id="original-event", correlation_id="correlation-1",
            ))
        self.handle(lambda _: self.fail("charged twice"))
        self.publisher.publish_once()
        self.assertEqual(self.producer.events[0][1]["event_id"], "original-event")

    def test_startup_backfills_previous_payment_result(self):
        with self.SessionLocal.begin() as db:
            db.add(Payment(
                payment_id="PAY-OLD", order_id="order-1", user_id="user-1",
                amount=10, currency="USD", method="card", status="SUCCESS",
            ))
            db.add(PaymentResult(
                order_id="order-1", event_id="original-event", correlation_id="correlation-1",
            ))
        with self.SessionLocal.begin() as db:
            self.assertEqual(backfill_payment_outbox(db), 1)
        with self.SessionLocal.begin() as db:
            self.assertEqual(backfill_payment_outbox(db), 0)
        self.publisher.publish_once()
        self.assertEqual(self.producer.events[0][1]["event_id"], "original-event")

    def test_conflicting_request_does_not_change_payment(self):
        self.handle(lambda _: (True, None))
        conflicting = self.event.model_copy(update={"total_amount": 11})
        with self.assertRaisesRegex(ValueError, "Conflicting payment"):
            handle_payment_event(conflicting, self.SessionLocal, self.producer,
                                 lambda _: self.fail("charged twice"))
        with self.SessionLocal() as db:
            self.assertEqual(db.query(PaymentOutboxEvent).count(), 1)

    def test_legacy_payment_is_not_replayed_with_new_event_id(self):
        with self.SessionLocal.begin() as db:
            db.add(Payment(
                payment_id="PAY-LEGACY", order_id="order-1", user_id="user-1",
                amount=10, currency="USD", method="card", status="SUCCESS",
            ))
        self.handle(lambda _: self.fail("charged twice"))
        self.assertFalse(self.publisher.publish_once())


if __name__ == "__main__":
    unittest.main()
