"""
saga_handler.py - Saga Orchestration for Order Processing

PURPOSE:
    Implements the Saga Choreography pattern for distributed order transactions.
    Coordinates events across multiple microservices to ensure data consistency
    without requiring a centralized transaction manager.

SAGA PATTERN OVERVIEW:
    The Saga pattern breaks down a distributed transaction into a sequence of 
    compensating transactions. Each service publishes an event after completing 
    its business logic, triggering the next service in the workflow.

PRODUCTION-STYLE ORDER FLOW (Inventory-First):
    ┌─────────────────────────────────────────────────────────────────┐
    │  Step 1: User adds items to cart and checks out                 │
    │  Cart Service publishes: cart.checkout_initiated                │ 
    └─────────────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────────────┐
    │  Step 2: Order Service receives checkout event                  │
    │  - Create order in PENDING status                               │
    │  - Publish order.created event (via Outbox Pattern)             │
    │  Method: handle_cart_checkout_initiated()                       │
    └─────────────────────────────────────────────────────────────────┘
                            ↓
    ┌─────────────────────────────────────────────────────────────────┐
    │  Step 3: Inventory Service receives order.created               │
    │  - Check stock availability                                     │
    │  - Reserve inventory if available                               │
    │  - Publish inventory.reserved or inventory.depleted             │
    └─────────────────────────────────────────────────────────────────┘
                    ├─ IF STOCK AVAILABLE: inventory.reserved ─────┐
                    │                                              │
                    └─ IF STOCK IS INSUFFICIENT or DEPLETED: ──┐   │
                                                               │   │
        ┌──────────────────────────────────────────────────────┘   └─┐
        ↓                                                            ↓
    ┌─────────────────────────────────────────────────────────┐    ┌─────────────────────────────────────────────────────┐
    │  Step 4a: Order CANCELLED (insufficient stock)          │    │  Step 4b: Order Service receives inventory.reserved │
    │  - Receive inventory.depleted event                     │    │  - Update order status to RESERVATION_CONFIRMED     │
    │  - Update order status to CANCELLED                     │    │  - Publish order.reservation_confirmed event        │
    │  - Publish order.cancelled event                        │    │  - Proceed to payment processing                    │
    │  - NO PAYMENT CHARGED ✓                                 │    │                                                     │
    │  - NO STOCK RELEASE (never reserved)                    │    │  Method: handle_inventory_reserved()                │
    │  Method: handle_inventory_depleted()                    │    │  ⭐ KEY POINT: This is BEFORE payment               │
    │  ⭐ Inventory-First Advantage: No refunds needed        │    │  ✓ Guarantees inventory availability for payment    │
    └─────────────────────────────────────────────────────────┘    └─────────────────────────────────────────────────────┘
                                                                                         ↓
                                                                    ┌─────────────────────────────────────────────────────┐
                                                                    │  Step 5: Payment Service receives order.            │
                                                                    │          reservation_confirmed                      │
                                                                    │  - Process payment with confirmed order amount      │
                                                                    │  - Publish payment.processed or payment.failed      │
                                                                    └─────────────────────────────────────────────────────┘
                                                                            ├─ IF PAYMENT SUCCEEDS ─────┐
                                                                            │                           │
                                                                            └─ IF PAYMENT FAILS ────┐   │
                                                                                                    │   │
                                                    ┌───────────────────────────────────────────────┘   │
                                                    ↓                                                   ↓
                    ┌─────────────────────────────────────────────────────┐    ┌─────────────────────────────────────────────────────┐
                    │  Step 6a: Order CANCELLED (payment failed)          │    │  Step 6b: Order PAID (payment successful)           │
                    │  - Receive payment.failed event                     │    │  - Receive payment.processed event                  │
                    │  - Update order status to CANCELLED                 │    │  - Update order status to PAID                      │
                    │  - Publish order.cancelled event                    │    │  - Publish order.confirmed event                    │
                    │  Method: handle_payment_failed()                    │    │  Method: handle_payment_processed()                 │
                    │  ✓ NO CHARGE + inventory released = no refund       │    │  ✓ Customer charged                                 │
                    │                                                     │    │  ✓ Inventory reserved + Payment successful = PAID   │
                    └─────────────────────────────────────────────────────┘    └─────────────────────────────────────────────────────┘

KEY ADVANTAGES vs PAYMENT-FIRST FLOW:
    ✓ Inventory checked BEFORE charging customer
    ✓ No refunds needed if item goes out of stock
    ✓ Better customer experience (charge = guaranteed fulfillment)
    ✓ Matches production e-commerce systems (Amazon, Shopify, etc.)
    ✓ Lower support/refund costs

OUTBOX PATTERN:
    All events published by Order Service use the Outbox Pattern:
    1. Event stored in outbox_events table (guaranteed durable storage)
    2. OutboxPublisher background thread polls every 2 seconds
    3. Polls unpublished events and publishes to Kafka
    4. Marks as published in database after Kafka confirms
    5. If service crashes between DB commit and Kafka publish, 
       the OutboxPublisher will retry on restart

IDEMPOTENCY:
    All event handlers check if event was already processed:
    - Repository.is_event_processed(event_id) prevents duplicate handling
    - Saga handlers are idempotent and can safely be called multiple times
    - Ensures consistency even if events are redelivered by Kafka

DATABASE SCHEMA:
    outbox_events table:
    - id: Primary key (auto-increment)
    - order_id: Foreign key to orders
    - event_type: Type of event (order.created, order.reservation_confirmed, etc.)
    - event_data: JSON payload with all event details
    - created_at: Timestamp when event was created
    - published_at: Timestamp when event was published to Kafka (NULL until published)
    - updated_at: Last update timestamp

EVENT HANDLERS (SagaHandler class):
    1. handle_cart_checkout_initiated(event)
       - Input: cart.checkout_initiated from Cart Service
       - Creates new Order in PENDING status
       - Publishes order.created event to trigger inventory reservation
       - Marks event processed to ensure idempotency

    2. handle_inventory_reserved(event) ⭐ KEY METHOD
       - Input: inventory.reserved from Inventory Service
       - Updates order status to RESERVATION_CONFIRMED (inventory is safely reserved)
       - Publishes order.reservation_confirmed event to trigger Payment Service
       - This is the CRITICAL POINT where we confirm inventory before payment
       - Marks event processed to ensure idempotency

    2b. handle_inventory_depleted(event) ⭐ INVENTORY-FIRST ADVANTAGE
       - Input: inventory.depleted from Inventory Service
       - Indicates insufficient stock to fulfill order
       - Updates order status to CANCELLED (NO PAYMENT PROCESSED)
       - Publishes order.cancelled event with cancellation_source="inventory_depleted"
       - Marks event processed to ensure idempotency
       - KEY: Stock was NEVER reserved, so NO stock release needed
       - ✓ No refunds needed (customer never charged in the first place)

    3. handle_payment_processed(event)
       - Input: payment.processed from Payment Service
       - Updates order status to PAID
       - Publishes order.confirmed event (order is fulfilled)
       - Marks event processed to ensure idempotency

    4. handle_payment_failed(event)
       - Input: payment.failed from Payment Service
       - Updates order status to CANCELLED
       - Publishes order.cancelled event with cancellation_source="payment_failed"
       - Marks event processed to ensure idempotency
       - Inventory Service receives order.cancelled and auto-releases reserved stock

OUTBOX PUBLISHER (OutboxPublisher class):
    Background thread that ensures reliable event publishing:
    - Runs continuously in daemon thread
    - Polls unpublished events every 2 seconds (configurable)
    - Publishes to Kafka with error handling
    - Marks as published only after Kafka confirms receipt
    - Catches and logs errors without crashing

TIMEZONE:
    All timestamps use: datetime.now(ZoneInfo("America/Los_Angeles"))
    Ensures consistent timestamp handling across all services

ERROR HANDLING:
    - Idempotency check prevents duplicate processing
    - Unpublished events persist in database (guaranteed retry on restart)
    - All exceptions logged but don't crash the handler
    - OutboxPublisher continues running even if individual event publishing fails

TESTING SCENARIOS:
    1. Successful Purchase:
       order.created → inventory.reserved → order.reservation_confirmed → 
       payment.processed → order.confirmed ✓

    2. Out of Stock:
       order.created → inventory.depleted (NOT reservation_confirmed) → 
       order.cancelled (NO CHARGE) ✓

    3. Payment Failure:
       order.created → inventory.reserved → order.reservation_confirmed → 
       payment.failed → order.cancelled (inventory auto-released by Inventory Service) ✓
"""

