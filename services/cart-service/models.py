"""Durable checkout identity, response, and outgoing event in one record."""

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Checkout(Base):
    __tablename__ = "cart_checkouts"

    checkout_id = Column(String(36), primary_key=True)
    idempotency_key = Column(String(255), unique=True, nullable=True)
    user_id = Column(String(255), nullable=False, index=True)
    response_data = Column(JSON, nullable=False)
    event_data = Column(Text, nullable=False)
    cart_cleared = Column(Boolean, nullable=False, default=False, index=True)
    published = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    published_at = Column(DateTime)
    claim_token = Column(String(36))
    claimed_until = Column(DateTime)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
