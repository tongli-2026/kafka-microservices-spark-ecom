"""Database-backed inventory saga tests; Kafka is replaced with a recording producer."""

import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from events import OrderCancelledEvent, OrderCreatedEvent
from main import handle_inventory_event
from models import Base, InventoryOrder, Product, StockReservation
from repository import InventoryRepository, backfill_legacy_orders


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
        self.engine = create_engine(f"sqlite:///{self.database_file.name}/inventory.db", connect_args={"timeout": 10})
        # SQLite's default driver does not BEGIN before SAVEPOINT. Explicitly
        # start the outer transaction so rollback tests match PostgreSQL.
        @event.listens_for(self.engine, "connect")
        def disable_driver_transactions(connection, _):
            connection.isolation_level = None

        @event.listens_for(self.engine, "begin")
        def begin_transaction(connection):
            connection.exec_driver_sql("BEGIN")

        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, class_=RecordingSession, autoflush=False, expire_on_commit=False)
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

    def cancelled(self, order_id="order-1", source="payment_failed"):
        return OrderCancelledEvent(
            order_id=order_id, user_id="user-1", reason="Cancelled",
            cancellation_source=source, correlation_id="correlation-1",
        )

    def handle(self, event):
        sessions = []

        def factory():
            db = self.session_factory()
            sessions.append(db)
            return db

        handle_inventory_event(event, factory, self.producer)
        self.assertTrue(sessions[0].info["closed"])

    def state(self):
        with self.SessionLocal() as db:
            stock = {p.product_id: p.stock for p in db.query(Product).all()}
            reservations = [(r.order_id, r.product_id, r.quantity) for r in db.query(StockReservation).all()]
        return stock, reservations

    def topics(self):
        return [topic for topic, _ in self.producer.events]

    def order_state(self, order_id="order-1"):
        with self.SessionLocal() as db:
            order = db.get(InventoryOrder, order_id)
            if order is None:
                return None
            return order.status, order.items_json, order.result_event_id, order.failed_product_id

    def test_single_item_success(self):
        self.seed(a=5)
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(self.order_state()[0], "RESERVED")
        self.assertEqual(self.topics().count("inventory.reserved"), 1)
        self.assertNotIn("inventory.depleted", self.topics())

    def test_single_item_insufficient(self):
        self.seed(a=1)
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 1}, []))
        self.assertEqual(self.order_state()[0], "DEPLETED")
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
        self.assertEqual(self.order_state()[0], "DEPLETED")
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
        self.assertEqual(self.order_state()[0], "RELEASED")

    def test_commit_failure_does_not_publish_success_and_closes_session(self):
        self.seed(a=5)
        with patch.object(RecordingSession, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                handle_inventory_event(self.created(a=2), self.session_factory, self.producer)
        self.assertTrue(self.sessions[-1].info["closed"])
        self.assertEqual(self.state(), ({"a": 5}, []))
        self.assertIsNone(self.order_state())
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
        self.assertIsNone(self.order_state())
        self.assertEqual(self.topics(), [])

    def test_concurrent_stale_reader_retries_without_overselling(self):
        self.seed(a=1)
        first = self.SessionLocal()
        second = self.SessionLocal()
        try:
            first_repo = InventoryRepository(first)
            second_repo = InventoryRepository(second)
            stale_product = first_repo.get_product("a")  # Version 0, stock 1.
            first.commit()  # End SQLite's read transaction; retain the cached object.
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
            release_session.commit()  # Let SQLite's next writer proceed.
            with self.SessionLocal.begin() as db:
                self.assertTrue(InventoryRepository(db).reserve_stock("order-2", "a", 1))
            self.assertTrue(release_repo.release_stock("a", 1))
            release_session.commit()
            self.assertEqual(self.state()[0], {"a": 4})
        finally:
            release_session.close()

    def test_exact_redelivery_and_new_session_replay_same_result(self):
        self.seed(a=5)
        message = self.created(a=2)
        self.handle(message)
        self.handle(message)
        # Every call makes a new SQLAlchemy session, like a restarted consumer.
        self.assertEqual(len(self.sessions), 2)
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(self.order_state()[0], "RESERVED")
        events = [event for topic, event in self.producer.events if topic == "inventory.reserved"]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event_id, events[1].event_id)

    def test_different_event_id_same_order_does_not_reserve_again(self):
        self.seed(a=5)
        self.handle(self.created(a=2))
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        ids = [event.event_id for topic, event in self.producer.events if topic == "inventory.reserved"]
        self.assertEqual(len(set(ids)), 1)

    def test_multi_item_replay_accepts_reordered_lines_without_extra_records(self):
        self.seed(a=5, b=4)
        self.handle(self.created(a=2, b=1))
        self.handle(self.created(b=1, a=2))
        self.assertCountEqual(self.state()[1], [("order-1", "a", 2), ("order-1", "b", 1)])
        self.assertEqual(self.state()[0], {"a": 3, "b": 3})
        events = [event for topic, event in self.producer.events if topic == "inventory.reserved"]
        self.assertEqual(events[0].event_id, events[1].event_id)
        self.assertEqual(events[0].items, events[1].items)

    def test_conflicting_order_items_raise_without_changing_stock(self):
        self.seed(a=5)
        self.handle(self.created(a=2))
        with self.assertRaisesRegex(ValueError, "Conflicting items"):
            self.handle(self.created(a=3))
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(self.topics().count("inventory.reserved"), 1)

    def test_rejected_order_stays_rejected_after_restock(self):
        self.seed(a=1)
        self.handle(self.created(a=2))
        first_id = self.producer.events[0][1].event_id
        self.handle(self.cancelled(source="inventory_depleted"))
        with self.SessionLocal.begin() as db:
            db.query(Product).filter_by(product_id="a").update({"stock": 5})
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 5}, []))
        self.assertEqual(self.order_state()[0], "DEPLETED")
        self.assertEqual(self.topics(), ["inventory.depleted", "inventory.depleted"])
        self.assertEqual(self.producer.events[-1][1].event_id, first_id)

    def test_duplicate_cancellation_and_old_created_event_after_release(self):
        self.seed(a=5)
        self.handle(self.created(a=2))
        self.handle(self.cancelled())
        self.handle(self.cancelled())
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 5}, []))
        self.assertEqual(self.order_state()[0], "RELEASED")
        self.assertEqual(self.topics().count("inventory.reserved"), 1)

    def test_cancellation_before_creation_blocks_stale_creation(self):
        self.seed(a=5)
        self.handle(self.cancelled())
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 5}, []))
        self.assertEqual(self.order_state()[0], "CANCELLED")
        self.assertEqual(self.topics(), [])
        with self.assertRaisesRegex(ValueError, "Conflicting items"):
            self.handle(self.created(a=3))
        self.assertEqual(self.state(), ({"a": 5}, []))

    def test_result_publish_failure_replays_stable_event_id(self):
        self.seed(a=5)
        message = self.created(a=2)

        class FailOnceProducer(RecordingProducer):
            def __init__(self, session_factory):
                super().__init__(session_factory)
                self.failed_event = None

            def publish(self, topic, event):
                if topic == "inventory.reserved" and self.failed_event is None:
                    self.failed_event = event
                    raise RuntimeError("Kafka unavailable")
                super().publish(topic, event)

        flaky = FailOnceProducer(self.SessionLocal)
        with self.assertRaisesRegex(RuntimeError, "Kafka unavailable"):
            handle_inventory_event(message, self.session_factory, flaky)
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(self.order_state()[0], "RESERVED")

        handle_inventory_event(message, self.session_factory, flaky)
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(flaky.events[0][1].event_id, flaky.failed_event.event_id)

    def test_concurrent_same_order_claims_only_one_reservation(self):
        self.seed(a=5)
        start = threading.Barrier(2)

        def process(event):
            start.wait(timeout=5)
            self.handle(event)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(process, self.created(a=2)) for _ in range(2)]
            for result in results:
                result.result(timeout=15)
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(self.order_state()[0], "RESERVED")
        events = [event for topic, event in self.producer.events if topic == "inventory.reserved"]
        self.assertEqual(len(events), 2)
        self.assertEqual(len({event.event_id for event in events}), 1)

    def test_concurrent_conflicting_order_payload_is_rejected(self):
        self.seed(a=5)
        start = threading.Barrier(2)

        def process(event):
            start.wait(timeout=5)
            handle_inventory_event(event, self.session_factory, self.producer)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(process, self.created(a=quantity)) for quantity in (2, 3)]
            errors = []
            for result in results:
                try:
                    result.result(timeout=15)
                except ValueError as error:
                    errors.append(error)
        self.assertEqual(len(errors), 1)
        self.assertIn("Conflicting items", str(errors[0]))
        stock, reservations = self.state()
        self.assertEqual(len(reservations), 1)
        self.assertEqual(stock["a"], 5 - reservations[0][2])
        self.assertEqual(self.topics().count("inventory.reserved"), 1)

    def test_two_orders_compete_for_limited_inventory(self):
        self.seed(a=1)
        start = threading.Barrier(2)

        def process(event):
            start.wait(timeout=5)
            self.handle(event)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(process, self.created(order_id=f"order-{i}", a=1)) for i in (1, 2)]
            for result in results:
                result.result(timeout=15)
        stock, reservations = self.state()
        self.assertEqual(stock, {"a": 0})
        self.assertEqual(len(reservations), 1)
        self.assertCountEqual(self.topics(), ["inventory.reserved", "inventory.depleted", "inventory.low"])
        self.assertCountEqual(
            [self.order_state("order-1")[0], self.order_state("order-2")[0]],
            ["RESERVED", "DEPLETED"],
        )

    def test_backfill_preserves_existing_active_reservation(self):
        self.seed(a=3)
        with self.SessionLocal.begin() as db:
            db.add(StockReservation(order_id="legacy", product_id="a", quantity=2))
        # Simulate an old database that has the existing tables but no status table.
        InventoryOrder.__table__.drop(self.engine)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal.begin() as db:
            self.assertEqual(backfill_legacy_orders(db), 1)
        self.assertEqual(self.order_state("legacy")[0], "RESERVED")
        self.assertIsNone(self.order_state("legacy")[2])
        self.handle(self.created(order_id="legacy", a=2))
        self.assertEqual(self.state(), ({"a": 3}, [("legacy", "a", 2)]))
        self.assertEqual(self.topics(), [])


if __name__ == "__main__":
    unittest.main()
