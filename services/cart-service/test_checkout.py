"""Checkout persistence and failure boundaries, without Kafka or Redis servers."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from cart_repository import CartItem, CartRepository
from checkout import CheckoutConflict, CheckoutService, EmptyCart
from models import Base, Checkout
from outbox import CheckoutPublisher


class MemoryRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, **kwargs):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)


class RecordingProducer:
    def __init__(self):
        self.events = []
        self.fail = False

    def publish(self, topic, payload):
        if self.fail:
            raise RuntimeError("Kafka unavailable")
        self.events.append((topic, payload))


class CheckoutTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.directory.name}/cart.db")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.user = "user-1"
        self.repo = CartRepository(MemoryRedis())
        self.prepare()

    def prepare(self):
        self.service = CheckoutService(self.SessionLocal, self.repo)
        self.producer = RecordingProducer()
        self.publisher = CheckoutPublisher(self.SessionLocal, self.producer, self.service, poll_interval=0)
        self.item = CartItem(product_id="product-1", quantity=2, price=10)
        self.service.cart_operation(self.user, lambda cart: cart.add_item(self.user, self.item))

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def rows(self):
        with self.SessionLocal() as db:
            return db.query(Checkout).count()

    def leave_pending_cleanup(self):
        class ProcessDied(BaseException):
            pass

        with patch.object(self.service, "cleanup", side_effect=ProcessDied()):
            with self.assertRaises(ProcessDied):
                self.service.submit(self.user, "key-1")
        with self.SessionLocal() as db:
            return db.query(Checkout).one().response_data

    def test_cleanup_outage_preserves_successful_response_and_recovers(self):
        with patch.object(self.repo, "clear_cart", side_effect=RuntimeError("Redis unavailable")):
            first = self.service.submit(self.user, "key-1")
            self.assertEqual(self.service.submit(self.user, "key-1"), first)
        self.publisher.cleanup_once()
        self.assertEqual(self.repo.get_cart(self.user)["items"], [])
        self.assertEqual(self.rows(), 1)

    def test_response_lost_and_restart_returns_same_response(self):
        response = self.service.submit(self.user, "key-1")
        restarted = CheckoutService(self.SessionLocal, self.repo)
        self.assertEqual(restarted.submit(self.user, "key-1"), response)
        self.assertEqual(self.rows(), 1)
        self.assertEqual(self.repo.get_cart(self.user)["items"], [])
        self.assertTrue(self.publisher.publish_once())
        self.assertFalse(self.publisher.publish_once())
        self.assertEqual(self.producer.events[0][1]["checkout_id"], response["checkout_id"])

    def test_conflicting_user_and_snapshot_are_rejected(self):
        self.service.submit(self.user, "key-1", [self.item.model_dump()])
        with self.assertRaises(CheckoutConflict):
            self.service.submit("other-user", "key-1")
        with self.assertRaises(CheckoutConflict):
            self.service.submit(self.user, "key-1", [{**self.item.model_dump(), "quantity": 3}])
        self.assertEqual(self.rows(), 1)

    def test_initial_snapshot_mismatch_does_not_checkout(self):
        with self.assertRaises(CheckoutConflict):
            self.service.submit(self.user, "key-1", [])
        self.assertEqual(self.rows(), 0)
        self.assertEqual(self.repo.get_cart(self.user)["item_count"], 1)

    def test_headerless_retry_and_new_cart_generation(self):
        with self.assertRaises(EmptyCart):
            self.service.submit("empty-user")
        first = self.service.submit(self.user)
        self.assertEqual(self.service.submit(self.user), first)
        self.service.cart_operation(self.user, lambda cart: cart.add_item(self.user, self.item))
        second = self.service.submit(self.user)
        self.assertNotEqual(first["checkout_id"], second["checkout_id"])
        self.assertEqual(self.rows(), 2)

    def test_kafka_ack_before_cleanup_and_request_retry(self):
        response = self.leave_pending_cleanup()
        self.assertTrue(self.publisher.publish_once())
        restarted = CheckoutService(self.SessionLocal, self.repo)
        self.assertEqual(restarted.submit(self.user, "key-1"), response)
        self.assertEqual(self.rows(), 1)
        self.assertEqual(len(self.producer.events), 1)
        self.assertEqual(self.repo.get_cart(self.user)["items"], [])

    def test_new_items_survive_delayed_cleanup_and_replayed_response(self):
        response = self.leave_pending_cleanup()
        new_item = CartItem(product_id="new-product", quantity=1, price=5)
        self.service.cart_operation(self.user, lambda cart: cart.add_item(self.user, new_item))
        self.service.cleanup(self.user)
        self.assertEqual(self.service.submit(self.user, "key-1"), response)
        self.assertEqual(self.repo.get_cart(self.user)["items"][0]["product_id"], "new-product")
        with self.assertRaises(CheckoutConflict):
            self.service.submit(self.user, "key-1", [new_item.model_dump()])

    def test_cleanup_commit_failure_cannot_erase_subsequent_write(self):
        self.leave_pending_cleanup()

        def fail_cleanup(db):
            if any(isinstance(row, Checkout) and row.cart_cleared for row in db.dirty):
                raise RuntimeError("cleanup commit failed")

        event.listen(self.SessionLocal, "before_commit", fail_cleanup)
        try:
            with self.assertRaisesRegex(RuntimeError, "cleanup commit failed"):
                self.service.cart_operation(self.user, lambda cart: cart.add_item(self.user, self.item))
        finally:
            event.remove(self.SessionLocal, "before_commit", fail_cleanup)
        self.service.cart_operation(self.user, lambda cart: cart.add_item(self.user, self.item))
        self.service.cleanup(self.user)
        self.assertEqual(self.repo.get_cart(self.user)["items"][0]["quantity"], 2)

    def test_checkout_commit_failure_keeps_cart_and_no_event(self):
        def fail_checkout(db):
            if any(isinstance(row, Checkout) for row in db.new):
                raise RuntimeError("checkout commit failed")

        event.listen(self.SessionLocal, "before_commit", fail_checkout)
        try:
            with self.assertRaises(RuntimeError):
                self.service.submit(self.user, "key-1")
        finally:
            event.remove(self.SessionLocal, "before_commit", fail_checkout)
        self.assertEqual(self.rows(), 0)
        self.assertFalse(self.publisher.publish_once())
        self.assertEqual(self.repo.get_cart(self.user)["item_count"], 1)

    def test_publication_failure_recovers_without_request_retry(self):
        self.service.submit(self.user, "key-1")
        self.producer.fail = True
        self.publisher.publish_once()
        with self.SessionLocal() as db:
            row = db.query(Checkout).one()
            self.assertFalse(row.published)
            event_id = json.loads(row.event_data)["event_id"]
        self.producer.fail = False
        restarted = CheckoutPublisher(self.SessionLocal, self.producer, self.service, poll_interval=0)
        self.assertTrue(restarted.publish_once())
        self.assertEqual(self.producer.events[0][1]["event_id"], event_id)

    def test_ack_then_process_death_resends_same_event_after_lease_expiry(self):
        self.service.submit(self.user, "key-1")

        class ProcessDied(BaseException):
            pass

        original_publish = self.producer.publish

        def die_after_ack(topic, payload):
            original_publish(topic, payload)
            raise ProcessDied()

        with patch.object(self.producer, "publish", side_effect=die_after_ack):
            with self.assertRaises(ProcessDied):
                self.publisher.publish_once()
        restarted = CheckoutPublisher(self.SessionLocal, self.producer, self.service, poll_interval=0)
        self.assertFalse(restarted.publish_once())
        with self.SessionLocal.begin() as db:
            db.query(Checkout).update({Checkout.claimed_until: datetime(2000, 1, 1)})
        self.assertTrue(restarted.publish_once())
        self.assertEqual(self.producer.events[0], self.producer.events[1])

    def test_background_cleanup_recovers_already_published_checkout(self):
        self.leave_pending_cleanup()
        self.publisher.publish_once()
        self.publisher.cleanup_once()
        with self.SessionLocal() as db:
            row = db.query(Checkout).one()
            self.assertTrue(row.published)
            self.assertTrue(row.cart_cleared)


if __name__ == "__main__":
    unittest.main()
