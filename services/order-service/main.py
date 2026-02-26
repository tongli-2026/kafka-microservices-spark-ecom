"""
order-service/main.py - Order Management Microservice (Saga Orchestrator)

PURPOSE:
    Central orchestrator for the order processing workflow using Saga pattern.
    Implements production-style inventory-first validation before payment processing.
    Coordinates distributed transactions across multiple services.

SAGA ORCHESTRATION (production-style: Inventory First):
    1. Listen for cart.checkout_initiated events
    2. Create order in PENDING state, publish order.created
    3. Inventory Service receives order.created → attempts stock reservation
    4. Receive inventory.reserved event → update order to RESERVATION_CONFIRMED
    5. Publish order.reservation_confirmed → triggers Payment Service
    6. Payment Service processes payment, publishes payment.processed or payment.failed
    7. Update order to CONFIRMED (paid) or CANCELLED (payment failed)
    8. Publish order.confirmed or order.cancelled events

KEY ADVANTAGE:
    - No charges if inventory is out of stock (no refunds needed)
    - Matches production e-commerce patterns (Amazon, Shopify, etc.)
    - Better customer experience and reduced support costs

RESPONSIBILITIES:
    - Create and manage orders
    - Orchestrate saga workflow with inventory priority
    - Handle compensation logic for failed transactions
    - Maintain order state consistency (successful: PENDING → RESERVATION_CONFIRMED → PAID → FULFILLED, failed: PENDING → CANCELLED or PENDING → RESERVATION_CONFIRMED → CANCELLED)
    - Query order status and history
    - Reliable event publishing via Outbox Pattern
    - Run background fulfillment job to automatically mark PAID orders as FULFILLED

BACKGROUND JOBS:
    - Fulfillment Job: Runs as background thread
      * Polls database every 10 seconds (configurable via POLL_INTERVAL_SECONDS)
      * Finds PAID orders ready for fulfillment (older than 5 seconds, configurable via FULFILLMENT_DELAY_SECONDS)
      * Publishes order.fulfilled events to Kafka
      * Generates tracking numbers for shipped orders

API ENDPOINTS:
    GET  /health - Health check
    GET  /orders/{order_id} - Get order details
    GET  /orders/user/{user_id} - Get user's orders

KAFKA EVENTS:
    CONSUMED:
        - cart.checkout_initiated: Triggers new order creation
        - inventory.reserved: Updates order to RESERVATION_CONFIRMED
        - inventory.depleted: Cancels order if stock unavailable (PENDING → CANCELLED)
        - payment.processed: Updates order to PAID
        - payment.failed: Updates order to CANCELLED
        - order.fulfilled: Updates order to FULFILLED (from fulfillment job)
    
    PUBLISHED (via Outbox Pattern):
        - order.created: New order created, triggers inventory reservation
        - order.reservation_confirmed: Stock reserved, triggers payment processing
        - order.confirmed: Payment successful, order confirmed
        - order.cancelled: Order cancelled (payment failed or out of stock)
        - order.fulfilled: Publishes when order is fulfilled (background job)

DATABASE:
    - PostgreSQL table: orders
      Columns: order_id, user_id, status (PENDING/RESERVATION_CONFIRMED/PAID/FULFILLED/CANCELLED), 
               total_amount, items, created_at, updated_at
    - PostgreSQL table: outbox_events (Outbox Pattern for reliable event publishing)
      Columns: id, aggregate_id, event_type, payload, created_at, published_at

PATTERN: Outbox Pattern + Saga Choreography
    - Events stored in database BEFORE publishing to Kafka
    - OutboxPublisher background thread polls every 2 seconds
    - Guarantees event publishing even if service crashes
    - Supports compensation logic for transaction rollback

USAGE:
    Runs on port 8002 in Docker container
    Access: http://localhost:8002/orders/...
"""

import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

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


