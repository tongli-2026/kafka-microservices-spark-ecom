"""
topic_initializer.py - Kafka Topic Auto-Creation Utility

PURPOSE:
    Automatically creates all required Kafka topics on application startup
    with proper partitioning and replication configuration.

TOPICS CREATED:
    - cart.item_added
    - cart.item_removed
    - cart.checkout_initiated
    - order.created
    - order.reservation_confirmed
    - order.confirmed
    - order.cancelled
    - inventory.reserved
    - inventory.low
    - inventory.depleted
    - payment.processed
    - payment.failed
    - notification.send
    - fraud.detected
    - dlq.events

CONFIGURATION:
    - Default partitions: 3 (enables parallel processing)
    - Default replication factor: 3 (ensures high availability)
    - Idempotent: Safe to call multiple times

RETRY LOGIC:
    - Retries topic creation if Kafka brokers not ready
    - 3 retry attempts with 5-second delays
    - Logs all creation attempts and failures

USAGE:
    Called by each microservice on startup:
        create_topics("kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092")

WHY AUTO-CREATE:
    - Ensures consistent topic configuration across environments
    - Prevents "topic not found" errors
    - Simplifies deployment (no manual topic creation needed)
    - Guarantees proper partitioning and replication
"""

import logging  # For status and error logging
import time  # For retry delays
from typing import List  # Type hints

from confluent_kafka.admin import AdminClient, NewTopic  # Kafka admin operations

# Import list of all topics to create
try:
    from shared.events import ALL_TOPICS
except ImportError:
    from events import ALL_TOPICS

logger = logging.getLogger(__name__)


def create_topics(bootstrap_servers: str, num_partitions: int = 3, replication_factor: int = 3) -> None:
    """
    Create all Kafka topics with specified partitions and replication factor.
    
    Args:
        bootstrap_servers: Comma-separated Kafka broker addresses
        num_partitions: Number of partitions per topic (default: 3)
        replication_factor: Number of replicas per partition (default: 3)
    
    Note:
        - Idempotent: Safe to call multiple times
        - Existing topics are ignored
        - Retries up to 3 times if brokers not ready
    """
    admin_config = {"bootstrap.servers": bootstrap_servers}
    admin_client = AdminClient(admin_config)

    # Create NewTopic objects for all topics
    topics_to_create: List[NewTopic] = [
        NewTopic(topic, num_partitions=num_partitions, replication_factor=replication_factor)
        for topic in ALL_TOPICS
    ]

    # Retry logic: brokers may not be ready immediately on startup
    max_retries = 10
    retry_delay = 3
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Creating topics (attempt {attempt + 1}/{max_retries})...")
            
            # Create topics
            fs = admin_client.create_topics(topics_to_create, validate_only=False)
            
            # Wait for operation to complete
            for topic, future in fs.items():
                try:
                    future.result(timeout=10)
                    logger.info(f"Topic '{topic}' created successfully")
                except Exception as e:
                    # Topic may already exist
                    if "already exists" in str(e) or "TOPIC_ALREADY_EXISTS" in str(e):
                        logger.info(f"Topic '{topic}' already exists")
                    else:
                        logger.warning(f"Error creating topic '{topic}': {e}")
            
            logger.info("All topics processed successfully")
            break
            
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Failed to create topics (attempt {attempt + 1}): {e}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to create topics after {max_retries} attempts: {e}")
                raise
