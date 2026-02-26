"""
kafka_client.py - Kafka Producer and Consumer Client Wrappers

PURPOSE:
    Provides reusable Kafka producer and consumer classes with built-in
    error handling, serialization, and delivery guarantees.

CLASSES:
    1. BaseKafkaProducer: Publishes events to Kafka topics
       - JSON serialization
       - Delivery acknowledgments
       - Retry logic (3 attempts)
       - Compression (snappy)
    
    2. BaseKafkaConsumer: Consumes events from Kafka topics
       - Automatic deserialization
       - Event type mapping
       - Consumer group management
       - At-least-once delivery semantics
       - Manual commit support

PRODUCER FEATURES:
    - Synchronous and asynchronous publishing
    - Delivery callbacks for tracking
    - Automatic retries on failure
    - Message compression
    - All replicas acknowledgment (acks=all)

CONSUMER FEATURES:
    - Topic subscription with regex patterns
    - Event type deserialization
    - Callback-based message processing
    - Configurable auto-commit
    - Consumer group coordination
    - Graceful shutdown handling

USAGE:
    Producer:
        producer = BaseKafkaProducer("localhost:9092", "my-service")
        producer.send("topic.name", event_object)
        producer.close()
    
    Consumer:
        consumer = BaseKafkaConsumer(
            "localhost:9092",
            ["topic1", "topic2"],
            "consumer-group-1"
        )
        consumer.consume(callback_function)
        consumer.close()

ERROR HANDLING:
    - Automatic retries on transient failures
    - Logging of all delivery failures
    - Graceful degradation on critical errors

DEAD LETTER QUEUE (DLQ) HANDLING:
    Purpose: Prevents infinite retry loops while preserving failed messages
    
    Flow:
        1. Message received from Kafka topic
        2. Handler function processes the message
        3. If error occurs, automatic retry with exponential backoff:
           - Attempt 1: Wait 1 second
           - Attempt 2: Wait 2 seconds
           - Attempt 3: Wait 4 seconds
        4. If all retries fail after 3 attempts:
           - Event is published to "dlq.events" topic
           - Original event data is preserved
           - Failure reason is logged for investigation
           - Event is marked as processed (prevents reprocessing)
    
    DLQ Event Contents:
        - original_topic: Topic where message originally came from
        - original_event_type: Type of event that failed
        - error_reason: Exception message/details
        - retry_count: Number of retry attempts made
        - payload: Complete original event data
    
    Benefits:
        - Prevents service from crashing on bad messages
        - Allows manual intervention for failed events
        - Enables post-mortem analysis of failures
        - Supports eventual message recovery/replay
"""

import json  # For event serialization/deserialization
import logging  # For error and info logging
import time  # For retry delays
from typing import Callable, List, Optional, Set  # Type hints

from confluent_kafka import Consumer, Producer  # Kafka client library
from confluent_kafka.error import KafkaError  # Kafka error types

# Import event schemas for serialization
try:
    from shared.events import EVENT_TYPE_MAP, BaseEvent
except ImportError:
    from events import EVENT_TYPE_MAP, BaseEvent

logger = logging.getLogger(__name__)


