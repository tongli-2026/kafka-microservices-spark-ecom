"""
cart-service/main.py - Shopping Cart Microservice

PURPOSE:
    Manages shopping cart operations for e-commerce platform.
    Stores cart state in Redis for fast access and publishes events to Kafka.

RESPONSIBILITIES:
    - Add/remove items from user shopping carts
    - Calculate cart totals and item counts
    - Initiate checkout process
    - Publish cart events to Kafka for order processing
    - Maintain cart state in Redis (in-memory storage)

API ENDPOINTS:
    POST   /cart/add       - Add item to cart
    DELETE /cart/remove    - Remove item from cart
    GET    /cart/{user_id} - View cart contents
    POST   /cart/checkout  - Initiate checkout (triggers order creation)
    GET    /health         - Health check endpoint

KAFKA EVENTS PUBLISHED:
    - cart.item_added: When user adds product to cart
    - cart.item_removed: When user removes product from cart
    - cart.checkout_initiated: When user starts checkout process

DATA STORAGE:
    - Redis: Cart state (key: "cart:{user_id}", value: JSON cart data)
    - TTL: Cart expires after inactivity (configurable)

DEPENDENCIES:
    - Redis: Session state storage
    - Kafka: Event streaming
    - FastAPI: HTTP API framework

USAGE:
    Runs on port 8001 in Docker container
    Access: http://localhost:8001/cart/...
"""

import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import redis  # In-memory cache for cart data
from fastapi import FastAPI  # Web framework
from pydantic_settings import BaseSettings  # Configuration management

# Add shared library to path for common utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Import shared Kafka and event utilities
from kafka_client import BaseKafkaProducer  # Kafka message publisher
from logging_config import setup_logging  # Centralized logging
from topic_initializer import create_topics  # Kafka topic creation
from events import CartCheckoutInitiatedEvent, CartItemAddedEvent, CartItemRemovedEvent  # Event schemas

# Setup logging
setup_logging("cart-service")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    cart_service_port: int = int(os.getenv("CART_SERVICE_PORT", "8001"))


settings = Settings()

# Global instances
redis_client: redis.Redis = None
producer: BaseKafkaProducer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle."""
    global redis_client, producer

    logger.info("Starting Cart Service...")

    # Initialize Kafka topics
    try:
        create_topics(settings.kafka_bootstrap_servers)
        logger.info("Kafka topics initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka topics: {e}")
        raise

    # Initialize Redis
    try:
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )
        redis_client.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise

    # Initialize Kafka producer
    try:
        producer = BaseKafkaProducer(settings.kafka_bootstrap_servers, client_id="cart-producer")
        logger.info("Kafka producer initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        raise

    # Start consumer thread for cart events
    def cart_event_consumer():
        """Consume cart events and handle business logic."""
        from kafka_client import BaseKafkaConsumer

        consumer = BaseKafkaConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="cart-service-group",
            topics=["cart.checkout_initiated"],
        )

        def handle_checkout_initiated(event):
            """Handle checkout initiated event."""
            logger.info(
                f"Handling checkout initiated event for user {event.user_id}",
                extra={"event_type": event.event_type, "correlation_id": event.correlation_id},
            )
            # Clear cart after checkout
            from cart_repository import CartRepository
            repo = CartRepository(redis_client)
            repo.clear_cart(event.user_id)
            logger.info(f"Cart cleared for user {event.user_id}")

        try:
            consumer.consume(handle_checkout_initiated)
        except Exception as e:
            logger.error(f"Error in cart consumer: {e}")

    consumer_thread = threading.Thread(target=cart_event_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Cart consumer thread started")

    yield

    logger.info("Shutting down Cart Service...")
    if redis_client:
        redis_client.close()
    if producer:
        producer.close()


app = FastAPI(title="Cart Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "cart-service",
        "version": "1.0.0",
    }


@app.post("/cart/{user_id}/items")
async def add_item(user_id: str, item: dict):
    """Add item to cart and publish event."""
    from cart_repository import CartRepository, CartItem

    try:
        repo = CartRepository(redis_client)
        cart_item = CartItem(**item)
        repo.add_item(user_id, cart_item)

        # Publish cart.item_added event
        event = CartItemAddedEvent(
            user_id=user_id,
            product_id=item["product_id"],
            quantity=item["quantity"],
            price=item["price"],
            correlation_id=str(uuid4()),
        )
        producer.publish("cart.item_added", event)

        return {"message": f"Item {item['product_id']} added to cart"}
    except Exception as e:
        logger.error(f"Error adding item to cart: {e}")
        raise


@app.delete("/cart/{user_id}/items/{product_id}")
async def remove_item(user_id: str, product_id: str):
    """Remove item from cart and publish event."""
    from cart_repository import CartRepository

    try:
        repo = CartRepository(redis_client)
        removed = repo.remove_item(user_id, product_id)

        if removed:
            # Publish cart.item_removed event
            event = CartItemRemovedEvent(
                user_id=user_id,
                product_id=product_id,
                correlation_id=str(uuid4()),
            )
            producer.publish("cart.item_removed", event)
            return {"message": f"Item {product_id} removed from cart"}
        else:
            return {"message": f"Item {product_id} not found in cart"}, 404
    except Exception as e:
        logger.error(f"Error removing item from cart: {e}")
        raise


@app.get("/cart/{user_id}")
async def get_cart(user_id: str):
    """Get user's cart."""
    from cart_repository import CartRepository

    try:
        repo = CartRepository(redis_client)
        cart = repo.get_cart(user_id)
        return cart
    except Exception as e:
        logger.error(f"Error getting cart: {e}")
        raise


@app.post("/cart/{user_id}/checkout")
async def checkout(user_id: str):
    """Initiate checkout."""
    from cart_repository import CartRepository

    try:
        repo = CartRepository(redis_client)
        cart = repo.get_cart(user_id)

        if not cart["items"]:
            return {"message": "Cart is empty"}, 400

        # Publish cart.checkout_initiated event
        event = CartCheckoutInitiatedEvent(
            user_id=user_id,
            items=cart["items"],
            total_amount=cart["total_amount"],
            correlation_id=str(uuid4()),
        )
        producer.publish("cart.checkout_initiated", event)

        return {
            "message": "Checkout initiated",
            "cart": cart,
        }
    except Exception as e:
        logger.error(f"Error during checkout: {e}")
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.cart_service_port)
