"""
events.py - Kafka Event Schema Definitions

PURPOSE:
    Defines all event schemas used across microservices for Kafka messaging.
    Uses Pydantic for data validation and serialization.

EVENT CATEGORIES:
    1. Cart Events: Shopping cart operations
       - cart.item_added
       - cart.item_removed
       - cart.checkout_initiated
    
    2. Order Events: Order lifecycle
       - order.created
       - order.reservation_confirmed
       - order.confirmed
       - order.cancelled
    
    3. Inventory Events: Stock management
       - inventory.reserved
       - inventory.low
       - inventory.depleted
    
    4. Payment Events: Payment processing
       - payment.processed
       - payment.failed
    
    5. Notification Events: Email/alert triggers
       - notification.send
    
    6. Fraud Events: Fraud detection
       - fraud.detected
    
    7. System Events: Dead Letter Queue
       - dlq.events (failed message processing)

COMMON FIELDS (BaseEvent):
    - event_id: Unique identifier (UUID)
    - event_type: Event category and action
    - timestamp: UTC timestamp of event creation
    - correlation_id: Links related events in saga workflow

SERIALIZATION:
    - Pydantic models auto-serialize to JSON
    - DateTime fields converted to ISO format
    - UUID fields converted to strings
    - Validation on construction

USAGE:
    Creating an event:
        event = OrderCreatedEvent(
            correlation_id="saga-123",
            order_id="ORD-456",
            user_id="user789",
            items=[...],
            total_amount=99.99
        )
    
    Serializing to JSON:
        json_data = event.model_dump_json()
    
    Deserializing from JSON (from dict):
        event_data = json.loads(json_string)
        event = OrderCreatedEvent.model_validate(event_data)
    
    Deserializing from JSON (from raw JSON string):
        event = OrderCreatedEvent.model_validate_json(json_string)

EVENT TYPE MAPPING:
    Maps event_type strings to their corresponding Pydantic classes
    Used by BaseKafkaConsumer for automatic deserialization
"""

from datetime import datetime, timezone  # For event timestamps with timezone
from zoneinfo import ZoneInfo  # For timezone support
from typing import Any, Dict, List, Optional  # Type hints
from uuid import UUID, uuid4  # For unique event IDs

from pydantic import BaseModel, Field  # Data validation and serialization


