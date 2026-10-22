from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Product(Base):
    """Product model with optimistic locking for stock management."""

    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    product_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False)
    version = Column(Integer, default=0, nullable=False)  # Optimistic lock - incremented on each update
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class StockReservation(Base):
    """Track stock reservations for orders."""

    __tablename__ = "stock_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(String(255), nullable=False, index=True)
    product_id = Column(String(255), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class InventoryOrder(Base):
    """Durable, order-level result of inventory processing."""

    __tablename__ = "inventory_orders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROCESSING', 'RESERVED', 'DEPLETED', 'RELEASED', 'CANCELLED')",
            name="ck_inventory_orders_status",
        ),
    )

    order_id = Column(String(255), primary_key=True)
    status = Column(String(16), nullable=False)
    items_json = Column(Text, nullable=True)
    result_event_id = Column(String(36), nullable=True)
    result_correlation_id = Column(String(255), nullable=True)
    failed_product_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
