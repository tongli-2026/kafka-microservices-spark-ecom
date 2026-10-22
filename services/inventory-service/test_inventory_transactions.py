"""Database-backed inventory saga tests; Kafka is replaced with a recording producer."""

import json
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from events import OrderCancelledEvent, OrderCreatedEvent
from kafka_client import KafkaDeliveryError
from main import handle_inventory_event
from models import Base, InventoryOrder, InventoryOutboxEvent, Product, StockReservation
from outbox import InventoryOutboxPublisher, backfill_result_outbox
from repository import InventoryRepository, backfill_legacy_orders
from seed_data import seed_products


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
                order = db.get(InventoryOrder, event["order_id"])
                assert order.status in ("RESERVED", "RELEASED")
                if order.status == "RESERVED":
                    assert db.query(StockReservation).filter_by(order_id=event["order_id"]).count() == len(event["items"])
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
        self.publisher = InventoryOutboxPublisher(self.SessionLocal, self.producer, poll_interval=0, lease_seconds=60)

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
        self.publish_pending()
        return [topic for topic, _ in self.producer.events]

    def publish_pending(self):
        for _ in range(10):
            if not self.publisher.publish_once():
                return
        self.fail("Outbox did not drain")

    def outbox_rows(self):
        with self.SessionLocal() as db:
            return db.query(InventoryOutboxEvent).all()

    def order_state(self, order_id="order-1"):
        with self.SessionLocal() as db:
            order = db.get(InventoryOrder, order_id)
            if order is None:
                return None
            return order.status, order.items_json, order.result_event_id, order.failed_product_id

    def test_single_item_success(self):
        self.seed(a=5)
        self.handle(self.created(a=2))
        self.assertNotIn("inventory.reserved", [topic for topic, _ in self.producer.events])
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(self.order_state()[0], "RESERVED")
        self.assertEqual(self.topics().count("inventory.reserved"), 1)
        self.assertEqual(len(self.outbox_rows()), 1)
        self.assertNotIn("inventory.depleted", self.topics())

    def test_single_item_insufficient(self):
        self.seed(a=1)
        self.handle(self.created(a=2))
        self.assertEqual(self.producer.events, [])
        self.assertEqual(self.state(), ({"a": 1}, []))
        self.assertEqual(self.order_state()[0], "DEPLETED")
        self.assertEqual(self.topics(), ["inventory.depleted"])
        self.assertEqual(len(self.outbox_rows()), 1)

    def test_multi_item_success(self):
        self.seed(a=5, b=4, c=3)
        self.handle(self.created(a=2, b=1, c=3))
        stock, reservations = self.state()
        self.assertEqual(stock, {"a": 3, "b": 3, "c": 0})
        self.assertCountEqual(reservations, [("order-1", "a", 2), ("order-1", "b", 1), ("order-1", "c", 3)])
        self.assertEqual(self.topics().count("inventory.reserved"), 1)
        reserved_event = next(event for topic, event in self.producer.events if topic == "inventory.reserved")
        self.assertEqual(reserved_event["items"], [
            {"product_id": "a", "quantity": 2},
            {"product_id": "b", "quantity": 1},
            {"product_id": "c", "quantity": 3},
        ])
        row = self.outbox_rows()[0]
        self.assertEqual(row.order_id, "order-1")
        self.assertEqual(row.event_type, "inventory.reserved")
        self.assertEqual(row.event_id, self.order_state()[2])
        self.assertEqual(json.loads(row.event_data), reserved_event)
        self.assertTrue(row.published)

    def test_later_item_insufficient_rolls_back_all_items(self):
        self.seed(a=5, b=4, c=1)
        self.handle(self.created(a=2, b=1, c=3))
        self.assertEqual(self.state(), ({"a": 5, "b": 4, "c": 1}, []))
        self.assertEqual(self.order_state()[0], "DEPLETED")
        self.assertEqual(self.topics(), ["inventory.depleted"])
        self.assertEqual(self.producer.events[0][1]["product_id"], "c")
        row = self.outbox_rows()[0]
        self.assertEqual(row.event_type, "inventory.depleted")
        self.assertEqual(row.event_id, self.order_state()[2])
        self.assertEqual(json.loads(row.event_data), self.producer.events[0][1])

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
        self.assertEqual(self.outbox_rows(), [])

    def test_depleted_commit_failure_leaves_no_order_or_outbox(self):
        self.seed(a=1)
        with patch.object(RecordingSession, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                handle_inventory_event(self.created(a=2), self.session_factory, self.producer)
        self.assertEqual(self.state(), ({"a": 1}, []))
        self.assertIsNone(self.order_state())
        self.assertEqual(self.outbox_rows(), [])
        self.assertEqual(self.producer.events, [])

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
        self.assertEqual(self.outbox_rows(), [])

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
        self.publish_pending()
        events = [event for topic, event in self.producer.events if topic == "inventory.reserved"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], self.order_state()[2])
        self.assertEqual(len(self.outbox_rows()), 1)

    def test_different_event_id_same_order_does_not_reserve_again(self):
        self.seed(a=5)
        self.handle(self.created(a=2))
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(len(self.outbox_rows()), 1)
        self.assertEqual(self.outbox_rows()[0].event_id, self.order_state()[2])

    def test_multi_item_replay_accepts_reordered_lines_without_extra_records(self):
        self.seed(a=5, b=4)
        self.handle(self.created(a=2, b=1))
        self.handle(self.created(b=1, a=2))
        self.assertCountEqual(self.state()[1], [("order-1", "a", 2), ("order-1", "b", 1)])
        self.assertEqual(self.state()[0], {"a": 3, "b": 3})
        self.publish_pending()
        events = [event for topic, event in self.producer.events if topic == "inventory.reserved"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], self.order_state()[2])
        self.assertEqual(len(self.outbox_rows()), 1)

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
        first_id = self.order_state()[2]
        self.handle(self.cancelled(source="inventory_depleted"))
        with self.SessionLocal.begin() as db:
            db.query(Product).filter_by(product_id="a").update({"stock": 5})
        self.handle(self.created(a=2))
        self.assertEqual(self.state(), ({"a": 5}, []))
        self.assertEqual(self.order_state()[0], "DEPLETED")
        self.assertEqual(self.topics(), ["inventory.depleted"])
        self.assertEqual(self.outbox_rows()[0].event_id, first_id)

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

    def test_result_publish_failure_retries_stable_event_id(self):
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
        handle_inventory_event(message, self.session_factory, flaky)
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(self.order_state()[0], "RESERVED")
        publisher = InventoryOutboxPublisher(self.SessionLocal, flaky, poll_interval=0)
        self.assertTrue(publisher.publish_once())
        self.assertFalse(self.outbox_rows()[0].published)
        self.assertTrue(publisher.publish_once())
        self.assertTrue(self.outbox_rows()[0].published)
        delivered = next(event for topic, event in flaky.events if topic == "inventory.reserved")
        self.assertEqual(delivered["event_id"], flaky.failed_event["event_id"])

    def test_negative_ack_and_timeout_leave_row_pending(self):
        self.seed(a=20)
        self.handle(self.created(a=2))

        class FailingProducer:
            def __init__(self, error):
                self.error = error

            def publish(self, _topic, _event):
                raise self.error

        for error in (KafkaDeliveryError("negative acknowledgment"), KafkaDeliveryError("delivery timeout")):
            with self.subTest(error=str(error)):
                publisher = InventoryOutboxPublisher(
                    self.SessionLocal, FailingProducer(error), poll_interval=0,
                )
                self.assertTrue(publisher.publish_once())
                row = self.outbox_rows()[0]
                self.assertFalse(row.published)
                self.assertIn(str(error), row.last_error)
        self.assertEqual(self.outbox_rows()[0].attempts, 2)
        self.assertTrue(self.publisher.publish_once())
        self.assertTrue(self.outbox_rows()[0].published)

    def test_commit_without_publisher_recovers_after_restart(self):
        self.seed(a=5)
        self.handle(self.created(a=2))
        self.assertEqual(self.producer.events[0][0], "inventory.low")
        row = self.outbox_rows()[0]
        self.assertFalse(row.published)
        original = row.event_data

        restarted = InventoryOutboxPublisher(self.SessionLocal, self.producer)
        self.assertTrue(restarted.publish_once())
        self.assertEqual(self.outbox_rows()[0].event_data, original)
        self.assertTrue(self.outbox_rows()[0].published)
        self.assertEqual(self.topics().count("inventory.reserved"), 1)

    def test_crash_after_ack_retries_same_payload_after_lease_expires(self):
        self.seed(a=20)
        self.handle(self.created(a=2))
        original = self.outbox_rows()[0].event_data
        publisher = InventoryOutboxPublisher(self.SessionLocal, self.producer, poll_interval=0)
        with patch.object(publisher, "_mark_published", side_effect=RuntimeError("database down")), patch.object(
            publisher, "_record_failure", side_effect=RuntimeError("process stopped")
        ):
            self.assertTrue(publisher.publish_once())
        self.assertFalse(self.outbox_rows()[0].published)
        with self.SessionLocal.begin() as db:
            row = db.query(InventoryOutboxEvent).one()
            now = db.execute(select(func.now())).scalar_one()
            row.claimed_until = now - timedelta(seconds=1)

        restarted = InventoryOutboxPublisher(self.SessionLocal, self.producer)
        self.assertTrue(restarted.publish_once())
        deliveries = [payload for topic, payload in self.producer.events if topic == "inventory.reserved"]
        self.assertEqual(len(deliveries), 2)
        self.assertEqual(deliveries[0], deliveries[1])
        self.assertEqual(deliveries[0], json.loads(original))
        self.assertTrue(self.outbox_rows()[0].published)

    def test_abandoned_claim_recovers_after_restart(self):
        self.seed(a=20)
        self.handle(self.created(a=1))
        claimed = self.publisher._claim_next()
        self.assertIsNotNone(claimed)
        self.assertFalse(self.publisher.publish_once())
        with self.SessionLocal.begin() as db:
            row = db.query(InventoryOutboxEvent).one()
            now = db.execute(select(func.now())).scalar_one()
            row.claimed_until = now - timedelta(seconds=1)
        restarted = InventoryOutboxPublisher(self.SessionLocal, self.producer)
        self.assertTrue(restarted.publish_once())
        self.assertTrue(self.outbox_rows()[0].published)

    def test_low_alert_failure_does_not_retry_reservation(self):
        self.seed(a=5)
        class LowAlertFailure(RecordingProducer):
            def publish(self, topic, event):
                if topic == "inventory.low":
                    raise RuntimeError("alert unavailable")
                super().publish(topic, event)

        producer = LowAlertFailure(self.SessionLocal)
        message = self.created(a=2)
        handle_inventory_event(message, self.session_factory, producer)
        handle_inventory_event(message, self.session_factory, producer)
        self.assertEqual(self.state(), ({"a": 3}, [("order-1", "a", 2)]))
        self.assertEqual(len(self.outbox_rows()), 1)
        self.assertTrue(InventoryOutboxPublisher(self.SessionLocal, producer).publish_once())

    def test_startup_backfill_queues_existing_result_once(self):
        self.seed(a=20)
        self.handle(self.created(a=2))
        with self.SessionLocal.begin() as db:
            db.query(InventoryOutboxEvent).delete()
        with self.SessionLocal.begin() as db:
            self.assertEqual(backfill_result_outbox(db), 1)
        with self.SessionLocal.begin() as db:
            self.assertEqual(backfill_result_outbox(db), 0)
        self.assertEqual(len(self.outbox_rows()), 1)
        self.assertEqual(self.outbox_rows()[0].event_id, self.order_state()[2])

    def test_two_publishers_claim_one_row_only(self):
        if self.engine.dialect.name != "postgresql":
            self.skipTest("FOR UPDATE SKIP LOCKED requires PostgreSQL")
        self.seed(a=20)
        self.handle(self.created(a=1))
        publishing = threading.Event()
        release = threading.Event()

        class BlockingProducer(RecordingProducer):
            def publish(self, topic, event):
                publishing.set()
                self.assert_release()
                super().publish(topic, event)

            def assert_release(self):
                assert release.wait(timeout=5)

        blocker = BlockingProducer(self.SessionLocal)
        first = InventoryOutboxPublisher(self.SessionLocal, blocker)
        second = InventoryOutboxPublisher(self.SessionLocal, self.producer)
        with ThreadPoolExecutor(max_workers=2) as pool:
            sent = pool.submit(first.publish_once)
            self.assertTrue(publishing.wait(timeout=5))
            self.assertFalse(second.publish_once())
            release.set()
            self.assertTrue(sent.result(timeout=10))
        self.assertEqual(len([topic for topic, _ in blocker.events if topic == "inventory.reserved"]), 1)
        self.assertEqual(len([topic for topic, _ in self.producer.events if topic == "inventory.reserved"]), 0)
        self.assertTrue(self.outbox_rows()[0].published)

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
        self.publish_pending()
        events = [event for topic, event in self.producer.events if topic == "inventory.reserved"]
        self.assertEqual(len(events), 1)
        self.assertEqual(len(self.outbox_rows()), 1)

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

    def test_restarting_seed_preserves_existing_catalog_and_stock(self):
        with self.SessionLocal.begin() as db:
            db.add(Product(product_id="original", name="Wireless Headphones", price=149.99, stock=3))
        with self.SessionLocal() as db:
            seed_products(db)
        with self.SessionLocal() as db:
            first_count = db.query(Product).count()
            self.assertEqual(db.query(Product).filter_by(product_id="original").one().stock, 3)
            seed_products(db)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(Product).count(), first_count)
            self.assertEqual(db.query(Product).filter_by(product_id="original").one().stock, 3)


if __name__ == "__main__":
    unittest.main()
