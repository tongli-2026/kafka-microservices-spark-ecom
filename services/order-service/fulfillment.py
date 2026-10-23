"""Queue one durable fulfillment event for each eligible paid order."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists

from events import OrderFulfilledEvent
from models import Order, OutboxEvent
from repository import OrderRepository


def queue_fulfillment_events(session_factory, delay_seconds=5, batch_size=10, now=None):
    """Atomically claim eligible orders and add their stable outbox event."""
    now = now or datetime.now(ZoneInfo("America/Los_Angeles"))
    cutoff = now - timedelta(seconds=delay_seconds)
    with session_factory.begin() as db:
        already_queued = exists().where(
            OutboxEvent.order_id == Order.order_id,
            OutboxEvent.event_type == "order.fulfilled",
        )
        orders = db.query(Order).filter(
            Order.status == "PAID",
            Order.updated_at <= cutoff,
            ~already_queued,
        ).order_by(Order.updated_at, Order.id).with_for_update(of=Order, skip_locked=True).limit(batch_size).all()
        repo = OrderRepository(db)
        for order in orders:
            event = OrderFulfilledEvent(
                order_id=order.order_id,
                user_id=order.user_id,
                correlation_id=order.correlation_id,
                tracking_number=f"TRK-{order.order_id[-8:]}",
                shipped_at=now,
            )
            repo.add_outbox_event(order.order_id, "order.fulfilled", event.model_dump_json())
        return len(orders)
