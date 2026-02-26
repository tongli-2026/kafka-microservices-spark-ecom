"""
inventory-service/main.py - Inventory and Product Management Microservice

PURPOSE:
    Manages product catalog and stock levels. Handles inventory reservations
    when orders are created and releases stock if orders are cancelled.
    Implements production-style inventory-first flow with optimistic locking.

INVENTORY WORKFLOW (Production-Style: Check Inventory FIRST):
    1. Listen for order.created events from Order Service
    2. Attempt to reserve stock for each ordered item
    3. If successful:
       - Publish inventory.reserved event → Order proceeds to payment
       - Check if stock is now low, publish inventory.low alert to admins
    4. If reservation fails (insufficient stock):
       - Publish inventory.depleted event → Order Service cancels order
       - Customer NOT charged (key advantage: no refunds needed)
    5. If order is cancelled:
       - Check cancellation_source field to determine action:
         * payment_failed: Release reserved stock back to inventory
         * inventory_depleted: No action (stock was never reserved)

KEY FEATURES:
    - Optimistic Locking: Prevents overselling in concurrent scenarios
    - Stock Reservation: Guarantees inventory before payment
    - Production Pattern: Inventory checked BEFORE payment processing
    - Low Stock Alerts: Proactive admin notifications
    - Smart Cancellation Handling: Different logic based on cancellation reason

RESPONSIBILITIES:
    - Maintain product catalog (CRUD operations)
    - Track stock levels for all products with version control
    - Reserve inventory for created orders (optimistic locking)
    - Release inventory for cancelled orders (only if payment failed)
    - Publish alerts on low stock or failed reservations
    - Seed initial product data

API ENDPOINTS:
    GET    /products - List all products
    GET    /products/{product_id} - Get product details
    POST   /products - Create new product (admin)
    PUT    /products/{product_id} - Update product (admin)
    DELETE /products/{product_id} - Delete product (admin)
    GET    /health - Health check

KAFKA EVENTS:
    CONSUMED:
        - order.created: Attempt to reserve stock for order items
        - order.cancelled: Release reserved stock ONLY if payment_failed
    
    PUBLISHED:
        - inventory.reserved ✓: Stock successfully reserved → order proceeds to payment
        - inventory.depleted ✗: Insufficient stock → order cancelled (NO CHARGE)
        - inventory.low: Stock below threshold after successful reservation (informational alert to admins)

SCENARIOS:
    Scenario 1: Sufficient Stock (e.g., 3 units available, customer buys 3)
        order.created → reserve_stock() succeeds → inventory.reserved published
        → Order proceeds to payment
        → inventory.low alert may follow (informational only)
    
    Scenario 2: Insufficient Stock (e.g., 2 units available, customer wants 3)
        order.created → reserve_stock() fails → inventory.depleted published
        → Order Service cancels order with cancellation_source=inventory_depleted
        → Inventory Service receives order.cancelled, sees inventory_depleted → NO stock release
        → Customer NOT charged ✓
    
    Scenario 3: Payment Failure After Successful Reservation
        order.created → reserve_stock() succeeds → inventory.reserved published
        → Order proceeds to payment → Payment fails
        → Order Service cancels order with cancellation_source=payment_failed
        → Inventory Service receives order.cancelled, sees payment_failed → Release stock
        → Stock back in inventory ✓
        → Customer NOT charged ✓

CANCELLATION SOURCE TRACKING:
    The order.cancelled event includes a cancellation_source field:
    - "inventory_depleted": Order was cancelled because stock unavailable (no release needed)
    - "payment_failed": Order was cancelled because payment failed (release reserved stock)
    
    This allows Inventory Service to handle each scenario correctly without ambiguity.

DATABASE:
    - PostgreSQL table: products
      Columns: product_id, name, description, price, stock, version, created_at, updated_at
      Note: version field used for optimistic locking to prevent overselling
    - PostgreSQL table: stock_reservations
      Columns: id, order_id, product_id, quantity, created_at

STOCK ALERTS:
    - Low stock warning: Triggered when stock < 10 units (after successful reservation)
    - Depleted/Insufficient: Triggered when reservation fails (regardless of current stock level)

OPTIMISTIC LOCKING:
    - Retries: Up to 3 attempts on concurrent conflicts
    - Pattern: Read version → Attempt update with version condition → Retry if conflict
    - Benefit: Prevents database locks while guaranteeing data consistency

USAGE:
    Runs on port 8004 in Docker container
    Access: http://localhost:8004/products/...
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
from events import (
    InventoryReservedEvent,  # Stock reservation success
    InventoryLowEvent,  # Low stock warning
    InventoryDepletedEvent,  # Out of stock alert
)

# Setup logging
setup_logging("inventory-service")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "kafka_ecom")
    inventory_service_port: int = int(os.getenv("INVENTORY_SERVICE_PORT", "8004"))


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

    logger.info("Starting Inventory Service...")

    # Initialize database
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Seed products
    try:
        from seed_data import seed_products

        db = SessionLocal()
        seed_products(db)
        db.close()
        logger.info("Products seeded")
    except Exception as e:
        logger.error(f"Failed to seed products: {e}")

    # Initialize Kafka topics
    try:
        create_topics(settings.kafka_bootstrap_servers)
        logger.info("Kafka topics initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka topics: {e}")
        raise

    # Initialize Kafka producer
    try:
        producer = BaseKafkaProducer(settings.kafka_bootstrap_servers, client_id="inventory-producer")
        logger.info("Kafka producer initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        raise

    # Start consumer thread for inventory events
    def inventory_consumer():
        """Consume order and inventory events."""
        from repository import InventoryRepository

        consumer = BaseKafkaConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="inventory-service-group",
            topics=["order.created", "order.cancelled"],
        )

        LOW_STOCK_THRESHOLD = 10

        def handle_event(event):
            """Handle incoming event."""
            db = SessionLocal()
            repo = InventoryRepository(db)

            if event.event_type == "order.created":
                # Reserve stock for each item in order
                for item in event.items:
                    product_id = item.get("product_id")
                    quantity = item.get("quantity")

                    success = repo.reserve_stock(event.order_id, product_id, quantity)

                    if success:
                        # Publish inventory.reserved event (reservation succeeded)
                        reserved_event = InventoryReservedEvent(
                            order_id=event.order_id,
                            product_id=product_id,
                            quantity=quantity,
                            correlation_id=event.correlation_id,
                        )
                        producer.publish("inventory.reserved", reserved_event)

                        # Check remaining stock levels for informational alerts
                        current_stock = repo.get_stock_level(product_id)
                        # Publish inventory.low as informational alert no matter when current_stock is low or depleted
                        if current_stock < LOW_STOCK_THRESHOLD:
                            low_event = InventoryLowEvent(
                                product_id=product_id,
                                current_stock=current_stock,
                                threshold=LOW_STOCK_THRESHOLD,
                                correlation_id=event.correlation_id,
                            )
                            producer.publish("inventory.low", low_event)
                            logger.info(f"Product {product_id} stock is low ({current_stock} units remaining)")
                    else:
                        # Reservation failed - cannot fulfill order due to insufficient stock or depleted inventory
                        current_stock = repo.get_stock_level(product_id)
                        logger.error(f"Failed to reserve stock for product {product_id}: need {quantity}, have {current_stock}")
                        
                        # Publish inventory.depleted to signal order cancellation
                        # (depleted means insufficient inventory, regardless of whether it's 0 or just low compared to requested quantity)
                        depleted_event = InventoryDepletedEvent(
                            order_id=event.order_id,  # Order Service needs this to know which order to cancel
                            product_id=product_id,
                            correlation_id=event.correlation_id,
                        )
                        producer.publish("inventory.depleted", depleted_event)

            elif event.event_type == "order.cancelled":
                # Release stock ONLY if order was cancelled due to payment failure
                # If cancelled due to inventory.depleted, no stock was reserved so nothing to release
                cancellation_source = getattr(event, 'cancellation_source', None)
                
                # Try to get from dict if event is a dict-like object
                if cancellation_source is None and hasattr(event, '__dict__'):
                    cancellation_source = event.__dict__.get('cancellation_source')
                
                # Try to access as dictionary if available
                if cancellation_source is None and isinstance(event, dict):
                    cancellation_source = event.get('cancellation_source')
                
                logger.info(f"Order {event.order_id} cancelled: cancellation_source = {cancellation_source}")
                
                if cancellation_source == "payment_failed":
                    # Payment failed - release the reserved stock back to inventory
                    from models import StockReservation

                    reservations = (
                        db.query(StockReservation).filter(
                            StockReservation.order_id == event.order_id
                        ).all()
                    )

                    for reservation in reservations:
                        repo.release_stock(reservation.product_id, reservation.quantity)
                        db.delete(reservation)
                    
                    logger.info(f"Released reserved stock for order {event.order_id} (payment failed)")
                else:
                    # Cancelled due to inventory.depleted or other reason
                    # No stock to release (reservation never succeeded)
                    logger.info(f"Order {event.order_id} cancelled but no stock to release (reason: {cancellation_source or 'unknown'})")


            db.commit()
            db.close()

        try:
            consumer.consume(handle_event)
        except Exception as e:
            logger.error(f"Error in inventory consumer: {e}")

    consumer_thread = threading.Thread(target=inventory_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Inventory consumer thread started")

    yield

    logger.info("Shutting down Inventory Service...")
    if producer:
        producer.flush()


app = FastAPI(title="Inventory Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "inventory-service",
        "version": "1.0.0",
    }


@app.get("/products")
async def list_products():
    """List all products."""
    from models import Product

    try:
        db = SessionLocal()
        products = db.query(Product).all()
        return [
            {
                "product_id": p.product_id,
                "name": p.name,
                "price": p.price,
                "stock": p.stock,
            }
            for p in products
        ]
    except Exception as e:
        logger.error(f"Error listing products: {e}")
        raise
    finally:
        db.close()


@app.get("/products/{product_id}")
async def get_product(product_id: str):
    """Get product details."""
    from repository import InventoryRepository

    try:
        db = SessionLocal()
        repo = InventoryRepository(db)
        product = repo.get_product(product_id)

        if not product:
            return {"error": "Product not found"}, 404

        return {
            "product_id": product.product_id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "stock": product.stock,
        }
    except Exception as e:
        logger.error(f"Error getting product: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.inventory_service_port)
