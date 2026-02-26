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
    POST   /cart/{user_id}/items           - Add item to cart
    PUT    /cart/{user_id}/items/{product_id} - Update item quantity
    DELETE /cart/{user_id}/items/{product_id} - Remove item from cart
    GET    /cart/{user_id}                 - View cart contents
    POST   /cart/{user_id}/checkout        - Initiate checkout (triggers order creation)
    GET    /health                         - Health check endpoint

KAFKA EVENTS PUBLISHED:
    - cart.item_added: When user adds product to cart
    - cart.item_removed: When user removes product from cart
    - cart.checkout_initiated: When user starts checkout process

DATA STORAGE:
    - Redis: Cart state (key: "cart:{user_id}", value: '{"product_id_1": {"quantity": X, "price": X.XX}, "prod_id_2": {"quantity": X, "price": X.XX}}')
    - TTL: Cart expires after inactivity (configurable)

TESTING COMMANDS:
    1. Health Check:
        curl -X GET http://localhost:8001/health
    
    2. Add Item to Cart (add 2 laptops at $999.99):
        curl -X POST http://localhost:8001/cart/user123/items \
          -H "Content-Type: application/json" \
          -d '{"product_id": "laptop", "quantity": 2, "price": 999.99}'
    
    3. Add Another Item (add 1 mouse at $29.99):
        curl -X POST http://localhost:8001/cart/user123/items \
          -H "Content-Type: application/json" \
          -d '{"product_id": "mouse", "quantity": 1, "price": 29.99}'
    
    4. View Cart Contents:
        curl -X GET http://localhost:8001/cart/user123
    
    5. Update Item Quantity (reduce laptops from 2 to 1):
        curl -X PUT http://localhost:8001/cart/user123/items/laptop \
          -H "Content-Type: application/json" \
          -d '{"quantity": 1}'
    
    6. Remove Item Completely (set quantity to 0):
        curl -X PUT http://localhost:8001/cart/user123/items/laptop \
          -H "Content-Type: application/json" \
          -d '{"quantity": 0}'
    
    7. Remove Item (alternative DELETE method):
        curl -X DELETE http://localhost:8001/cart/user123/items/mouse
    
    8. View Updated Cart (should only have mouse if using step 6, or laptop if using step 7, or empty if both steps were done):
        curl -X GET http://localhost:8001/cart/user123
    
    9. Checkout (initiate order processing):
        curl -X POST http://localhost:8001/cart/user123/checkout \
          -H "Content-Type: application/json"
    
    10. View Cart After Checkout (should be empty):
        curl -X GET http://localhost:8001/cart/user123

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
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import redis  # In-memory cache for cart data
from fastapi import FastAPI, HTTPException, status  # Web framework
from pydantic_settings import BaseSettings  # Configuration management

# Import local schemas for input/output validation
from schemas import CartItemRequest, CartResponse, HealthResponse, UpdateQuantityRequest  # Pydantic models

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


# Creates a context manager with two phases:
# 1. Initialization phase (before yield): Initialize Kafka topics, Redis, and Kafka producer
# 2. Cleanup phase (after yield): Close Redis and Kafka connections gracefully
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

    yield   # ← Application is now ready to handle requests

    # Cleanup on shutdown
    logger.info("Shutting down Cart Service...")
    if redis_client:
        redis_client.close()
    if producer:
        producer.close()


# Create FastAPI app with lifespan context manager for startup and shutdown logic
# The app is created with the lifespan context manager, so startup tasks run automatically.
app = FastAPI(title="Cart Service", version="1.0.0", lifespan=lifespan)


# This creates a health check endpoint at GET /health that returns a JSON response showing the service is running.
# We can use this endpoint for monitoring and load balancer health checks to ensure the service is healthy and responsive.
# Visit http://localhost:8001/health to see the response:
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        service="cart-service",
        version="1.0.0",
    )

