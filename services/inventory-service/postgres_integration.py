"""Run the inventory transaction suite against an isolated PostgreSQL schema.

Set INVENTORY_TEST_POSTGRES_URL to a dedicated test server/database URL, then run:
python -m unittest discover -s services/inventory-service -p postgres_integration.py -q
"""

import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))

from models import Base
import test_inventory_transactions as inventory_tests


class PostgresInventoryTransactionsTest(inventory_tests.InventoryTransactionsTest):
    def setUp(self):
        url = os.getenv("INVENTORY_TEST_POSTGRES_URL")
        if not url:
            self.skipTest("INVENTORY_TEST_POSTGRES_URL is not set")

        self.schema = f"inventory_test_{uuid4().hex[:12]}"
        self.admin_engine = create_engine(url)
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {self.schema}"))

        self.engine = create_engine(url, connect_args={"options": f"-csearch_path={self.schema}"})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(
            bind=self.engine, class_=inventory_tests.RecordingSession,
            autoflush=False, expire_on_commit=False,
        )
        self.sessions = []
        self.producer = inventory_tests.RecordingProducer(self.SessionLocal)

    def tearDown(self):
        self.engine.dispose()
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
        self.admin_engine.dispose()
