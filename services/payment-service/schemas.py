from typing import Optional

from pydantic import BaseModel


class PaymentSchema(BaseModel):
    """Payment schema."""

    payment_id: str
    order_id: str
    user_id: str
    amount: float
    currency: str
    method: str
    status: str
    reason: Optional[str] = None


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    service: str
    version: str
