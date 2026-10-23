"""Durable state for one logical email notification."""

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id = Column(String(64), primary_key=True)
    source_event_id = Column(String(255), nullable=False)
    notification_type = Column(String(100), nullable=False)
    channel = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, server_default="PENDING")
    attempts = Column(Integer, nullable=False, server_default="0")
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    sent_at = Column(DateTime, nullable=True)
