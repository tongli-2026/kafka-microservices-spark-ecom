"""Order state guards and transactional outgoing events."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from kafka_client import RetryableProcessingError
from models import Base, Order, OutboxEvent, ProcessedEvent
from saga_handler import SagaHandler


class SagaTransitionsTest(unittest.TestCase):
    def setUp(self):
        self.database_dir = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.database_dir.name}/order.db")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        with self.SessionLocal.begin() as db:
            db.add(Order(order_id="order-1", user_id="user-1", correlation_id="corr-1",
                         items=[{"product_id": "product-1", "quantity": 1}],
                         total_amount=10, status="PENDING"))

    def tearDown(self):
        self.engine.dispose()
        self.database_dir.cleanup()

    def event(self, event_type, event_id, **fields):
        return SimpleNamespace(event_type=event_type, event_id=event_id,
                               order_id="order-1", user_id="user-1",
                               correlation_id="corr-1", product_id="product-1",
                               **fields)

    def handle(self, method, event):
        with self.SessionLocal() as db:
            getattr(SagaHandler(db), method)(event)

    def state(self):
        with self.SessionLocal() as db:
            return db.query(Order).one().status, db.query(OutboxEvent).count(), db.query(ProcessedEvent).count()

    def reserve(self):
        self.handle("handle_inventory_reserved", self.event("inventory.reserved", "inventory-1"))

    def test_success_duplicate_and_fulfillment(self):
        self.reserve()
        self.reserve()
        self.assertEqual(self.state(), ("RESERVATION_CONFIRMED", 1, 1))
        self.handle("handle_payment_processed", self.event("payment.processed", "payment-1"))
        self.handle("handle_payment_processed", self.event("payment.processed", "payment-2"))
        self.assertEqual(self.state(), ("PAID", 2, 3))
        self.handle("handle_order_fulfilled", self.event("order.fulfilled", "fulfill-1"))
        self.assertEqual(self.state(), ("FULFILLED", 2, 4))

    def test_late_payment_success_cannot_reactivate_cancelled_order(self):
        self.handle("handle_inventory_depleted", self.event("inventory.depleted", "depleted-1"))
        self.handle("handle_payment_processed", self.event("payment.processed", "late-success"))
        self.assertEqual(self.state(), ("CANCELLED", 1, 2))

    def test_late_payment_failure_cannot_cancel_fulfilled_order(self):
        self.reserve()
        self.handle("handle_payment_processed", self.event("payment.processed", "payment-1"))
        self.handle("handle_order_fulfilled", self.event("order.fulfilled", "fulfill-1"))
        self.handle("handle_payment_failed", self.event("payment.failed", "late-failure", reason="declined"))
        self.assertEqual(self.state(), ("FULFILLED", 2, 4))

    def test_payment_failure_emits_one_compensation_event(self):
        self.reserve()
        self.handle("handle_payment_failed", self.event("payment.failed", "failure-1", reason="declined"))
        self.handle("handle_payment_failed", self.event("payment.failed", "failure-2", reason="declined"))
        self.assertEqual(self.state(), ("CANCELLED", 2, 3))
        with self.SessionLocal() as db:
            self.assertIn('"cancellation_source": "payment_failed"',
                          db.query(OutboxEvent).filter_by(event_type="order.cancelled").one().event_data)

    def test_missing_and_premature_order_state_are_retryable(self):
        with self.assertRaises(RetryableProcessingError):
            self.handle("handle_payment_processed", self.event("payment.processed", "early"))
        with self.assertRaises(RetryableProcessingError):
            self.handle("handle_inventory_reserved", SimpleNamespace(
                event_type="inventory.reserved", event_id="missing", order_id="missing"))
        self.assertEqual(self.state(), ("PENDING", 0, 0))


if __name__ == "__main__":
    unittest.main()