def fulfillment_job_worker(producer: BaseKafkaProducer, poll_interval_seconds: int = 10, fulfillment_delay_seconds: int = 5):
    """
    Background worker that simulates order fulfillment process.
    
    Periodically checks for orders in PAID status and publishes order.fulfilled events.
    
    Args:
        producer: Kafka producer for publishing events
        poll_interval_seconds: How often to check for PAID orders (default 10 seconds)
        fulfillment_delay_seconds: Delay before order is marked fulfilled (default 5 seconds)
    """
    logger.info(f"Fulfillment job started (poll every {poll_interval_seconds}s, delay {fulfillment_delay_seconds}s)")
    
    while True:
        try:
            from repository import OrderRepository
            
            db_session = SessionLocal()
            repo = OrderRepository(db_session)
            
            # Get orders that are PAID and ready for fulfillment
            now = datetime.now(ZoneInfo("America/Los_Angeles"))
            fulfillment_cutoff = now - timedelta(seconds=fulfillment_delay_seconds)
            
            # Query database for PAID orders older than cutoff
            from models import Order
            orders = db_session.query(Order).filter(
                Order.status == "PAID",
                Order.updated_at <= fulfillment_cutoff,
            ).limit(10).all()
            
            if orders:
                logger.info(f"Found {len(orders)} orders ready for fulfillment")
                
                for order in orders:
                    try:
                        # Publish fulfillment event
                        event_id = str(uuid4())
                        event_data = {
                            "event_id": event_id,
                            "event_type": "order.fulfilled",
                            "correlation_id": order.order_id,
                            "timestamp": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
                            "order_id": order.order_id,
                            "user_id": order.user_id,
                            "tracking_number": f"TRK-{order.order_id[-8:]}",
                            "shipped_at": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
                        }
                        
                        producer.publish("order.fulfilled", event_data)
                        logger.info(f"Published order.fulfilled event for order {order.order_id}")
                        
                    except Exception as e:
                        logger.error(f"Error publishing fulfillment event for order {order.order_id}: {e}")
            
            db_session.close()
            
        except Exception as e:
            logger.error(f"Error in fulfillment job: {e}")
        
        # Wait before next check
        time.sleep(poll_interval_seconds)


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
                "inventory.reserved",
                "inventory.depleted",
                "payment.processed",
                "payment.failed",
                "order.fulfilled",
            ],
        )

        db_session = SessionLocal()

        def handle_event(event):
            """Handle incoming event based on type."""
            saga = SagaHandler(db_session, producer)

            if event.event_type == "cart.checkout_initiated":
                saga.handle_cart_checkout_initiated(event)
            elif event.event_type == "inventory.reserved":
                saga.handle_inventory_reserved(event)
            elif event.event_type == "inventory.depleted":
                saga.handle_inventory_depleted(event)
            elif event.event_type == "payment.processed":
                saga.handle_payment_processed(event)
            elif event.event_type == "payment.failed":
                saga.handle_payment_failed(event)
            elif event.event_type == "order.fulfilled":
                saga.handle_order_fulfilled(event)

        try:
            consumer.consume(handle_event)
        except Exception as e:
            logger.error(f"Error in order consumer: {e}")

    consumer_thread = threading.Thread(target=order_event_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Order consumer thread started")

    # Start fulfillment job as background thread
    fulfillment_thread = threading.Thread(
        target=fulfillment_job_worker,
        args=(producer,),
        kwargs={
            "poll_interval_seconds": int(os.getenv("POLL_INTERVAL_SECONDS", "10")),
            "fulfillment_delay_seconds": int(os.getenv("FULFILLMENT_DELAY_SECONDS", "5")),
        },
        daemon=True,
    )
    fulfillment_thread.start()
    logger.info("Fulfillment job thread started")

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


@app.get("/orders/user/{user_id}")
async def get_user_orders(user_id: str):
    """Get all orders for a specific user."""
    from repository import OrderRepository

    try:
        db = SessionLocal()
        repo = OrderRepository(db)
        orders = repo.get_orders_by_user(user_id)

        if not orders:
            return {
                "user_id": user_id,
                "orders": [],
                "total_orders": 0,
            }

        return {
            "user_id": user_id,
            "orders": [
                {
                    "order_id": order.order_id,
                    "status": order.status,
                    "total_amount": order.total_amount,
                    "items": order.items,
                    "created_at": order.created_at.isoformat(),
                    "updated_at": order.updated_at.isoformat(),
                }
                for order in orders
            ],
            "total_orders": len(orders),
        }
    except Exception as e:
        logger.error(f"Error getting user orders: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.order_service_port)
