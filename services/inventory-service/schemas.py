from pydantic import BaseModel


class ProductSchema(BaseModel):
    """Product schema."""

    product_id: str
    name: str
    description: str = None
    price: float
    stock: int


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    service: str
    version: str
