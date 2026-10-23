"""Run notification row-lock tests in isolated PostgreSQL schemas."""

import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))

from delivery import NotificationDeliveryService
from models import Base
import test_delivery as delivery_tests


class PostgresNotificationDeliveryTest(delivery_tests.NotificationDeliveryTest):
    def setUp(self):
        url = os.getenv("NOTIFICATION_TEST_POSTGRES_URL")
        if not url:
            self.skipTest("NOTIFICATION_TEST_POSTGRES_URL is not set")
        self.schema = f"notification_test_{uuid4().hex[:12]}"
        self.admin_engine = create_engine(url)
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {self.schema}"))
        self.engine = create_engine(url, connect_args={"options": f"-csearch_path={self.schema}"})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.delivery = NotificationDeliveryService(self.SessionLocal)
        self.event = delivery_tests.SimpleNamespace(event_id="event-1", event_type="order.confirmed")

    def tearDown(self):
        self.engine.dispose()
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
        self.admin_engine.dispose()
