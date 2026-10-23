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
    - Synchronous offset commit after handling or confirmed DLQ delivery
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
           - Source offset is committed only after DLQ delivery is confirmed
    
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

# Prometheus metrics for monitoring
try:
    from prometheus_client import Counter, Gauge, Histogram
    
    # DLQ Metrics
    dlq_messages_sent_total = Counter(
        'dlq_messages_sent_total',
        'Total messages sent to DLQ',
        ['original_topic', 'error_type']
    )
    
    dlq_message_count = Gauge(
        'dlq_message_count',
        'Current number of messages in DLQ'
    )
    
    # Producer Metrics
    kafka_messages_published_total = Counter(
        'kafka_messages_published_total',
        'Total Kafka messages published',
        ['topic', 'event_type']
    )
    
    kafka_publish_errors_total = Counter(
        'kafka_publish_errors_total',
        'Total Kafka publish errors',
        ['topic', 'error_type']
    )
    
    # Consumer Metrics
    kafka_messages_consumed_total = Counter(
        'kafka_messages_consumed_total',
        'Total Kafka messages consumed and processed',
        ['topic', 'event_type', 'status']  # status: success, error, dlq
    )
    
    kafka_message_processing_duration_seconds = Histogram(
        'kafka_message_processing_duration_seconds',
        'Time taken to process a Kafka message',
        ['topic', 'event_type'],
        buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0)
    )
    
    # Retry Metrics
    kafka_retry_attempts_total = Counter(
        'kafka_retry_attempts_total',
        'Total retry attempts made',
        ['topic', 'event_type', 'attempt_number']
    )
    
    has_prometheus = True
except ImportError:
    has_prometheus = False
    logger_msg = "⚠️  Prometheus client not installed. Metrics collection disabled."

# Import event schemas for serialization
try:
    from shared.events import EVENT_TYPE_MAP, BaseEvent
except ImportError:
    from events import EVENT_TYPE_MAP, BaseEvent

logger = logging.getLogger(__name__)

# Log Prometheus status at module load time
if not has_prometheus:
    logger.warning(logger_msg)


class KafkaDeliveryError(RuntimeError):
    """The broker did not confirm delivery of a produced message."""


class RetryableProcessingError(RuntimeError):
    """Business work is unfinished; keep the source offset uncommitted."""


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
        """Publish and return only after Kafka confirms this message."""
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
                
            delivery_errors = []
            delivered = []

            def delivery_report(err, msg):
                self._delivery_report(err, msg)
                if err is not None:
                    delivery_errors.append(err)
                else:
                    delivered.append(msg)

            try:
                self.producer.produce(
                    topic=topic,
                    value=message.encode("utf-8"),
                    callback=delivery_report,
                )
                remaining = self.producer.flush(timeout=30)
            except Exception as error:
                raise KafkaDeliveryError(f"Failed to deliver to {topic}: {error}") from error
            # flush() can report another thread's pending message. This
            # message is successful only when its own callback confirms it.
            if delivery_errors or not delivered:
                raise KafkaDeliveryError(
                    f"Kafka did not confirm delivery to {topic}: "
                    f"pending={remaining}, errors={delivery_errors}"
                )
            
            # Record metrics
            if has_prometheus:
                kafka_messages_published_total.labels(topic=topic, event_type=event_type).inc()
            
            logger.info(
                f"Published event to {topic}",
                extra={
                    "event_type": event_type,
                    "event_id": event_id,
                    "correlation_id": correlation_id,
                },
            )
        except Exception as e:
            # Record error metric
            if has_prometheus:
                kafka_publish_errors_total.labels(
                    topic=topic, 
                    error_type=type(e).__name__
                ).inc()
            
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
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
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
        """Process one message at a time and commit only after a durable outcome."""
        while True:
            try:
                msg = self.consumer.poll(timeout)
                if msg is None:
                    continue
                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue
                self._process_message(msg, handler_fn)
            except Exception as e:
                # Never poll a later offset after a failed commit or DLQ send.
                # Rejoining the group resumes from the last committed offset.
                logger.exception("Consumer could not finish message; rejoining group")
                try:
                    self.consumer.close()
                except Exception:
                    logger.exception("Failed to close consumer after error")
                time.sleep(1)
                self.consumer = Consumer(self.config)
                self.consumer.subscribe(self.topics)

    def _commit_message(self, msg) -> None:
        committed = self.consumer.commit(message=msg, asynchronous=False)
        if not committed:
            raise RuntimeError("Kafka returned no committed offset")
        for partition in committed:
            if partition.error is not None:
                raise RuntimeError(f"Kafka offset commit failed: {partition.error}")

    def _send_to_dlq(self, msg, event_data, error, retry_count: int) -> None:
        data = event_data if isinstance(event_data, dict) else {}
        dlq_message = {
            "original_topic": msg.topic(),
            "original_event_type": data.get("event_type"),
            "event_id": data.get("event_id"),
            "correlation_id": data.get("correlation_id"),
            "error_reason": str(error),
            "error_type": type(error).__name__,
            "retry_count": retry_count,
            "payload": event_data,
            "timestamp": time.time(),
        }
        # publish() raises unless the broker confirms delivery.
        self.producer.publish("dlq.events", dlq_message)

    def _process_message(self, msg, handler_fn: Callable[[BaseEvent], None]) -> None:
        raw_bytes = msg.value()
        raw_value = raw_bytes.decode("utf-8", errors="replace") if raw_bytes is not None else None
        event_data = raw_value
        try:
            if raw_value is None:
                raise ValueError("Kafka event value is null")
            event_data = json.loads(raw_value)
            if not isinstance(event_data, dict):
                raise ValueError("Kafka event must be a JSON object")
            if not event_data.get("event_id"):
                raise ValueError("Kafka event is missing event_id")
            event_class = EVENT_TYPE_MAP.get(event_data.get("event_type"))
            if event_class is None:
                raise ValueError(f"Unknown Kafka event_type: {event_data.get('event_type')}")
            event = event_class.model_validate(event_data)
        except (ValueError, TypeError) as error:
            logger.error(f"Invalid Kafka message: {error}")
            self._send_to_dlq(msg, event_data, error, retry_count=0)
            if isinstance(event_data, dict) and event_data.get("event_id"):
                self.processed_events.add(event_data["event_id"])
            self._commit_message(msg)
            return

        event_id = event.event_id
        if event_id in self.processed_events:
            self._commit_message(msg)
            return

        max_retries = 3
        for attempt in range(max_retries):
            try:
                handler_fn(event)
            except (KafkaDeliveryError, RetryableProcessingError):
                # Transient work must be retried, never acknowledged via DLQ.
                if attempt == max_retries - 1:
                    raise
            except Exception as error:
                if attempt == max_retries - 1:
                    logger.error(f"Event failed after {max_retries} attempts: {error}. Sending to DLQ.")
                    self._send_to_dlq(msg, event_data, error, retry_count=max_retries)
                    self.processed_events.add(event_id)
                    self._commit_message(msg)
                    return
            else:
                self.processed_events.add(event_id)
                self._commit_message(msg)
                logger.info("Event processed successfully", extra={
                    "event_id": event_id,
                    "event_type": event.event_type,
                    "correlation_id": event.correlation_id,
                })
                return
            logger.warning(f"Error processing event (attempt {attempt + 1}/{max_retries}); retrying")
            time.sleep((1, 2)[attempt])

    def close(self) -> None:
        """Close the consumer."""
        self.consumer.close()