import json
import logging
import threading
import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from repository import OrderRepository
from shared.metrics import (
    track_order_status,
    track_order_duration,
    track_saga_step,
    track_saga_compensation,
    track_deduplicated_event,
)

logger = logging.getLogger(__name__)


class SagaHandler:
    """Handles saga orchestration for orders."""

    def __init__(self, db_session: Session):
        """Initialize saga handler."""
        self.db = db_session
        self.repo = OrderRepository(db_session)

    def handle_cart_checkout_initiated(self, event) -> None:
        """Handle cart.checkout_initiated event - creates order."""
        # Idempotency check to prevent duplicate handling
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            # Track deduplicated event
            track_deduplicated_event("order-service")
            return

        # Create order from cart
        items = event.items
        order = self.repo.create_order(
            user_id=event.user_id,
            items=items,
            total_amount=event.total_amount,
            correlation_id=event.correlation_id,  # Store correlation_id for saga tracing
        )

        # Track order creation
        track_order_status("order-service", "created")

        # Create and add outbox event
        order_created_event = {
            "event_id": event.event_id,
            "event_type": "order.created",
            "timestamp": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
            "correlation_id": event.correlation_id,
            "order_id": order.order_id,
            "user_id": event.user_id,
            "items": items,
            "total_amount": event.total_amount,
        }

        # Add outbox event to trigger inventory reservation
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
        
        # Track saga step (inventory reservation coming next)
        track_saga_step("order-service", "inventory", success=None)
    
    def handle_inventory_reserved(self, event) -> None:
        """
        Handle inventory.reserved event from Inventory Service.
        Production-style flow: Inventory reserved BEFORE payment.
        Now that inventory is reserved, trigger payment processing.
        """
        # Idempotency check to prevent duplicate handling
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            # Track deduplicated event
            track_deduplicated_event("order-service")
            return

        order = self.repo.get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        # Update order status to reflect inventory is reserved
        self.repo.update_order_status(event.order_id, "RESERVATION_CONFIRMED")

        # Track successful inventory reservation step
        track_saga_step("order-service", "inventory", success=True)

        # Create outbox event to trigger payment processing
        # Now that inventory is reserved, we can safely process payment
        order_reservation_confirmed_event = {
            "event_id": event.event_id,
            "event_type": "order.reservation_confirmed",
            "timestamp": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
            "correlation_id": event.correlation_id,
            "order_id": event.order_id,
            "user_id": order.user_id,
            "total_amount": order.total_amount,
        }

        self.repo.add_outbox_event(
            order.order_id,
            "order.reservation_confirmed",
            json.dumps(order_reservation_confirmed_event),
        )

        # Mark event as processed
        self.repo.mark_event_processed(event.event_id, event.event_type)

        self.db.commit()
        logger.info(f"Order {event.order_id} reservation confirmed, triggering payment")

    def handle_inventory_depleted(self, event) -> None:
        """
        Handle inventory.depleted event from Inventory Service.
        Inventory is not available - cancel order WITHOUT charging customer.
        This is the key advantage of inventory-first flow: no refunds needed.
        """
        # Idempotency check to prevent duplicate handling
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            # Track deduplicated event
            track_deduplicated_event("order-service")
            return

        # Get order details
        order = self.repo.get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        # Cancel order (PENDING → CANCELLED)
        self.repo.update_order_status(event.order_id, "CANCELLED")

        # Track failed inventory reservation step (and compensation via cancellation)
        track_saga_step("order-service", "inventory", success=False)
        track_saga_compensation("order-service", "inventory")
        track_order_status("order-service", "cancelled")

        # Create outbox event to notify customer of cancellation
        # Include cancellation_source to help downstream services understand WHY it was cancelled
        order_cancelled_event = {
            "event_id": str(uuid4()),  # Generate new unique event_id for this cancellation event
            "event_type": "order.cancelled",
            "timestamp": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
            "correlation_id": event.correlation_id,
            "order_id": event.order_id,
            "user_id": order.user_id,  # Get from order record, not from event
            "reason": getattr(event, 'reason', f"Out of stock or insufficient stock: {event.product_id}"),
            "cancellation_source": "inventory_depleted",  # ← Key field: tells Inventory Service NOT to release stock
        }

        self.repo.add_outbox_event(
            order.order_id,
            "order.cancelled",
            json.dumps(order_cancelled_event),
        )

        # Mark event as processed to ensure idempotency
        self.repo.mark_event_processed(event.event_id, event.event_type)

        self.db.commit()
        logger.info(f"Order {event.order_id} cancelled due to inventory depletion or insufficient stock (NO PAYMENT CHARGED)")
        logger.debug(f"Outbox event created: {json.dumps(order_cancelled_event)}")

    def handle_payment_processed(self, event) -> None:
        """Handle payment.processed event - confirms order."""
        # Idempotency check to prevent duplicate handling
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            # Track deduplicated event
            track_deduplicated_event("order-service")
            return

        order = self.repo.get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        self.repo.update_order_status(event.order_id, "PAID")

        # Track successful payment step
        track_saga_step("order-service", "payment", success=True)
        track_order_status("order-service", "confirmed")
        
        # Track order processing duration (from creation to payment completion)
        if order.created_at:
            # Handle both naive and aware datetimes
            now = datetime.now(ZoneInfo("America/Los_Angeles"))
            created_at = order.created_at
            
            # If created_at is naive, make it aware by assuming it's in LA timezone
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=ZoneInfo("America/Los_Angeles"))
            
            duration = (now - created_at).total_seconds()
            track_order_duration("order-service", duration)
            logger.info(f"Order {event.order_id} processing duration: {duration:.2f}s")

        # Create outbox event
        order_confirmed_event = {
            "event_id": event.event_id,
            "event_type": "order.confirmed",
            "timestamp": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
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
        # Idempotency check to prevent duplicate handling
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            # Track deduplicated event
            track_deduplicated_event("order-service")
            return

        order = self.repo.get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        self.repo.update_order_status(event.order_id, "CANCELLED")

        # Track failed payment step and compensation (inventory release)
        track_saga_step("order-service", "payment", success=False)
        track_saga_compensation("order-service", "payment")
        track_order_status("order-service", "cancelled")

        # Create outbox event
        # Include cancellation_source to help downstream services understand WHY it was cancelled
        order_cancelled_event = {
            "event_id": event.event_id,  # Reuse event_id since Notification Service doesn't consume payment.failed
            "event_type": "order.cancelled",
            "timestamp": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
            "correlation_id": event.correlation_id,
            "order_id": event.order_id,
            "user_id": event.user_id,
            "reason": getattr(event, 'reason', "Payment processing failed"),
            "cancellation_source": "payment_failed",  # ← Key field: tells Inventory Service TO release reserved stock
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
        logger.debug(f"Outbox event created: {json.dumps(order_cancelled_event)}")

    def handle_order_fulfilled(self, event) -> None:
        """Handle order.fulfilled event from fulfillment service/job."""
        # Idempotency check to prevent duplicate handling
        if self.repo.is_event_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed")
            return

        order = self.repo.get_order(event.order_id)
        if not order:
            logger.error(f"Order {event.order_id} not found")
            return

        self.repo.update_order_status(event.order_id, "FULFILLED")

        # Mark event as processed for idempotency
        self.repo.mark_event_processed(event.event_id, event.event_type)

        self.db.commit()
        logger.info(f"Order {event.order_id} fulfilled (status updated to FULFILLED)")


class OutboxPublisher:
    """Background thread to publish outbox events every few seconds."""

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
                
                if unpublished:
                    logger.info(f"Found {len(unpublished)} unpublished outbox events")
                
                for event in unpublished:
                    try:
                        event_data = json.loads(event.event_data)
                        logger.info(f"Publishing outbox event: topic={event.event_type}, order_id={event.order_id}, event_id={event_data.get('event_id')}")
                        self.producer.publish(event.event_type, event_data)
                        repo.mark_event_published(event.id)
                        self.db.commit()
                        logger.info(f"Successfully published outbox event {event.event_type} for order {event.order_id}")
                    except Exception as e:
                        logger.error(f"Error publishing outbox event: {e}", exc_info=True)

                time.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"Error in outbox publisher: {e}", exc_info=True)
                time.sleep(self.poll_interval)

    def stop(self) -> None:
        """Stop publisher thread."""
        self.running = False
        logger.info("Outbox publisher stopped")
