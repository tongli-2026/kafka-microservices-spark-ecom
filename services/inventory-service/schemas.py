from typing import List, Optional

from pydantic import BaseModel


class ProductSchema(BaseModel):
    """Product schema."""

    product_id: str
    name: str
    description: Optional[str] = None
    price: float
    stock: int


class ProductsListResponse(BaseModel):
    """Response model for list of products."""

    products: List[ProductSchema]
    total_products: int


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    service: str
    version: str
