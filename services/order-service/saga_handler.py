import json
import logging
import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from models import OutboxEvent
from repository import OrderRepository

logger = logging.getLogger(__name__)


class SagaHandler:
    """Handles saga orchestration for orders."""

    def __init__(self, db_session: Session, producer):
        """Initialize saga handler."""
        self.db = db_session
        self.producer = producer
        self.repo = OrderRepository(db_session)

    def handle_cart_checkout_initiated(self, event) -> None:
        """Handle cart.checkout_initiated event - creates order."""
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            return

        # Create order from cart
        items = event.items
        order = self.repo.create_order(
            user_id=event.user_id,
            items=items,
            total_amount=event.total_amount,
        )

        # Create and add outbox event
        order_created_event = {
            "event_id": event.event_id,
            "event_type": "order.created",
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": event.correlation_id,
            "order_id": order.order_id,
            "user_id": event.user_id,
            "items": items,
            "total_amount": event.total_amount,
        }

        self.repo.add_outbox_event(
            order.order_id,
            "order.created",
            json.dumps(order_created_event),
        )

        # Mark event as processed
        self.repo.mark_event_processed(event.event_id, event.event_type)

        # Commit transaction
        self.db.commit()
        logger.info(f"Order saga started for order {order.order_id}")

    def handle_payment_processed(self, event) -> None:
        """Handle payment.processed event - confirms order."""
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            return

        order = self.repo.get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        self.repo.update_order_status(event.order_id, "PAID")

        # Create outbox event
        order_confirmed_event = {
            "event_id": event.event_id,
            "event_type": "order.confirmed",
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": event.correlation_id,
            "order_id": event.order_id,
            "user_id": event.user_id,
        }

        self.repo.add_outbox_event(
            event.order_id,
            "order.confirmed",
            json.dumps(order_confirmed_event),
        )

        # Mark event as processed
        self.repo.mark_event_processed(event.event_id, event.event_type)

        self.db.commit()
        logger.info(f"Order {event.order_id} confirmed")

    def handle_payment_failed(self, event) -> None:
        """Handle payment.failed event - cancels order."""
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            return

        order = self.repo.get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        self.repo.update_order_status(event.order_id, "CANCELLED")

        # Create outbox event
        order_cancelled_event = {
            "event_id": event.event_id,
            "event_type": "order.cancelled",
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": event.correlation_id,
            "order_id": event.order_id,
            "user_id": event.user_id,
            "reason": event.reason,
        }

        self.repo.add_outbox_event(
            event.order_id,
            "order.cancelled",
            json.dumps(order_cancelled_event),
        )

        # Mark event as processed
        self.repo.mark_event_processed(event.event_id, event.event_type)

        self.db.commit()
        logger.info(f"Order {event.order_id} cancelled due to payment failure")

    def handle_inventory_reserved(self, event) -> None:
        """Handle inventory.reserved event - marks order as fulfilled."""
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            return

        order = self.repo.get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        self.repo.update_order_status(event.order_id, "FULFILLED")
        self.repo.mark_event_processed(event.event_id, event.event_type)

        self.db.commit()
        logger.info(f"Order {event.order_id} fulfilled")


class OutboxPublisher:
    """Background thread to publish outbox events."""

    def __init__(self, db_session: Session, producer, poll_interval: int = 2):
        """Initialize publisher."""
        self.db = db_session
        self.producer = producer
        self.poll_interval = poll_interval
        self.running = True

    def start(self) -> threading.Thread:
        """Start publisher thread."""
        thread = threading.Thread(target=self._publish_loop, daemon=True)
        thread.start()
        logger.info("Outbox publisher started")
        return thread

    def _publish_loop(self) -> None:
        """Poll and publish outbox events."""
        repo = OrderRepository(self.db)
        
        while self.running:
            try:
                unpublished = repo.get_unpublished_events()
                
                for event in unpublished:
                    try:
                        event_data = json.loads(event.event_data)
                        self.producer.publish(event.event_type, event_data)
                        repo.mark_event_published(event.id)
                        self.db.commit()
                        logger.info(f"Published outbox event {event.event_type} for order {event.order_id}")
                    except Exception as e:
                        logger.error(f"Error publishing outbox event: {e}")

                time.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in outbox publisher: {e}")
                time.sleep(self.poll_interval)

    def stop(self) -> None:
        """Stop publisher thread."""
        self.running = False
        logger.info("Outbox publisher stopped")
