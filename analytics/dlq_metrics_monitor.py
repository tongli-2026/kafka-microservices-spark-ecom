#!/usr/bin/env python3
"""
DLQ Metrics Monitor - Exposes DLQ message count to Prometheus

PURPOSE:
    Continuously monitors the dlq.events Kafka topic and exposes metrics
    for dashboard visualization. This ensures DLQ dashboard panels always
    show current state of failed events.

METRICS EXPOSED:
    - dlq_message_count: Current number of messages in dlq.events topic
    - dlq_service_errors: Failed message count by service and error type

USAGE:
    python analytics/dlq_metrics_monitor.py

ENVIRONMENT VARIABLES:
    KAFKA_BOOTSTRAP_SERVERS: Kafka broker addresses (default: localhost:9094)
    METRICS_PORT: Prometheus metrics port (default: 9091)
    UPDATE_INTERVAL: Seconds between metric updates (default: 30)
"""

import os
import sys
import json
import logging
import time
from typing import Dict

# Prometheus metrics
from prometheus_client import Counter, Gauge, start_http_server

# Kafka
try:
    from confluent_kafka import Consumer, TopicPartition, KafkaError
except ImportError:
    print("ERROR: confluent-kafka not installed")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
METRICS_PORT = int(os.getenv("METRICS_PORT", "9091"))
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", "30"))

# ============ PROMETHEUS METRICS ============
dlq_message_count = Gauge(
    'dlq_message_count',
    'Current number of messages in Dead Letter Queue',
    ['service']
)

dlq_service_errors = Counter(
    'dlq_service_errors_total',
    'Total DLQ errors by service and type',
    ['service', 'error_type']
)

dlq_messages_by_service = Gauge(
    'dlq_messages_by_service',
    'Count of messages in DLQ by originating service',
    ['service']
)


class DLQMetricsMonitor:
    """Monitor DLQ metrics and expose to Prometheus"""

    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
        """Initialize DLQ metrics monitor"""
        self.bootstrap_servers = bootstrap_servers
        self.consumer = None
        self._init_consumer()

    def _init_consumer(self):
        """Initialize Kafka consumer for DLQ topic"""
        try:
            import uuid
            unique_group = f"dlq-metrics-{uuid.uuid4().hex[:8]}"

            self.consumer = Consumer({
                'bootstrap.servers': self.bootstrap_servers,
                'group.id': unique_group,
                'auto.offset.reset': 'earliest',
                'enable.auto.commit': False,
                'session.timeout.ms': 30000,
                'api.version.request.timeout.ms': 10000,
            })
            logger.info(f"✓ Kafka consumer initialized (group: {unique_group})")
        except Exception as e:
            logger.error(f"✗ Failed to initialize consumer: {e}")
            raise

    def get_dlq_messages(self) -> Dict[str, int]:
        """
        Read all messages from DLQ topic and count by service.
        
        Returns:
            Dict with service names as keys and message counts as values
        """
        service_counts = {}
        total_count = 0

        if not self.consumer:
            logger.warning("Consumer not initialized")
            return service_counts

        try:
            # Assign all partitions starting from beginning
            partitions = self.consumer.list_topics(topic='dlq.events', timeout=5).topics['dlq.events'].partitions
            partition_list = [TopicPartition('dlq.events', p, 0) for p in partitions.keys()]
            self.consumer.assign(partition_list)
            
            logger.debug(f"Reading from {len(partition_list)} partition(s)")

            # Poll messages with timeout
            poll_timeout = 0.5  # 500ms per poll
            empty_polls = 0
            max_empty_polls = 20  # Stop after 10 seconds of no messages

            while empty_polls < max_empty_polls:
                msg = self.consumer.poll(timeout=poll_timeout)

                if msg is None:
                    empty_polls += 1
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        pass  # Ignore EOF
                    continue

                # Reset counter when we get a message
                empty_polls = 0

                try:
                    dlq_event = json.loads(msg.value().decode('utf-8'))
                    
                    # Extract service name (can be from original_topic or error_details)
                    # Original topic format: "service.event_type"
                    original_topic = dlq_event.get('original_topic', 'unknown')
                    service = original_topic.split('.')[0] if '.' in original_topic else 'unknown'
                    
                    service_counts[service] = service_counts.get(service, 0) + 1
                    total_count += 1
                    
                except Exception as e:
                    logger.error(f"Error parsing DLQ message: {e}")
                    continue

            logger.info(f"Found {total_count} messages in DLQ")
            logger.debug(f"Messages by service: {service_counts}")
            return service_counts

        except Exception as e:
            logger.error(f"Error reading DLQ messages: {e}")
            return service_counts

    def update_metrics(self):
        """Query DLQ and update Prometheus metrics"""
        try:
            service_counts = self.get_dlq_messages()
            
            # Reset metrics for all services first
            for service in ['cart', 'order', 'payment', 'inventory', 'notification']:
                dlq_message_count.labels(service=service).set(0)
                dlq_messages_by_service.labels(service=service).set(0)
            
            # Update with actual counts
            for service, count in service_counts.items():
                dlq_message_count.labels(service=service).set(count)
                dlq_messages_by_service.labels(service=service).set(count)
                logger.info(f"Updated DLQ metric: {service}={count}")
            
            # Log total
            total = sum(service_counts.values())
            logger.info(f"DLQ Total: {total} messages")
            
        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def run(self):
        """Continuously update DLQ metrics"""
        logger.info(f"Starting DLQ Metrics Monitor (update interval: {UPDATE_INTERVAL}s)")
        
        while True:
            try:
                self.update_metrics()
                time.sleep(UPDATE_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in metrics loop: {e}")
                time.sleep(UPDATE_INTERVAL)
        
        if self.consumer:
            self.consumer.close()


def main():
    """Main entry point"""
    logger.info("=" * 80)
    logger.info("DLQ Metrics Monitor")
    logger.info("=" * 80)
    logger.info(f"Kafka Servers: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Metrics Port: {METRICS_PORT}")
    logger.info(f"Update Interval: {UPDATE_INTERVAL}s")
    logger.info("=" * 80)

    try:
        # Start Prometheus HTTP server
        logger.info(f"Starting Prometheus metrics server on port {METRICS_PORT}...")
        start_http_server(METRICS_PORT)
        logger.info(f"✓ Metrics available at http://localhost:{METRICS_PORT}/metrics")

        # Start DLQ metrics monitor
        monitor = DLQMetricsMonitor(KAFKA_BOOTSTRAP_SERVERS)
        monitor.run()

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
