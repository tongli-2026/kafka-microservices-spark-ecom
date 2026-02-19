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
       - order.confirmed
       - order.cancelled
    
    3. Payment Events: Payment processing
       - payment.processed
       - payment.failed
    
    4. Inventory Events: Stock management
       - inventory.reserved
       - inventory.low
       - inventory.depleted
    
    5. Notification Events: Email/alert triggers
       - notification.sent

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
    
    Deserializing from JSON:
        event = OrderCreatedEvent.model_validate_json(json_data)

EVENT TYPE MAPPING:
    Maps event_type strings to their corresponding Pydantic classes
    Used by BaseKafkaConsumer for automatic deserialization
"""

from datetime import datetime  # For event timestamps
from typing import Any, Dict, List, Optional  # Type hints
from uuid import UUID, uuid4  # For unique event IDs

from pydantic import BaseModel, Field  # Data validation and serialization


class BaseEvent(BaseModel):
    """
    Base event model for all Kafka events.
    
    All events inherit from this class and include:
    - Unique event ID
    - Event type identifier
    - UTC timestamp
    - Correlation ID for saga orchestration
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))  # Auto-generated unique ID
    event_type: str  # Event category (e.g., "order.created")
    timestamp: datetime = Field(default_factory=datetime.utcnow)  # Event creation time
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
    """Event published when an item is removed from cart."""

    event_type: str = "cart.item_removed"
    user_id: str
    product_id: str


class CartCheckoutInitiatedEvent(BaseEvent):
    """Event published when checkout is initiated."""

    event_type: str = "cart.checkout_initiated"
    user_id: str
    items: List[Dict[str, Any]]
    total_amount: float


# Order Events
class OrderCreatedEvent(BaseEvent):
    """Event published when an order is created."""

    event_type: str = "order.created"
    order_id: str
    user_id: str
    items: List[Dict[str, Any]]
    total_amount: float


class OrderConfirmedEvent(BaseEvent):
    """Event published when an order is confirmed."""

    event_type: str = "order.confirmed"
    order_id: str
    user_id: str


class OrderCancelledEvent(BaseEvent):
    """Event published when an order is cancelled."""

    event_type: str = "order.cancelled"
    order_id: str
    user_id: str
    reason: str


# Payment Events
class PaymentProcessedEvent(BaseEvent):
    """Event published when payment is processed successfully."""

    event_type: str = "payment.processed"
    payment_id: str
    order_id: str
    user_id: str
    amount: float
    currency: str = "USD"
    method: str


class PaymentFailedEvent(BaseEvent):
    """Event published when payment fails."""

    event_type: str = "payment.failed"
    order_id: str
    user_id: str
    reason: str


# Inventory Events
class InventoryReservedEvent(BaseEvent):
    """Event published when inventory is reserved."""

    event_type: str = "inventory.reserved"
    order_id: str
    product_id: str
    quantity: int


class InventoryLowEvent(BaseEvent):
    """Event published when inventory is low."""

    event_type: str = "inventory.low"
    product_id: str
    current_stock: int
    threshold: int = 10


class InventoryDepletedEvent(BaseEvent):
    """Event published when inventory is depleted."""

    event_type: str = "inventory.depleted"
    product_id: str


# Fraud Events
class FraudDetectedEvent(BaseEvent):
    """Event published when fraud is detected."""

    event_type: str = "fraud.detected"
    user_id: str
    order_id: str
    alert_type: str
    details: Dict[str, Any]


# Event mapping for deserialization
EVENT_TYPE_MAP = {
    "cart.item_added": CartItemAddedEvent,
    "cart.item_removed": CartItemRemovedEvent,
    "cart.checkout_initiated": CartCheckoutInitiatedEvent,
    "order.created": OrderCreatedEvent,
    "order.confirmed": OrderConfirmedEvent,
    "order.cancelled": OrderCancelledEvent,
    "payment.processed": PaymentProcessedEvent,
    "payment.failed": PaymentFailedEvent,
    "inventory.reserved": InventoryReservedEvent,
    "inventory.low": InventoryLowEvent,
    "inventory.depleted": InventoryDepletedEvent,
    "fraud.detected": FraudDetectedEvent,
}

ALL_TOPICS = [
    "cart.item_added",
    "cart.item_removed",
    "cart.checkout_initiated",
    "order.created",
    "order.confirmed",
    "order.cancelled",
    "payment.processed",
    "payment.failed",
    "inventory.reserved",
    "inventory.low",
    "inventory.depleted",
    "notification.send",
    "fraud.detected",
    "dlq.events",
]
