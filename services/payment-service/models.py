from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Payment(Base):
    """Payment model."""

    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    payment_id = Column(String(255), unique=True, nullable=False, index=True)
    order_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    method = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)  # SUCCESS, FAILED
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
