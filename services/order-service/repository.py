import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from models import Order, OutboxEvent, ProcessedEvent

logger = logging.getLogger(__name__)


class OrderRepository:
    """Repository for order operations."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def create_order(self, user_id: str, items: list, total_amount: float, correlation_id: str, checkout_id=None) -> Order:
        """Create a new order."""
        order_id = f"ORD-{uuid4().hex[:12].upper()}"
        order = Order(
            order_id=order_id,
            checkout_id=checkout_id,
            user_id=user_id,
            correlation_id=correlation_id,  # Store correlation_id for saga tracing
            items=items,
            total_amount=total_amount,
            status="PENDING",
        )
        self.db.add(order)
        self.db.flush()
        logger.info(f"Created order {order_id} for user {user_id} (correlation_id: {correlation_id})")
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by order_id."""
        return self.db.query(Order).filter(Order.order_id == order_id).first()

    def get_order_for_update(self, order_id: str) -> Optional[Order]:
        """Serialize all saga transitions for one order until commit."""
        return self.db.query(Order).filter(Order.order_id == order_id).with_for_update().first()

    def get_orders_by_user(self, user_id: str) -> list:
        """Get all orders for a specific user."""
        return self.db.query(Order).filter(Order.user_id == user_id).order_by(Order.created_at.desc()).all()

    def update_order_status(self, order_id: str, status: str) -> Optional[Order]:
        """Update order status."""
        order = self.get_order(order_id)
        if order:
            order.status = status
            order.updated_at = datetime.now(ZoneInfo("America/Los_Angeles"))
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
