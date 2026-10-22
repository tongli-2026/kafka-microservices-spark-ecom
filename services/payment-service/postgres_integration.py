"""Run payment replay tests in isolated PostgreSQL schemas.

Set PAYMENT_TEST_POSTGRES_URL, then run:
python -m unittest discover -s services/payment-service -p postgres_integration.py -q
"""

import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent))

from models import Base
import test_payment_handler as payment_tests


class PostgresPaymentHandlerTest(payment_tests.PaymentHandlerTest):
    def setUp(self):
        url = os.getenv("PAYMENT_TEST_POSTGRES_URL")
        if not url:
            self.skipTest("PAYMENT_TEST_POSTGRES_URL is not set")

        self.schema = f"payment_test_{uuid4().hex[:12]}"
        self.admin_engine = create_engine(url)
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"CREATE SCHEMA {self.schema}"))
        self.engine = create_engine(url, connect_args={"options": f"-csearch_path={self.schema}"})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.producer = payment_tests.RecordingProducer(self.SessionLocal)
        self.event = payment_tests.OrderReservationConfirmedEvent(
            order_id="order-1", user_id="user-1", total_amount=10,
            correlation_id="correlation-1",
        )

    def tearDown(self):
        self.engine.dispose()
        with self.admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA {self.schema} CASCADE"))
        self.admin_engine.dispose()
