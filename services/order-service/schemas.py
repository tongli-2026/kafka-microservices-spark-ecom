from typing import Any, Dict, List

from pydantic import BaseModel


class OrderItemSchema(BaseModel):
    """Order item schema."""

    product_id: str
    quantity: int
    price: float


class CreateOrderRequest(BaseModel):
    """Request to create an order."""

    user_id: str
    items: List[OrderItemSchema]
    total_amount: float


class OrderResponse(BaseModel):
    """Response model for order."""

    order_id: str
    user_id: str
    status: str
    items: List[Dict[str, Any]]
    total_amount: float


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    service: str
    version: str
