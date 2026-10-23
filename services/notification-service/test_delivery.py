"""Durable notification state and retry behavior without an SMTP server."""

import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from delivery import NotificationDeliveryService
from kafka_client import RetryableProcessingError
from models import Base, NotificationDelivery


class FakeSender:
    def __init__(self, responses=None, delay=0):
        self.responses = list(responses or [True])
        self.delay = delay
        self.calls = 0
        self.lock = threading.Lock()

    def send_email(self, *_args):
        with self.lock:
            self.calls += 1
            result = self.responses.pop(0) if self.responses else True
        if self.delay:
            time.sleep(self.delay)
        if isinstance(result, BaseException):
            raise result
        return result


class NotificationDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.database_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.database_dir.name}/notification.db")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.delivery = NotificationDeliveryService(self.SessionLocal)
        self.event = SimpleNamespace(event_id="event-1", event_type="order.confirmed")

    def tearDown(self):
        self.engine.dispose()
        self.database_dir.cleanup()

    def send(self, sender):
        return self.delivery.send(self.event, sender, "user@example.com", "Subject", "Body")

    def test_duplicate_after_success_does_not_resend(self):
        sender = FakeSender()
        self.assertTrue(self.send(sender))
        self.assertIsNone(self.send(sender))
        self.assertEqual(sender.calls, 1)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(NotificationDelivery).one().status, "SENT")

    def test_failure_persists_and_retry_succeeds(self):
        sender = FakeSender([False, True])
        with self.assertRaises(RetryableProcessingError):
            self.send(sender)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(NotificationDelivery).one().status, "FAILED")
        self.assertTrue(self.send(sender))
        self.assertEqual(sender.calls, 2)
        with self.SessionLocal() as db:
            row = db.query(NotificationDelivery).one()
            self.assertEqual((row.status, row.attempts), ("SENT", 2))

    def test_concurrent_consumers_send_once(self):
        sender = FakeSender(delay=0.2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=10) for future in
                       [pool.submit(self.send, sender) for _ in range(2)]]
        self.assertEqual(sender.calls, 1)
        self.assertCountEqual(results, [True, None])

    def test_abandoned_transaction_is_retried(self):
        # A process death while SMTP is in progress rolls back the DB attempt.
        sender = FakeSender([KeyboardInterrupt(), True])
        with self.assertRaises(KeyboardInterrupt):
            self.send(sender)
        self.assertTrue(self.send(sender))
        with self.SessionLocal() as db:
            self.assertEqual(db.query(NotificationDelivery).one().status, "SENT")


if __name__ == "__main__":
    unittest.main()
