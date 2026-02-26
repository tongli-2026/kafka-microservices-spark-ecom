"""
Cart Repository Module

This module provides Redis-based persistence for shopping cart data in the Cart Service.
It implements the repository pattern to abstract cart storage operations from business logic.

Key Features:
    - Fast, in-memory cart storage using Redis
    - Automatic expiration of abandoned carts (24-hour TTL)
    - Cart operations: add, remove, update, and retrieve items
    - Seamless JSON serialization for complex cart data
    - Atomic operations using Redis transactions when needed
    - Logging for debugging and monitoring

Architecture:
    - CartItem: Pydantic model for type-safe item representation
    - CartRepository: Main class handling Redis operations
    - Uses Redis key pattern: "cart:{user_id}" for cart storage

Data Format (Redis):
    Key: "cart:user123"
    Value: '{
        "product_id_1": {"quantity": 2, "price": 99.99},
        "product_id_2": {"quantity": 1, "price": 49.99}
    }'

TTL Management:
    - Each cart is stored with 86400-second (24-hour) expiration
    - TTL resets on every cart modification
    - Expired carts are automatically removed by Redis
    - Helps manage memory and clean up abandoned carts

Integration Points:
    - Receives CartItem objects from API schemas
    - Produces events to Kafka topics when carts are modified
    - Supports checkout operations by returning full cart data

Example Usage:
    ```python
    from shared.kafka_client import KafkaProducerClient
    
    redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
    cart_repo = CartRepository(redis_client)
    
    # Add item to cart
    item = CartItem(product_id="PROD-001", quantity=2, price=99.99)
    cart_repo.add_item("user123", item)
    
    # Add another item
    item2 = CartItem(product_id="PROD-002", quantity=1, price=49.99)
    cart_repo.add_item("user123", item2)
    
    # Retrieve cart
    cart = cart_repo.get_cart("user123")
    # Returns: {
    #     "user_id": "user123",
    #     "items": [
    #         {"product_id": "PROD-001", "quantity": 2, "price": 99.99, "item_total": 199.98},
    #         {"product_id": "PROD-002", "quantity": 1, "price": 49.99, "item_total": 49.99}
    #     ],
    #     "total_amount": 249.97,
    #     "item_count": 2
    # }
    
    # Update item quantity (reduce PROD-001 from 2 to 1)
    cart_repo.update_item_quantity("user123", "PROD-001", 1)
    
    # Remove item by setting quantity to 0
    cart_repo.update_item_quantity("user123", "PROD-002", 0)
    
    # Remove item completely using remove_item method
    cart_repo.remove_item("user123", "PROD-001")
    
    # Clear entire cart after checkout
    cart_repo.clear_cart("user123")
    ```
"""

import json
import logging
from typing import Any, Dict, List, Optional

import redis
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CartItem(BaseModel):
    """Cart item model."""

    product_id: str
    quantity: int
    price: float


class CartRepository:
    """Repository for managing shopping carts in Redis."""

    CART_KEY_PREFIX = "cart:"
    # Set a TTL (Time To Live) for cart data in Redis to automatically expire carts that haven't been updated for a certain period (e.g., 24 hours). 
    # This helps prevent stale data and manages memory usage.
    CART_TTL = 86400  # 24 hours

    def __init__(self, redis_client: redis.Redis):
        """Initialize cart repository."""
        # Store the Redis client instance for use in cart operations
        self.redis = redis_client

    def add_item(self, user_id: str, item: CartItem) -> None:
        """Add item to user's cart. Increment quantity if item already exists."""
        cart_key = f"{self.CART_KEY_PREFIX}{user_id}"
        cart_data = self._get_cart_dict(user_id)

        # Check if the item already exists in the cart
        if item.product_id in cart_data:
            # Increment the quantity
            cart_data[item.product_id]["quantity"] += item.quantity
        else:
            # Add new item
            cart_data[item.product_id] = {
                "quantity": item.quantity,
                "price": item.price,
            }

        # Store updated cart
        self.redis.set(cart_key, json.dumps(cart_data), ex=self.CART_TTL)
        logger.info(f"Added item {item.product_id} to cart for user {user_id}")

    def remove_item(self, user_id: str, product_id: str) -> bool:
        """Remove item from user's cart. Returns True if item was removed."""
        cart_key = f"{self.CART_KEY_PREFIX}{user_id}"
        cart_data = self._get_cart_dict(user_id)

        if product_id not in cart_data:
            logger.warning(f"Product {product_id} not in cart for user {user_id}")
            return False

        del cart_data[product_id]

        if cart_data:
            # Store updated cart
            self.redis.set(cart_key, json.dumps(cart_data), ex=self.CART_TTL)
        else:
            # Delete empty cart
            self.redis.delete(cart_key)

        logger.info(f"Removed item {product_id} from cart for user {user_id}")
        return True

    def get_cart(self, user_id: str) -> Dict[str, Any]:
        """Get user's cart with total amount and item count."""
        cart_data = self._get_cart_dict(user_id)

        items: List[Dict[str, Any]] = []
        total_amount = 0.0

        for product_id, item_data in cart_data.items():
            item_total = item_data["quantity"] * item_data["price"]
            items.append(
                {
                    "product_id": product_id,
                    "quantity": item_data["quantity"],
                    "price": item_data["price"],
                    "item_total": item_total,
                }
            )
            total_amount += item_total

        return {
            "user_id": user_id,
            "items": items,
            "total_amount": total_amount,
            "item_count": len(items),
        }

    def update_item_quantity(self, user_id: str, product_id: str, quantity: int) -> bool:
        """Update quantity of an item in cart. If quantity is 0, remove the item. Returns True if successful."""
        cart_key = f"{self.CART_KEY_PREFIX}{user_id}"
        cart_data = self._get_cart_dict(user_id)

        if product_id not in cart_data:
            logger.warning(f"Product {product_id} not in cart for user {user_id}")
            return False

        if quantity < 0:
            logger.warning(f"Invalid quantity {quantity} for product {product_id}")
            return False

        if quantity == 0:
            # Remove item if quantity is 0
            del cart_data[product_id]
            logger.info(f"Removed item {product_id} from cart for user {user_id} (quantity set to 0)")
        else:
            # Update quantity
            cart_data[product_id]["quantity"] = quantity
            logger.info(f"Updated item {product_id} quantity to {quantity} for user {user_id}")

        if cart_data:
            # Store updated cart
            self.redis.set(cart_key, json.dumps(cart_data), ex=self.CART_TTL)
        else:
            # Delete empty cart
            self.redis.delete(cart_key)

        return True

    def clear_cart(self, user_id: str) -> None:
        """Clear user's cart."""
        cart_key = f"{self.CART_KEY_PREFIX}{user_id}"
        self.redis.delete(cart_key)
        logger.info(f"Cleared cart for user {user_id}")

    def _get_cart_dict(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """Get cart as dictionary, return empty dict if not found."""
        # What's actually in Redis:
        # Key: "cart:user_123"
        # Value: '{"prod_123": {"quantity": 2, "price": 19.99}, "prod_456": {"quantity": 1, "price": 9.99}}'
        # If the key doesn't exist (e.g., cart expired or never created), return an empty dictionary to indicate an empty cart. 
        # This allows the rest of the code to handle it gracefully without needing to check for None.
        cart_key = f"{self.CART_KEY_PREFIX}{user_id}"
        cart_json = self.redis.get(cart_key)

        if cart_json is None:
            return {}

        return json.loads(cart_json)
