from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Payment(Base):
    """Payment model."""

    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    payment_id = Column(String(255), unique=True, nullable=False, index=True)
    order_id = Column(String(255), unique=True, nullable=False, index=True)  # FIX: Unique constraint ensures only one payment per order (idempotency)
    user_id = Column(String(255), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    method = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)  # SUCCESS, FAILED
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class PaymentResult(Base):
    """Result identity for new payments, committed with the payment row."""

    __tablename__ = "payment_results"

    order_id = Column(String(255), primary_key=True)
    event_id = Column(String(36), nullable=False)
    correlation_id = Column(String(255), nullable=False)


class PaymentOutboxEvent(Base):
    """One durable outgoing payment result per order."""

    __tablename__ = "payment_outbox_events"

    order_id = Column(String(255), primary_key=True)
    event_id = Column(String(36), nullable=False, unique=True)
    event_type = Column(String(100), nullable=False)
    event_data = Column(Text, nullable=False)
    published = Column(Boolean, nullable=False, default=False)
    published_at = Column(DateTime, nullable=True)
    claim_token = Column(String(36), nullable=True)
    claimed_until = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
