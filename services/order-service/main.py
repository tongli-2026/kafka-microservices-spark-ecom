"""
order-service/main.py - Order Management Microservice (Saga Orchestrator)

PURPOSE:
    Central orchestrator for the order processing workflow using Saga pattern.
    Coordinates distributed transactions across multiple services.

SAGA ORCHESTRATION:
    1. Listen for cart.checkout_initiated events
    2. Create order in PENDING state
    3. Wait for payment.processed event
    4. Update order to CONFIRMED or CANCELLED based on payment result
    5. Publish order.confirmed or order.cancelled events

RESPONSIBILITIES:
    - Create and manage orders
    - Orchestrate saga workflow (order → payment → inventory)
    - Handle compensation logic for failed transactions
    - Maintain order state consistency
    - Query order status and history

API ENDPOINTS:
    GET  /orders/{order_id} - Get order details
    GET  /orders/user/{user_id} - Get user's orders
    GET  /health - Health check

KAFKA EVENTS:
    CONSUMED:
        - cart.checkout_initiated: Triggers new order creation
        - payment.processed: Updates order based on payment result
    
    PUBLISHED:
        - order.created: New order created
        - order.confirmed: Payment successful, order confirmed
        - order.cancelled: Payment failed, order cancelled

DATABASE:
    - PostgreSQL table: orders
      Columns: order_id, user_id, status, total_amount, items, created_at, updated_at
    - PostgreSQL table: outbox_events (for reliable event publishing)

USAGE:
    Runs on port 8002 in Docker container
    Access: http://localhost:8002/orders/...
"""

import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI  # Web framework
from pydantic_settings import BaseSettings  # Configuration
from sqlalchemy import create_engine  # Database ORM
from sqlalchemy.orm import sessionmaker  # Database session management

# Add shared library to path for common utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Import shared Kafka and event utilities
from kafka_client import BaseKafkaConsumer, BaseKafkaProducer  # Kafka clients
from logging_config import setup_logging  # Centralized logging
from topic_initializer import create_topics  # Kafka topic creation

# Setup logging
setup_logging("order-service")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "kafka_ecom")
    order_service_port: int = int(os.getenv("ORDER_SERVICE_PORT", "8002"))


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
outbox_publisher = None


def init_db():
    """Initialize database tables."""
    from models import Base

    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle."""
    global producer, outbox_publisher

    logger.info("Starting Order Service...")

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
        producer = BaseKafkaProducer(settings.kafka_bootstrap_servers, client_id="order-producer")
        logger.info("Kafka producer initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        raise

    # Start outbox publisher
    from saga_handler import OutboxPublisher

    db = SessionLocal()
    outbox_publisher = OutboxPublisher(db, producer)
    outbox_publisher.start()
    logger.info("Outbox publisher started")

    # Start consumer thread for order events
    def order_event_consumer():
        """Consume order-related Kafka events."""
        from saga_handler import SagaHandler

        consumer = BaseKafkaConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="order-service-group",
            topics=[
                "cart.checkout_initiated",
                "payment.processed",
                "payment.failed",
                "inventory.reserved",
            ],
        )

        db_session = SessionLocal()

        def handle_event(event):
            """Handle incoming event based on type."""
            saga = SagaHandler(db_session, producer)

            if event.event_type == "cart.checkout_initiated":
                saga.handle_cart_checkout_initiated(event)
            elif event.event_type == "payment.processed":
                saga.handle_payment_processed(event)
            elif event.event_type == "payment.failed":
                saga.handle_payment_failed(event)
            elif event.event_type == "inventory.reserved":
                saga.handle_inventory_reserved(event)

        try:
            consumer.consume(handle_event)
        except Exception as e:
            logger.error(f"Error in order consumer: {e}")

    consumer_thread = threading.Thread(target=order_event_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Order consumer thread started")

    yield

    logger.info("Shutting down Order Service...")
    if outbox_publisher:
        outbox_publisher.stop()
    if producer:
        producer.flush()


app = FastAPI(title="Order Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "order-service",
        "version": "1.0.0",
    }


@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """Get order details."""
    from repository import OrderRepository

    try:
        db = SessionLocal()
        repo = OrderRepository(db)
        order = repo.get_order(order_id)

        if not order:
            return {"error": "Order not found"}, 404

        return {
            "order_id": order.order_id,
            "user_id": order.user_id,
            "status": order.status,
            "items": order.items,
            "total_amount": order.total_amount,
            "created_at": order.created_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting order: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.order_service_port)
