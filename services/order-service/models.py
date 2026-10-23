from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Order(Base):
    """Order model."""

    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    correlation_id = Column(String(255), nullable=False, index=True)  # Saga correlation ID - links all events for this order
    status = Column(String(50), default="PENDING", nullable=False)  # PENDING, RESERVATION_CONFIRMED, PAID, FULFILLED, CANCELLED
    items = Column(JSON, nullable=False)
    total_amount = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class OutboxEvent(Base):
    """Outbox pattern for reliable Kafka publishing."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "uq_order_fulfilled_once", "order_id", unique=True,
            postgresql_where=text("event_type = 'order.fulfilled'"),
            sqlite_where=text("event_type = 'order.fulfilled'"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    event_data = Column(Text, nullable=False)  # JSON string
    published = Column(String(1), default="N", nullable=False)  # Y or N
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    published_at = Column(DateTime, nullable=True)
    claim_token = Column(String(36), nullable=True)
    claimed_until = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(Text, nullable=True)


class ProcessedEvent(Base):
    """Track processed events for idempotency."""

    __tablename__ = "processed_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    processed_at = Column(DateTime, server_default=func.now(), nullable=False)
