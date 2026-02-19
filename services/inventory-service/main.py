"""
inventory-service/main.py - Inventory and Product Management Microservice

PURPOSE:
    Manages product catalog and stock levels. Handles inventory reservations
    when orders are confirmed and releases stock if orders are cancelled.

INVENTORY WORKFLOW:
    1. Listen for order.confirmed events
    2. Reserve stock for ordered items
    3. Update stock levels in database
    4. Publish inventory events (reserved, low stock, depleted)
    5. Handle order cancellations (release reserved stock)

RESPONSIBILITIES:
    - Maintain product catalog (CRUD operations)
    - Track stock levels for all products
    - Reserve inventory for confirmed orders
    - Release inventory for cancelled orders
    - Alert on low stock or depleted inventory
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
        - order.confirmed: Reserve stock for order items
        - order.cancelled: Release reserved stock
    
    PUBLISHED:
        - inventory.reserved: Stock successfully reserved
        - inventory.low: Stock below threshold (< 10 units)
        - inventory.depleted: Product out of stock

DATABASE:
    - PostgreSQL table: products
      Columns: product_id, name, price, stock, created_at, updated_at
    - PostgreSQL table: stock_reservations
      Columns: reservation_id, order_id, product_id, quantity, created_at

STOCK ALERTS:
    - Low stock warning: stock < 10 units
    - Depleted alert: stock = 0

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
                        # Publish inventory.reserved event
                        reserved_event = InventoryReservedEvent(
                            order_id=event.order_id,
                            product_id=product_id,
                            quantity=quantity,
                            correlation_id=event.correlation_id,
                        )
                        producer.publish("inventory.reserved", reserved_event)

                        # Check stock levels
                        current_stock = repo.get_stock_level(product_id)
                        if current_stock == 0:
                            depleted_event = InventoryDepletedEvent(
                                product_id=product_id,
                                correlation_id=event.correlation_id,
                            )
                            producer.publish("inventory.depleted", depleted_event)
                        elif current_stock < LOW_STOCK_THRESHOLD:
                            low_event = InventoryLowEvent(
                                product_id=product_id,
                                current_stock=current_stock,
                                threshold=LOW_STOCK_THRESHOLD,
                                correlation_id=event.correlation_id,
                            )
                            producer.publish("inventory.low", low_event)
                    else:
                        logger.error(f"Failed to reserve stock for product {product_id}")

            elif event.event_type == "order.cancelled":
                # Release stock for each item in order
                from models import StockReservation

                reservations = (
                    db.query(StockReservation).filter(
                        StockReservation.order_id == event.order_id
                    ).all()
                )

                for reservation in reservations:
                    repo.release_stock(reservation.product_id, reservation.quantity)
                    db.delete(reservation)

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