class BaseEvent(BaseModel):
    """
    Base event model for all Kafka events.
    
    All events inherit from this class and include:
    - Unique event ID
    - Event type identifier
    - Los Angeles timezone-aware timestamp
    - Correlation ID for saga orchestration
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))  # Auto-generated unique ID
    event_type: str  # Event category (e.g., "order.created")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("America/Los_Angeles")))  # Event creation time (Los Angeles timezone-aware)
    correlation_id: str  # Links related events in workflow

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}  # ISO datetime format


# ============================================================================
# CART EVENTS - Shopping cart operations
# ============================================================================

class CartItemAddedEvent(BaseEvent):
    """
    Event published when an item is added to shopping cart.
    Triggers: Cart Service when user adds product
    Consumers: Analytics (cart abandonment tracking)
    """

    event_type: str = "cart.item_added"
    user_id: str  # User who added the item
    product_id: str  # Product being added
    quantity: int  # Number of units
    price: float  # Price per unit


class CartItemRemovedEvent(BaseEvent):
    """
    Event published when an item is removed from cart.
    Triggers: Cart Service when user removes product
    Consumers: Analytics (cart abandonment tracking)
    """

    event_type: str = "cart.item_removed"
    user_id: str
    product_id: str


class CartCheckoutInitiatedEvent(BaseEvent):
    """
    Event published when checkout is initiated.
    Triggers: Cart Service when user initiates checkout
    Consumers: Order Service (creates order), Analytics (checkout funnel tracking)
    """

    event_type: str = "cart.checkout_initiated"
    user_id: str
    items: List[Dict[str, Any]]
    total_amount: float


# ============================================================================
# ORDER EVENTS - Order lifecycle
# ============================================================================

class OrderCreatedEvent(BaseEvent):
    """
    Event published when an order is created.
    Triggers: Order Service when user creates an order from cart checkout
    Consumers: Inventory Service (attempt to reserve inventory)
    Note: This is the start of the Amazon-style saga - inventory is checked FIRST
    """

    event_type: str = "order.created"
    order_id: str
    user_id: str
    items: List[Dict[str, Any]]
    total_amount: float


class OrderReservationConfirmedEvent(BaseEvent):
    """
    Event published when inventory is successfully reserved for an order.
    Triggers: Inventory Service when stock is available for all order items
    Consumers: Payment Service (process payment)
    Note: Only after inventory is reserved do we attempt payment - this prevents payment failures due to out-of-stock items and reduces customer frustration
    """

    event_type: str = "order.reservation_confirmed"
    order_id: str
    user_id: str
    total_amount: float


class OrderConfirmedEvent(BaseEvent):
    """
    Event published when an order is confirmed (payment successful + inventory reserved).
    Triggers: Order Service when payment is successful
    Consumers: Notification Service (send confirmation email), Analytics (conversion tracking)
    """

    event_type: str = "order.confirmed"
    order_id: str
    user_id: str


class OrderCancelledEvent(BaseEvent):
    """
    Event published when an order is cancelled.
    Triggers: Order Service when user cancels order or payment fails
    Consumers: Inventory Service (release inventory), Notification Service (send cancellation email)
    """

    event_type: str = "order.cancelled"
    order_id: str
    user_id: str
    reason: str


class OrderFulfilledEvent(BaseEvent):
    """
    Order has been fulfilled (shipped/delivered).
    Triggers: Fulfillment Service or fulfillment job after order is paid
    Consumers: Order Service (updates order status to FULFILLED)
    
    Purpose: Transitions order from PAID to FULFILLED status
    """

    event_type: str = "order.fulfilled"
    order_id: str  # Order ID being fulfilled
    user_id: str  # User ID for tracking
    tracking_number: Optional[str] = None  # Shipping tracking number (if applicable)
    shipped_at: datetime = Field(default_factory=lambda: datetime.now(ZoneInfo("America/Los_Angeles")))


# ============================================================================
# INVENTORY EVENTS - Stock management
# ============================================================================

class InventoryReservedEvent(BaseEvent):
    """
    Event published when inventory is reserved.
    Triggers: Inventory Service when order is created
    Consumers: Order Service (confirm order), Notification Service (send reservation email)
    """

    event_type: str = "inventory.reserved"
    order_id: str
    product_id: str
    quantity: int


class InventoryLowEvent(BaseEvent):
    """
    Event published when inventory is low.
    Triggers: Inventory Service when stock falls below threshold
    Consumers: Notification Service (send restock alert), Analytics (stock level tracking)
    """

    event_type: str = "inventory.low"
    product_id: str
    current_stock: int
    threshold: int = 10


class InventoryDepletedEvent(BaseEvent):
    """
    Event published when inventory is depleted.
    Triggers: Inventory Service when stock reaches zero
    Consumers: Notification Service (send out-of-stock alert), Analytics (stock level tracking)
    """

    event_type: str = "inventory.depleted"
    product_id: str


# ============================================================================
# PAYMENT EVENTS - Payment processing
# ============================================================================

class PaymentProcessedEvent(BaseEvent):
    """
    Event published when payment is processed successfully.
    Triggers: Payment Service when payment is successful
    Consumers: Order Service (confirm order), Notification Service (send receipt email), Analytics (revenue tracking)
    """

    event_type: str = "payment.processed"
    payment_id: str
    order_id: str
    user_id: str
    amount: float
    currency: str = "USD"
    method: str


class PaymentFailedEvent(BaseEvent):
    """
    Event published when payment fails.
    Triggers: Payment Service when payment fails
    Consumers: Order Service (cancel order), Notification Service (send failure email), Analytics (payment failure tracking)
    """

    event_type: str = "payment.failed"
    order_id: str
    user_id: str
    reason: str


# ============================================================================
# FRAUD EVENTS - Fraud detection and prevention
# ============================================================================

class FraudDetectedEvent(BaseEvent):
    """
    Event published when fraud is detected.
    Triggers: Fraud Detection Service when suspicious activity is identified
    Consumers: Order Service (flag order), Notification Service (send alert), Analytics (fraud tracking)
    """

    event_type: str = "fraud.detected"
    user_id: str
    order_id: str
    alert_type: str
    details: Dict[str, Any]


# ============================================================================
# NOTIFICATION EVENTS - Email and alert notifications
# ============================================================================

class NotificationSendEvent(BaseEvent):
    """
    Event published when a notification should be sent.
    Triggers: Order Service or other services when notifications are needed
    Consumers: Notification Service (sends emails via Mailhog)
    """

    event_type: str = "notification.send"
    user_id: str
    recipient_email: str
    notification_type: str  # e.g., "order_confirmation", "payment_failed", "inventory_low"
    data: Dict[str, Any]  # Notification-specific data (order details, etc.)


# ============================================================================
# DLQ EVENTS - Dead Letter Queue (failed message processing)
# ============================================================================

class DLQEvent(BaseEvent):
    """
    Event published when message processing fails after retries.
    Triggers: Any service that fails to process a message after retry attempts
    Consumers: DLQ Handler (manual review and replay logic)
    
    Purpose: Prevents infinite retry loops while preserving failed messages for investigation
    """

    event_type: str = "dlq.events"
    original_topic: str  # Topic where the message originally came from
    original_event_type: str  # Event type that failed
    error_reason: str  # Why processing failed
    retry_count: int  # Number of retry attempts made
    payload: Dict[str, Any]  # Original event data that failed


# Event mapping for deserialization
EVENT_TYPE_MAP = {
    "cart.item_added": CartItemAddedEvent,
    "cart.item_removed": CartItemRemovedEvent,
    "cart.checkout_initiated": CartCheckoutInitiatedEvent,
    "order.created": OrderCreatedEvent,
    "order.reservation_confirmed": OrderReservationConfirmedEvent,
    "order.confirmed": OrderConfirmedEvent,
    "order.cancelled": OrderCancelledEvent,
    "order.fulfilled": OrderFulfilledEvent,
    "inventory.reserved": InventoryReservedEvent,
    "inventory.low": InventoryLowEvent,
    "inventory.depleted": InventoryDepletedEvent,
    "payment.processed": PaymentProcessedEvent,
    "payment.failed": PaymentFailedEvent,
    "notification.send": NotificationSendEvent,
    "fraud.detected": FraudDetectedEvent,
    "dlq.events": DLQEvent,
}

ALL_TOPICS = [
    "cart.item_added",
    "cart.item_removed",
    "cart.checkout_initiated",
    "order.created",
    "order.reservation_confirmed",
    "order.confirmed",
    "order.cancelled",
    "order.fulfilled",
    "inventory.reserved",
    "inventory.low",
    "inventory.depleted",
    "payment.processed",
    "payment.failed",
    "notification.send",
    "fraud.detected",
    "dlq.events",
]
