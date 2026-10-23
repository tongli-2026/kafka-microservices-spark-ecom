"""One business order per checkout, even when Kafka event IDs differ."""

import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from events import CartCheckoutInitiatedEvent
from models import Base, Order, OutboxEvent, ProcessedEvent
from saga_handler import SagaHandler


class CheckoutIdentityTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.directory.name}/order.db")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.directory.cleanup()

    def checkout_event(self, **changes):
        data = dict(event_id="event-1", checkout_id="checkout-1", user_id="user-1",
                    items=[{"product_id": "product-1", "quantity": 2, "price": 10}],
                    total_amount=20, correlation_id="correlation-1")
        data.update(changes)
        return CartCheckoutInitiatedEvent(**data)

    def handle(self, event):
        with self.SessionLocal() as db:
            SagaHandler(db).handle_cart_checkout_initiated(event)

    def counts(self):
        with self.SessionLocal() as db:
            return tuple(db.query(model).count() for model in (Order, OutboxEvent, ProcessedEvent))

    def test_same_business_checkout_with_different_event_ids_creates_one_order(self):
        self.handle(self.checkout_event())
        self.handle(self.checkout_event(event_id="event-2"))
        self.handle(self.checkout_event())
        self.assertEqual(self.counts(), (1, 1, 2))

    def test_conflicting_business_payload_is_rejected(self):
        self.handle(self.checkout_event())
        for changes in ({"user_id": "other-user"}, {"total_amount": 30}, {"items": []}):
            with self.assertRaisesRegex(ValueError, "Conflicting checkout"):
                self.handle(self.checkout_event(event_id="conflict", **changes))
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_legacy_events_remain_idempotent_by_event_id(self):
        legacy = self.checkout_event(checkout_id=None)
        self.handle(legacy)
        self.handle(legacy)
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_new_checkout_for_same_user_can_create_another_order(self):
        self.handle(self.checkout_event())
        self.handle(self.checkout_event(checkout_id="checkout-2", event_id="event-2"))
        self.assertEqual(self.counts(), (2, 2, 2))

    def test_database_unique_index_prevents_duplicate_checkout(self):
        self.handle(self.checkout_event())
        with self.assertRaises(IntegrityError):
            with self.SessionLocal.begin() as db:
                db.add(Order(order_id="other-order", checkout_id="checkout-1", user_id="user-1",
                             correlation_id="other-corr", items=[], total_amount=20))
        self.assertEqual(self.counts(), (1, 1, 1))
