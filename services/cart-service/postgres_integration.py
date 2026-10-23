"""Real PostgreSQL locks and Redis cleanup. Uses an isolated schema and user."""

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
import test_checkout as checkout_tests
from cart_repository import CartItem, CartRepository
from checkout import EmptyCart
from models import Base


class PostgresCheckoutTest(checkout_tests.CheckoutTest):
    def setUp(self):
        url = os.getenv("CART_TEST_POSTGRES_URL")
        if not url:
            self.skipTest("CART_TEST_POSTGRES_URL is not set")
        self.schema = f"checkout_test_{uuid4().hex[:12]}"
        self.user = self.schema
        self.admin_engine = create_engine(url)
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {self.schema}"))
        self.addCleanup(self.drop_schema)
        self.engine = create_engine(url, connect_args={"options": f"-csearch_path={self.schema}"})
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.redis = redis.Redis.from_url(os.getenv("CART_TEST_REDIS_URL", "redis://127.0.0.1:6379/0"),
                                         decode_responses=True, socket_timeout=5)
        self.redis.ping()
        self.addCleanup(self.redis.close)
        self.addCleanup(self.redis.delete, f"cart:{self.user}")
        self.repo = CartRepository(self.redis)
        self.prepare()

    def drop_schema(self):
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
        self.admin_engine.dispose()

    def tearDown(self):
        pass  # addCleanup also runs if setup fails.

    def parallel_checkout(self, keys):
        barrier = threading.Barrier(len(keys))

        def submit(key):
            barrier.wait(timeout=5)
            try:
                return self.service.submit(self.user, key)
            except EmptyCart:
                return None

        with ThreadPoolExecutor(max_workers=len(keys)) as pool:
            futures = [pool.submit(submit, key) for key in keys]
            return [future.result(timeout=15) for future in futures]

    def test_same_key_concurrent_requests_have_one_checkout(self):
        first, second = self.parallel_checkout(["key-1", "key-1"])
        self.assertEqual(first, second)
        self.assertEqual(self.rows(), 1)

    def test_headerless_concurrent_requests_have_one_checkout(self):
        first, second = self.parallel_checkout([None, None])
        self.assertEqual(first, second)
        self.assertEqual(self.rows(), 1)

    def test_different_keys_cannot_checkout_one_cart_twice(self):
        results = self.parallel_checkout(["key-1", "key-2"])
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self.rows(), 1)

    def test_new_cart_write_between_commit_and_cleanup_is_preserved(self):
        committed = threading.Event()
        resume_cleanup = threading.Event()
        cleanup = self.service.cleanup

        def delayed_cleanup(user_id):
            committed.set()
            if not resume_cleanup.wait(timeout=10):
                raise AssertionError("test cleanup was not released")
            cleanup(user_id)

        new_item = CartItem(product_id="new-product", quantity=1, price=5)
        with patch.object(self.service, "cleanup", side_effect=delayed_cleanup):
            with ThreadPoolExecutor(max_workers=2) as pool:
                checkout = pool.submit(self.service.submit, self.user, "key-1")
                try:
                    self.assertTrue(committed.wait(timeout=5))
                    mutation = pool.submit(self.service.cart_operation, self.user,
                                           lambda cart: cart.add_item(self.user, new_item))
                    mutation.result(timeout=5)
                finally:
                    resume_cleanup.set()
                checkout.result(timeout=10)
        items = self.repo.get_cart(self.user)["items"]
        self.assertEqual([(item["product_id"], item["quantity"]) for item in items], [("new-product", 1)])

    def test_concurrent_cart_additions_are_serialized(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.service.cart_operation, self.user,
                                   lambda cart: cart.add_item(self.user, self.item)) for _ in range(2)]
            for future in futures:
                future.result(timeout=10)
        self.assertEqual(self.repo.get_cart(self.user)["items"][0]["quantity"], 6)
