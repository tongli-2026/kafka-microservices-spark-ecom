"""
payment-service/main.py - Payment Processing Microservice

PURPOSE:
    Handles payment processing for e-commerce orders with simulated
    payment gateway integration. Supports success/failure scenarios.

PAYMENT FLOW:
    1. Listen for order.created events from Order Service
    2. Simulate payment processing (80% success, 20% failure)
    3. Record payment transaction in database
    4. Publish payment.processed event with result
    5. Order Service reacts to payment result

RESPONSIBILITIES:
    - Process payment transactions
    - Simulate payment gateway integration
    - Handle payment retries and failures
    - Record payment history
    - Publish payment result events

SIMULATION:
    - 80% chance of successful payment
    - 20% chance of payment failure (for testing saga compensation)
    - Random amount validation
    - Idempotency: Prevents duplicate payments for same order

API ENDPOINTS:
    GET /payments/{payment_id} - Get payment details
    GET /payments/order/{order_id} - Get payments for order
    GET /health - Health check

KAFKA EVENTS:
    CONSUMED:
        - order.created: Triggers payment processing
    
    PUBLISHED:
        - payment.processed: Payment succeeded or failed
        - payment.failed: Payment explicitly failed (alternative event)

DATABASE:
    - PostgreSQL table: payments
      Columns: payment_id, order_id, amount, status, 
               payment_method, transaction_id, created_at

USAGE:
    Runs on port 8003 in Docker container
    Access: http://localhost:8003/payments/...
"""

import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI  # Web framework
from pydantic_settings import BaseSettings  # Configuration management
from sqlalchemy import create_engine  # Database ORM
from sqlalchemy.orm import sessionmaker  # Database session management

# Add shared library to path for common utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Import shared Kafka and event utilities
from kafka_client import BaseKafkaConsumer, BaseKafkaProducer  # Kafka clients
from logging_config import setup_logging  # Centralized logging
from topic_initializer import create_topics  # Kafka topic creation
from events import PaymentProcessedEvent, PaymentFailedEvent  # Event schemas

# Setup logging
setup_logging("payment-service")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "kafka_ecom")
    payment_service_port: int = int(os.getenv("PAYMENT_SERVICE_PORT", "8003"))


settings = Settings()

# Database setup
DATABASE_URL = (
    f"postgresql://{settings.postgres_user}:{settings.postgres_password}@"
    f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Global instances
producer: BaseKafkaProducer = None


def init_db():
    """Initialize database tables."""
    from models import Base

    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle."""
    global producer

    logger.info("Starting Payment Service...")

    # Initialize database
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Initialize Kafka topics
    try:
        create_topics(settings.kafka_bootstrap_servers)
        logger.info("Kafka topics initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka topics: {e}")
        raise

    # Initialize Kafka producer
    try:
        producer = BaseKafkaProducer(settings.kafka_bootstrap_servers, client_id="payment-producer")
        logger.info("Kafka producer initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        raise

    # Start consumer thread for order.created events
    def payment_consumer():
        """Consume order.created events and process payments."""
        from payment_processor import PaymentProcessor
        from repository import PaymentRepository

        consumer = BaseKafkaConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="payment-service-group",
            topics=["order.created"],
        )

        def handle_order_created(event):
            """Handle order.created event."""
            logger.info(
                f"Processing payment for order {event.order_id}",
                extra={"event_type": event.event_type, "correlation_id": event.correlation_id},
            )

            db = SessionLocal()
            repo = PaymentRepository(db)

            # Process payment
            success, reason = PaymentProcessor.process_payment(event.total_amount)

            if success:
                # Create success payment record
                payment = repo.create_payment(
                    order_id=event.order_id,
                    user_id=event.user_id,
                    amount=event.total_amount,
                    currency="USD",
                    method="card",
                    status="SUCCESS",
                )

                # Publish payment.processed event
                payment_event = PaymentProcessedEvent(
                    payment_id=payment.payment_id,
                    order_id=event.order_id,
                    user_id=event.user_id,
                    amount=event.total_amount,
                    currency="USD",
                    method="card",
                    correlation_id=event.correlation_id,
                )
                producer.publish("payment.processed", payment_event)

            else:
                # Create failed payment record
                payment = repo.create_payment(
                    order_id=event.order_id,
                    user_id=event.user_id,
                    amount=event.total_amount,
                    currency="USD",
                    method="card",
                    status="FAILED",
                    reason=reason,
                )

                # Publish payment.failed event
                payment_event = PaymentFailedEvent(
                    order_id=event.order_id,
                    user_id=event.user_id,
                    reason=reason,
                    correlation_id=event.correlation_id,
                )
                producer.publish("payment.failed", payment_event)

            db.commit()
            db.close()

        try:
            consumer.consume(handle_order_created)
        except Exception as e:
            logger.error(f"Error in payment consumer: {e}")

    consumer_thread = threading.Thread(target=payment_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Payment consumer thread started")

    yield

    logger.info("Shutting down Payment Service...")
    if producer:
        producer.flush()


app = FastAPI(title="Payment Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "payment-service",
        "version": "1.0.0",
    }


@app.get("/payments/{payment_id}")
async def get_payment(payment_id: str):
    """Get payment details."""
    from repository import PaymentRepository

    try:
        db = SessionLocal()
        repo = PaymentRepository(db)
        payment = repo.get_payment(payment_id)

        if not payment:
            return {"error": "Payment not found"}, 404

        return {
            "payment_id": payment.payment_id,
            "order_id": payment.order_id,
            "user_id": payment.user_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "method": payment.method,
            "status": payment.status,
            "reason": payment.reason,
            "created_at": payment.created_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting payment: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.payment_service_port)
