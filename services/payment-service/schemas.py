from typing import List, Optional

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
    created_at: Optional[str] = None


class PaymentListResponse(BaseModel):
    """Response model for list of payments."""

    order_id: str
    payments: List[PaymentSchema]
    total_payments: int


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    service: str
    version: str
