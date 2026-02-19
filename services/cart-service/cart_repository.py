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
    CART_TTL = 86400  # 24 hours

    def __init__(self, redis_client: redis.Redis):
        """Initialize cart repository."""
        self.redis = redis_client

    def add_item(self, user_id: str, item: CartItem) -> None:
        """Add item to user's cart."""
        cart_key = f"{self.CART_KEY_PREFIX}{user_id}"
        cart_data = self._get_cart_dict(user_id)

        # Update or add item
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
        """Get user's cart with total amount."""
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

    def clear_cart(self, user_id: str) -> None:
        """Clear user's cart."""
        cart_key = f"{self.CART_KEY_PREFIX}{user_id}"
        self.redis.delete(cart_key)
        logger.info(f"Cleared cart for user {user_id}")

    def _get_cart_dict(self, user_id: str) -> Dict[str, Dict[str, Any]]:
        """Get cart as dictionary, return empty dict if not found."""
        cart_key = f"{self.CART_KEY_PREFIX}{user_id}"
        cart_json = self.redis.get(cart_key)

        if cart_json is None:
            return {}

        return json.loads(cart_json)