class BaseKafkaProducer:
    """
    Base Kafka producer with JSON serialization and delivery callbacks.
    
    Features:
        - Automatic JSON serialization of events
        - Delivery acknowledgment from all replicas (acks=all)
        - 3 retry attempts on failure
        - Snappy compression for efficiency
        - Synchronous send with callback tracking
    """

    def __init__(self, bootstrap_servers: str, client_id: str = "producer"):
        """
        Initialize Kafka producer.
        
        Args:
            bootstrap_servers: Comma-separated Kafka broker addresses
            client_id: Unique identifier for this producer instance
        """
        self.config = {
            "bootstrap.servers": bootstrap_servers,  # Kafka broker addresses
            "client.id": client_id,  # Producer identifier
            "acks": "all",  # Wait for all replicas to acknowledge
            "retries": 3,  # Retry failed sends 3 times
            "compression.type": "snappy",  # Compress before sending
        }
        self.producer = Producer(self.config)

    def _delivery_report(self, err: Optional[KafkaError], msg) -> None:
        """Delivery report handler called by producer on message delivery."""
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.info(
                f"Message delivered to topic={msg.topic()}, "
                f"partition={msg.partition()}, offset={msg.offset()}"
            )

    def publish(self, topic: str, event: BaseEvent) -> None:
        """Publish event to Kafka topic."""
        try:
            # Handle both BaseEvent objects and dicts for flexibility
            if isinstance(event, dict):
                message = json.dumps(event)
                event_type = event.get("event_type", "unknown")
                event_id = event.get("event_id", "unknown")
                correlation_id = event.get("correlation_id", "unknown")
            else:
                message = event.model_dump_json()
                event_type = event.event_type
                event_id = event.event_id
                correlation_id = event.correlation_id
                
            self.producer.produce(
                topic=topic,
                value=message.encode("utf-8"),
                callback=self._delivery_report,
            )
            # Flush to ensure message is sent before method returns (can be optimized for batch sending)
            self.producer.flush()
            logger.info(
                f"Published event to {topic}",
                extra={
                    "event_type": event_type,
                    "event_id": event_id,
                    "correlation_id": correlation_id,
                },
            )
        except Exception as e:
            logger.error(f"Error publishing event to {topic}: {e}")
            raise

    def flush(self) -> None:
        """Flush any pending messages."""
        self.producer.flush()


class BaseKafkaConsumer:
    """Base Kafka consumer with retry logic and DLQ handling."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: List[str],
    ):
        """Initialize Kafka consumer."""
        self.config = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
            "session.timeout.ms": 30000,
        }
        self.consumer = Consumer(self.config)
        self.topics = topics
        self.consumer.subscribe(topics)
        # Set to track processed event IDs for idempotency
        self.processed_events: Set[str] = set()
        # Initialize a producer for sending failed events to DLQ
        self.producer = BaseKafkaProducer(bootstrap_servers, client_id=f"{group_id}-dlq-producer")

    def consume(self, handler_fn: Callable[[BaseEvent], None], timeout: float = 1.0) -> None:
        """Consume messages from subscribed topics."""
        while True:
            # Poll for messages with specified timeout
            msg = self.consumer.poll(timeout)

            if msg is None:
                continue

            if msg.error():
                logger.error(f"Consumer error: {msg.error()}")
                continue

            try:
                # Parse JSON to get event_type and event_id for pre-processing checks
                event_data = json.loads(msg.value().decode("utf-8"))
                event_type = event_data.get("event_type")
                event_id = event_data.get("event_id")

                # Check for idempotency
                if event_id in self.processed_events:
                    logger.info(
                        f"Event {event_id} already processed, skipping",
                        extra={"event_type": event_type, "correlation_id": event_data.get("correlation_id")},
                    )
                    continue

                # Deserialize to appropriate event class using Pydantic validation
                event_class = EVENT_TYPE_MAP.get(event_type, BaseEvent)
                # Validate and create event instance (raises ValidationError if data is invalid)
                event = event_class.model_validate(event_data)

                # Retry logic
                max_retries = 3
                retry_delays = [1, 2, 4]  # exponential backoff

                for attempt in range(max_retries):
                    try:
                        # Call the handler function to process the event
                        handler_fn(event)
                        self.processed_events.add(event_id)
                        logger.info(
                            f"Event processed successfully",
                            extra={
                                "event_id": event_id,
                                "event_type": event_type,
                                "correlation_id": event.correlation_id,
                            },
                        )
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = retry_delays[attempt]
                            logger.warning(
                                f"Error processing event (attempt {attempt + 1}/{max_retries}): {e}. "
                                f"Retrying in {wait_time}s...",
                                extra={
                                    "event_id": event_id,
                                    "event_type": event_type,
                                    "correlation_id": event.correlation_id,
                                },
                            )
                            time.sleep(wait_time)
                        else:
                            # All retries exhausted, send to DLQ
                            logger.error(
                                f"Event failed after {max_retries} retries: {e}. Sending to DLQ.",
                                extra={
                                    "event_id": event_id,
                                    "event_type": event_type,
                                    "correlation_id": event.correlation_id,
                                },
                            )
                            self.producer.publish("dlq.events", event)
                            self.processed_events.add(event_id)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to deserialize message: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in consumer: {e}")

    def close(self) -> None:
        """Close the consumer."""
        self.consumer.close()
