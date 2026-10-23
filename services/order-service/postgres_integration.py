"""Order saga state tests with PostgreSQL row locking."""

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from models import Base, Order, OutboxEvent
from saga_handler import SagaHandler
import test_saga_transitions as saga_tests
import test_order_outbox_fulfillment as outbox_tests
import test_checkout_identity as checkout_tests
from fulfillment import queue_fulfillment_events
from outbox import OutboxPublisher


class PostgresCheckoutIdentityTest(checkout_tests.CheckoutIdentityTest):
    def setUp(self):
        url = os.getenv("ORDER_TEST_POSTGRES_URL")
        if not url:
            self.skipTest("ORDER_TEST_POSTGRES_URL is not set")
        self.schema = f"order_checkout_test_{uuid4().hex[:12]}"
        self.admin_engine = create_engine(url)
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {self.schema}"))
        self.engine = create_engine(url, connect_args={"options": f"-csearch_path={self.schema}"})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
        self.admin_engine.dispose()

    def test_concurrent_different_event_ids_create_one_order(self):
        barrier = threading.Barrier(2)

        def handle(event_id):
            barrier.wait(timeout=5)
            self.handle(self.checkout_event(event_id=event_id))

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(handle, event_id) for event_id in ("event-a", "event-b")]
            for future in futures:
                future.result(timeout=10)
        self.assertEqual(self.counts(), (1, 1, 2))

    def test_migration_preserves_legacy_rows_and_is_repeatable(self):
        from migrations import migrate_checkout_identity

        self.handle(self.checkout_event(checkout_id=None))
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE orders DROP COLUMN checkout_id"))
        migrate_checkout_identity(self.engine)
        migrate_checkout_identity(self.engine)
        with self.SessionLocal() as db:
            self.assertIsNone(db.query(Order).one().checkout_id)
        self.handle(self.checkout_event(event_id="new-event"))
        self.assertEqual(self.counts(), (2, 2, 2))


class PostgresSagaTransitionsTest(saga_tests.SagaTransitionsTest):
    def setUp(self):
        url = os.getenv("ORDER_TEST_POSTGRES_URL")
        if not url:
            self.skipTest("ORDER_TEST_POSTGRES_URL is not set")
        self.schema = f"order_test_{uuid4().hex[:12]}"
        self.admin_engine = create_engine(url)
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {self.schema}"))
        self.engine = create_engine(url, connect_args={"options": f"-csearch_path={self.schema}"})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        with self.SessionLocal.begin() as db:
            db.add(Order(order_id="order-1", user_id="user-1", correlation_id="corr-1",
                         items=[{"product_id": "product-1", "quantity": 1}],
                         total_amount=10, status="PENDING"))

    def tearDown(self):
        self.engine.dispose()
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
        self.admin_engine.dispose()

    def test_conflicting_concurrent_payment_events_have_one_outcome(self):
        self.reserve()
        success = self.event("payment.processed", "success-1")
        failure = self.event("payment.failed", "failure-1", reason="declined")

        def apply(method, event):
            with self.SessionLocal() as db:
                getattr(SagaHandler(db), method)(event)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(apply, "handle_payment_processed", success),
                       pool.submit(apply, "handle_payment_failed", failure)]
            for future in futures:
                future.result(timeout=10)
        with self.SessionLocal() as db:
            status = db.query(Order).one().status
            topics = [row.event_type for row in db.query(OutboxEvent).all()]
        self.assertIn(status, ("PAID", "CANCELLED"))
        self.assertEqual(len(topics), 2)
        self.assertEqual(sum(topic in ("order.confirmed", "order.cancelled") for topic in topics), 1)


class PostgresOrderOutboxFulfillmentTest(outbox_tests.OrderOutboxFulfillmentTest):
    def setUp(self):
        url = os.getenv("ORDER_TEST_POSTGRES_URL")
        if not url:
            self.skipTest("ORDER_TEST_POSTGRES_URL is not set")
        self.schema = f"order_outbox_test_{uuid4().hex[:12]}"
        self.admin_engine = create_engine(url)
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {self.schema}"))
        self.engine = create_engine(url, connect_args={"options": f"-csearch_path={self.schema}"})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.now = datetime.now(ZoneInfo("America/Los_Angeles"))
        with self.SessionLocal.begin() as db:
            db.add(Order(
                order_id="order-1", user_id="user-1", correlation_id="corr-1",
                items=[{"product_id": "product-1", "quantity": 1}],
                total_amount=10, status="PAID", updated_at=self.now - timedelta(minutes=1),
            ))
        self.producer = outbox_tests.RecordingProducer()
        self.publisher = OutboxPublisher(self.SessionLocal, self.producer, poll_interval=0)

    def tearDown(self):
        self.engine.dispose()
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
        self.admin_engine.dispose()

    def test_two_workers_queue_one_fulfillment(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(queue_fulfillment_events, self.SessionLocal, 5, 10, self.now)
                       for _ in range(2)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sorted(results), [0, 1])
        with self.SessionLocal() as db:
            self.assertEqual(db.query(OutboxEvent).count(), 1)

    def test_two_publishers_do_not_send_same_claim_concurrently(self):
        self.queue()
        published = []
        guard = threading.Lock()

        class SlowProducer:
            def publish(self, topic, payload):
                time.sleep(0.2)
                with guard:
                    published.append((topic, payload["event_id"]))

        publisher_a = OutboxPublisher(self.SessionLocal, SlowProducer(), poll_interval=0)
        publisher_b = OutboxPublisher(self.SessionLocal, SlowProducer(), poll_interval=0)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(publisher.publish_once) for publisher in
                       (publisher_a, publisher_b)]
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(len(published), 1)

    def test_database_rejects_second_fulfillment_outbox_row(self):
        self.queue()
        with self.assertRaises(IntegrityError):
            with self.SessionLocal.begin() as db:
                db.add(OutboxEvent(order_id="order-1", event_type="order.fulfilled",
                                   event_data='{"event_id":"other","event_type":"order.fulfilled"}'))
