"""Database-backed inventory saga tests; Kafka is replaced with a recording producer."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from events import OrderCancelledEvent, OrderCreatedEvent
from main import handle_inventory_event
from models import Base, Product, StockReservation
from repository import InventoryRepository


class RecordingSession(Session):
    def close(self):
        self.info["closed"] = True
        super().close()


class RecordingProducer:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.events = []

    def publish(self, topic, event):
        # A separate connection must see the committed state before success is sent.
        if topic == "inventory.reserved":
            with self.session_factory() as db:
                assert db.query(StockReservation).filter_by(order_id=event.order_id).count() == len(event.items)
        self.events.append((topic, event))


class InventoryTransactionsTest(unittest.TestCase):
    def setUp(self):
        self.database_file = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.database_file.name}/inventory.db")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, class_=RecordingSession, autoflush=False)
        self.sessions = []
        self.producer = RecordingProducer(self.SessionLocal)

    def tearDown(self):
        self.engine.dispose()
        self.database_file.cleanup()

    def session_factory(self):
        db = self.SessionLocal()
        self.sessions.append(db)
        return db

    def seed(self, **stock):
        with self.SessionLocal.begin() as db:
            for product_id, quantity in stock.items():
                db.add(Product(product_id=product_id, name=product_id, price=1, stock=quantity))

    def created(self, order_id="order-1", **items):
        return OrderCreatedEvent(
            order_id=order_id, user_id="user-1", total_amount=1,
            correlation_id="correlation-1",
            items=[{"product_id": product_id, "quantity": quantity} for product_id, quantity in items.items()],
        )

    def handle(self, event):
        handle_inventory_event(event, self.session_factory, self.producer)
        self.assertTrue(self.sessions[-1].info["closed"])

    def state(self):
        with self.SessionLocal() as db:
            stock = {p.product_id: p.stock for p in db.query(Product).all()}
            reservations = [(r.order_id, r.product_id, r.quantity) for r in db.query(StockReservation).all()]
        return stock, reservations

    def topics(self):
        return [topic for topic, _ in self.producer.events]

    def test_single_item_success(self):
        self.seed(a=5)
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(self.topics().count("inventory.reserved"), 1)
        self.assertNotIn("inventory.depleted", self.topics())

    def test_single_item_insufficient(self):
        self.seed(a=1)
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 1}, []))
        self.assertEqual(self.topics(), ["inventory.depleted"])

    def test_multi_item_success(self):
        self.seed(a=5, b=4, c=3)
        self.handle(self.created(a=2, b=1, c=3))
        stock, reservations = self.state()
        self.assertEqual(stock, {"a": 3, "b": 3, "c": 0})
        self.assertCountEqual(reservations, [("order-1", "a", 2), ("order-1", "b", 1), ("order-1", "c", 3)])
        self.assertEqual(self.topics().count("inventory.reserved"), 1)
        reserved_event = next(event for topic, event in self.producer.events if topic == "inventory.reserved")
        self.assertEqual(reserved_event.items, [
            {"product_id": "a", "quantity": 2},
            {"product_id": "b", "quantity": 1},
            {"product_id": "c", "quantity": 3},
        ])

    def test_later_item_insufficient_rolls_back_all_items(self):
        self.seed(a=5, b=4, c=1)
        self.handle(self.created(a=2, b=1, c=3))
        self.assertEqual(self.state(), ({"a": 5, "b": 4, "c": 1}, []))
        self.assertEqual(self.topics(), ["inventory.depleted"])
        self.assertEqual(self.producer.events[0][1].product_id, "c")

    def test_payment_failure_releases_committed_reservations(self):
        self.seed(a=5, b=4)
        self.handle(self.created(a=2, b=1))
        self.handle(OrderCancelledEvent(
            order_id="order-1", user_id="user-1", reason="Payment failed",
            cancellation_source="payment_failed", correlation_id="correlation-1",
        ))
        self.assertEqual(self.state(), ({"a": 5, "b": 4}, []))

    def test_commit_failure_does_not_publish_success_and_closes_session(self):
        self.seed(a=5)
        with patch.object(RecordingSession, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                handle_inventory_event(self.created(a=2), self.session_factory, self.producer)
        self.assertTrue(self.sessions[-1].info["closed"])
        self.assertEqual(self.state(), ({"a": 5}, []))
        self.assertEqual(self.topics(), [])

    def test_unexpected_failure_after_first_item_rolls_back_and_closes(self):
        self.seed(a=5, b=5)
        reserve_stock = InventoryRepository.reserve_stock

        def fail_on_second_item(repo, order_id, product_id, quantity):
            if product_id == "b":
                raise RuntimeError("database error")
            return reserve_stock(repo, order_id, product_id, quantity)

        with patch.object(InventoryRepository, "reserve_stock", fail_on_second_item):
            with self.assertRaisesRegex(RuntimeError, "database error"):
                handle_inventory_event(self.created(a=2, b=2), self.session_factory, self.producer)
        self.assertTrue(self.sessions[-1].info["closed"])
        self.assertEqual(self.state(), ({"a": 5, "b": 5}, []))
        self.assertEqual(self.topics(), [])

    def test_concurrent_stale_reader_retries_without_overselling(self):
        self.seed(a=1)
        first = self.SessionLocal()
        second = self.SessionLocal()
        try:
            first_repo = InventoryRepository(first)
            second_repo = InventoryRepository(second)
            stale_product = first_repo.get_product("a")  # Version 0, stock 1.
            self.assertTrue(second_repo.reserve_stock("order-2", "a", 1))
            second.commit()
            real_get_product = first_repo.get_product
            reads = 0

            def stale_first_read(product_id):
                nonlocal reads
                reads += 1
                return stale_product if reads == 1 else real_get_product(product_id)

            with patch.object(first_repo, "get_product", side_effect=stale_first_read):
                self.assertFalse(first_repo.reserve_stock("order-1", "a", 1))
            self.assertEqual(reads, 2)  # Version conflict, then fresh stock check.
            first.rollback()
            self.assertEqual(self.state(), ({"a": 0}, [("order-2", "a", 1)]))
        finally:
            first.close()
            second.close()

    def test_payment_release_does_not_overwrite_a_concurrent_reservation(self):
        self.seed(a=5)
        with self.SessionLocal.begin() as db:
            self.assertTrue(InventoryRepository(db).reserve_stock("order-1", "a", 1))

        release_session = self.SessionLocal()
        try:
            release_repo = InventoryRepository(release_session)
            release_repo.get_product("a")  # Stock 4 cached before another order.
            with self.SessionLocal.begin() as db:
                self.assertTrue(InventoryRepository(db).reserve_stock("order-2", "a", 1))
            self.assertTrue(release_repo.release_stock("a", 1))
            release_session.commit()
            self.assertEqual(self.state()[0], {"a": 4})
        finally:
            release_session.close()


if __name__ == "__main__":
    unittest.main()
