import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import and_
from sqlalchemy.orm import Session

from models import Order, OutboxEvent, ProcessedEvent

logger = logging.getLogger(__name__)


class OrderRepository:
    """Repository for order operations."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def create_order(self, user_id: str, items: list, total_amount: float) -> Order:
        """Create a new order."""
        order_id = f"ORD-{uuid4().hex[:12].upper()}"
        order = Order(
            order_id=order_id,
            user_id=user_id,
            items=items,
            total_amount=total_amount,
            status="PENDING",
        )
        self.db.add(order)
        self.db.flush()
        logger.info(f"Created order {order_id} for user {user_id}")
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by order_id."""
        return self.db.query(Order).filter(Order.order_id == order_id).first()

    def update_order_status(self, order_id: str, status: str) -> Optional[Order]:
        """Update order status."""
        order = self.get_order(order_id)
        if order:
            order.status = status
            order.updated_at = datetime.utcnow()
            self.db.flush()
            logger.info(f"Updated order {order_id} status to {status}")
        return order

    def add_outbox_event(self, order_id: str, event_type: str, event_data: str) -> OutboxEvent:
        """Add event to outbox."""
        outbox_event = OutboxEvent(
            order_id=order_id,
            event_type=event_type,
            event_data=event_data,
            published="N",
        )
        self.db.add(outbox_event)
        self.db.flush()
        logger.info(f"Added outbox event {event_type} for order {order_id}")
        return outbox_event

    def get_unpublished_events(self) -> list:
        """Get all unpublished outbox events."""
        return self.db.query(OutboxEvent).filter(OutboxEvent.published == "N").all()

    def mark_event_published(self, event_id) -> None:
        """Mark outbox event as published."""
        event = self.db.query(OutboxEvent).filter(OutboxEvent.id == event_id).first()
        if event:
            event.published = "Y"
            event.published_at = datetime.utcnow()
            self.db.flush()

    def is_event_processed(self, event_id: str) -> bool:
        """Check if event has been processed."""
        return self.db.query(ProcessedEvent).filter(ProcessedEvent.event_id == event_id).first() is not None

    def mark_event_processed(self, event_id: str, event_type: str) -> ProcessedEvent:
        """Mark event as processed."""
        processed_event = ProcessedEvent(
            event_id=event_id,
            event_type=event_type,
        )
        self.db.add(processed_event)
        self.db.flush()
        logger.info(f"Marked event {event_id} as processed")
        return processed_event
