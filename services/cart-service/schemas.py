from typing import List

from pydantic import BaseModel


class CartItemRequest(BaseModel):
    """Request model for adding item to cart."""

    product_id: str
    quantity: int
    price: float


class UpdateQuantityRequest(BaseModel):
    """Request model for updating item quantity."""

    quantity: int


class CartItemResponse(BaseModel):
    """Response model for cart item."""

    product_id: str
    quantity: int
    price: float
    item_total: float


class CartResponse(BaseModel):
    """Response model for cart."""

    user_id: str
    items: List[CartItemResponse]
    total_amount: float
    item_count: int


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    service: str
    version: str