# The add_item endpoint allows clients to add a product to a user's shopping cart. 
# It accepts a POST request with the user_id in the URL and the item details (product_id, quantity, price) in the request body as JSON. 
# The endpoint updates the cart in Redis and publishes a cart.item_added event to Kafka with the item details and a correlation ID for tracing.
@app.post("/cart/{user_id}/items", status_code=status.HTTP_201_CREATED)
async def add_item(user_id: str, item: CartItemRequest) -> dict:
    """Add item to cart and publish event."""
    from cart_repository import CartRepository, CartItem

    try:
        repo = CartRepository(redis_client)
        # Convert CartItemRequest to CartItem for repository
        cart_item = CartItem(
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price
        )
        repo.add_item(user_id, cart_item)

        # Publish cart.item_added event
        event = CartItemAddedEvent(
            user_id=user_id,
            product_id=item.product_id,
            quantity=item.quantity,
            price=item.price,
            correlation_id=str(uuid4()),
        )
        producer.publish("cart.item_added", event)

        return {"message": f"Item {item.product_id} added to cart"}
    except Exception as e:
        logger.error(f"Error adding item to cart: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# The remove_item endpoint allows clients to remove a product from a user's shopping cart.
# It accepts a DELETE request with the user_id and product_id in the URL.
# The endpoint updates the cart in Redis and publishes a cart.item_removed event to Kafka with the product_id and a correlation ID for tracing. 
@app.delete("/cart/{user_id}/items/{product_id}", status_code=status.HTTP_200_OK)
async def remove_item(user_id: str, product_id: str) -> dict:
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item {product_id} not found in cart"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing item from cart: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# The update_item_quantity endpoint allows clients to update the quantity of an item in the cart.
# It accepts a PUT request with the user_id and product_id in the URL and the new quantity in the request body.
# If quantity is set to 0, the item is removed from the cart.
# The endpoint publishes a cart.item_removed event if the item is removed, or no event if only quantity is updated.
@app.put("/cart/{user_id}/items/{product_id}", status_code=status.HTTP_200_OK)
async def update_item_quantity(user_id: str, product_id: str, request: UpdateQuantityRequest) -> dict:
    """Update item quantity in cart. If quantity is 0, remove the item."""
    from cart_repository import CartRepository

    try:
        quantity = request.quantity
        if quantity < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be >= 0"
            )

        repo = CartRepository(redis_client)
        updated = repo.update_item_quantity(user_id, product_id, quantity)

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Item {product_id} not found in cart"
            )

        if quantity == 0:
            # Publish cart.item_removed event when item is removed
            event = CartItemRemovedEvent(
                user_id=user_id,
                product_id=product_id,
                correlation_id=str(uuid4()),
            )
            producer.publish("cart.item_removed", event)
            return {"message": f"Item {product_id} removed from cart"}
        else:
            return {"message": f"Item {product_id} quantity updated to {quantity}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating item quantity: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# The get_cart endpoint allows clients to view the contents of a user's shopping cart.
# It accepts a GET request with the user_id in the URL and returns the cart contents, including the list of items and the total amount. 
@app.get("/cart/{user_id}", response_model=CartResponse)
async def get_cart(user_id: str) -> CartResponse:
    """Get user's cart."""
    from cart_repository import CartRepository

    try:
        repo = CartRepository(redis_client)
        cart = repo.get_cart(user_id)
        return CartResponse(**cart)
    except Exception as e:
        logger.error(f"Error getting cart: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# The checkout endpoint allows clients to initiate the checkout process for a user's shopping cart.
# It accepts a POST request with the user_id in the URL. 
# The endpoint retrieves the cart contents from Redis and checks if the cart is empty. 
# If the cart has items, it publishes a cart.checkout_initiated event to Kafka with the cart details and a correlation ID for tracing.
# The cart is then cleared synchronously from Redis.
@app.post("/cart/{user_id}/checkout", status_code=status.HTTP_200_OK)
async def checkout(user_id: str) -> dict:
    """Initiate checkout and clear cart."""
    from cart_repository import CartRepository

    try:
        repo = CartRepository(redis_client)
        cart = repo.get_cart(user_id)

        if not cart["items"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cart is empty"
            )

        # Publish cart.checkout_initiated event to Kafka
        # This triggers Order Service to create an order and Analytics for cart abandonment tracking
        event = CartCheckoutInitiatedEvent(
            user_id=user_id,
            items=cart["items"],
            total_amount=cart["total_amount"],
            correlation_id=str(uuid4()),
        )
        producer.publish("cart.checkout_initiated", event)
        
        # Clear cart synchronously after publishing event to ensure cart is empty for next session
        repo.clear_cart(user_id)
        logger.info(f"Cart cleared for user {user_id} after checkout")

        return {
            "message": "Checkout initiated",
            "cart": cart,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during checkout: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# The main block runs the FastAPI application using Uvicorn, listening on all interfaces (0.0.0.0, allows Docker containers to connect) and the port specified in the settings (default 8001).
# Uvicorn is an ASGI server — it's what actually runs FastAPI and handles HTTP requests.
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.cart_service_port)
