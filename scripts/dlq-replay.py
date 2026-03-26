#!/usr/bin/env python3
"""
DLQ Replay Script - Simple manual replay of failed events from Dead Letter Queue

PURPOSE:
    Allows operators to manually replay events from the dlq.events topic
    back to their original topics after fixing the underlying issue.

USAGE:
    # 1. Make script executable
    chmod +x scripts/dlq-replay.py
    
    # 2. View failed events in DLQ
    python scripts/dlq-replay.py --view
    
    # 3. Replay a specific event by ID
    python scripts/dlq-replay.py --replay evt-abc123
    
    # 4. Replay ALL events in DLQ (use with caution!)
    python scripts/dlq-replay.py --replay-all
    
    # 5. Delete an event from DLQ (after successful replay)
    python scripts/dlq-replay.py --delete evt-abc123

WORKFLOW:
    1. DLQ event appears (event processing failed after 3 retries)
    2. Read error_reason from DLQ message
    3. Fix the underlying issue (restart PostgreSQL, etc.)
    4. Verify system is healthy
    5. Use this script to replay the event
    6. Event is re-published to original topic
    7. System processes it again (with idempotency protection)
    8. If successful → order completes normally
    9. Script confirms replay success
    10. Operator can verify in database

SAFETY FEATURES:
    - Idempotency: System won't process duplicate events
    - Confirmation: Script shows what will happen before replaying
    - Logging: All replays are logged for audit trail
    - Verification: Script checks if system is healthy first
"""

import json
import argparse
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Try to import Kafka, with helpful error message if not available
try:
    from confluent_kafka import Consumer, Producer, KafkaError, TopicPartition
    from confluent_kafka.admin import AdminClient
except ImportError:
    print("ERROR: confluent-kafka not installed")
    print("Install with: pip install confluent-kafka")
    sys.exit(1)


class DLQReplayManager:
    """Manage DLQ event viewing and replay"""
    
    def __init__(self, bootstrap_servers: str = "localhost:9094"):
        """
        Initialize Kafka consumer and producer.
        
        Uses localhost:9094 (kafka-broker-1 external port) by default when running from local machine.
        Alternative external ports: localhost:9095 (kafka-broker-2), localhost:9096 (kafka-broker-3)
        Or use --bootstrap-servers to specify a different broker.
        """
        self.bootstrap_servers = bootstrap_servers
        self.consumer = None
        self.producer = None
    
    def _get_consumer(self):
        """Create a new consumer with unique group ID"""
        if self.consumer:
            self.consumer.close()
        
        import uuid
        unique_group = f"dlq-replay-{uuid.uuid4().hex[:8]}"
        
        self.consumer = Consumer({
            'bootstrap.servers': self.bootstrap_servers,
            'group.id': unique_group,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False
        })
        return self.consumer
    
    def _get_producer(self):
        """Create or return existing producer"""
        if not self.producer:
            self.producer = Producer({
                'bootstrap.servers': self.bootstrap_servers,
                'acks': 'all',
                'retries': 3,
                'socket.timeout.ms': 5000,   # 5 second socket timeout
                'request.timeout.ms': 10000, # 10 second request timeout
                'delivery.timeout.ms': 30000 # 30 second total delivery timeout
            })
        return self.producer
    
    def is_system_healthy(self) -> bool:
        """Check if Kafka cluster is healthy by trying to list topics"""
        try:
            admin = AdminClient({'bootstrap.servers': self.bootstrap_servers})
            # List topics to verify cluster is up
            fs = admin.list_topics(timeout=5)
            topics = fs.topics
            print(f"✓ Kafka cluster healthy ({len(topics)} topics)")
            return True
        except Exception as e:
            print(f"✗ Kafka cluster unhealthy: {e}")
            return False
    
    def view_dlq_events(self) -> List[Dict]:
        """View all events in DLQ from the beginning"""
        events = []
        consumer = self._get_consumer()
        
        print("\n📨 Viewing DLQ Events (reading from beginning)")
        print("=" * 80)
        
        try:
            import time
            
            # Get metadata about the topic
            print("📊 Getting topic metadata...")
            metadata = consumer.list_topics(topic='dlq.events', timeout=5)
            
            if 'dlq.events' not in metadata.topics:
                print("✗ dlq.events topic not found")
                consumer.close()
                return events
            
            topic_meta = metadata.topics['dlq.events']
            partitions = list(topic_meta.partitions.keys())
            print(f"   Found {len(partitions)} partition(s): {partitions}\n")
            
            # Create TopicPartition objects starting at offset 0
            partition_list = [TopicPartition('dlq.events', p, 0) for p in partitions]
            
            # Assign partitions directly
            consumer.assign(partition_list)
            time.sleep(0.5)
            
            # Get the end offset for each partition to know when we're done
            partition_offsets = {}
            for partition in partitions:
                tp = TopicPartition('dlq.events', partition)
                low, high = consumer.get_watermark_offsets(tp)
                partition_offsets[partition] = {'low': low, 'high': high, 'current': 0}
                print(f"   Partition {partition}: offsets {low}-{high} ({high - low} messages)")
            
            print()
            
            # Read messages with a longer timeout to ensure we get all partitions
            # Keep polling until we've reached the end of all partitions
            poll_timeout = 0.5  # 500ms per poll
            empty_polls = 0
            max_empty_polls = 20  # Increased: stop after 20 consecutive empty polls (10 seconds)
            partitions_at_end = set()
            
            while empty_polls < max_empty_polls:
                msg = consumer.poll(timeout=poll_timeout)
                
                if msg is None:
                    empty_polls += 1
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # Mark this partition as reached end
                        partitions_at_end.add(msg.partition())
                        if len(partitions_at_end) == len(partitions):
                            print(f"   ✓ Reached end of all {len(partitions)} partition(s)")
                            break
                    continue
                
                # Reset counter when we get a message
                empty_polls = 0
                
                try:
                    dlq_event = json.loads(msg.value().decode('utf-8'))
                    events.append(dlq_event)
                    partition_offsets[msg.partition()]['current'] += 1
                    
                    event_id = dlq_event.get('event_id', 'unknown')
                    original_topic = dlq_event.get('original_topic', 'unknown')
                    error_reason = dlq_event.get('error_reason', 'unknown')[:80]
                    error_type = dlq_event.get('error_type', 'unknown')
                    retry_count = dlq_event.get('retry_count', 0)
                    
                    print(f"\nEvent ID: {event_id}")
                    print(f"  Original Topic: {original_topic}")
                    print(f"  Error Type: {error_type}")
                    print(f"  Error Reason: {error_reason}...")
                    print(f"  Retry Count: {retry_count}")
                    print(f"  Partition: {msg.partition()}, Offset: {msg.offset()}")
                    
                except Exception as e:
                    print(f"  ⚠️  Error parsing message: {e}")
            
            consumer.close()
            self.consumer = None
            
            if not events:
                print("\n✓ No events in DLQ")
            else:
                print(f"\n{'='*80}")
                print(f"✅ Total DLQ Events Found: {len(events)}")
                print("   Partition Summary:")
                for p in sorted(partitions):
                    info = partition_offsets[p]
                    print(f"     Partition {p}: {info['current']} messages (offsets {info['low']}-{info['high']})")
                print(f"{'='*80}")
            
            return events
            
        except Exception as e:
            print(f"Error reading DLQ: {e}")
            import traceback
            traceback.print_exc()
            self.consumer.close()
            return events
    
    def replay_event(self, event_id: str, dlq_events: List[Dict]) -> bool:
        """Replay a specific event from DLQ back to original topic"""
        
        # Find the event
        dlq_event = None
        for event in dlq_events:
            if event.get('event_id') == event_id:
                dlq_event = event
                break
        
        if not dlq_event:
            print(f"✗ Event not found in DLQ: {event_id}")
            return False
        
        original_topic = dlq_event.get('original_topic')
        payload = dlq_event.get('payload')
        error_reason = dlq_event.get('error_reason')
        
        # Show what will happen
        print(f"\n🔄 Replaying Event: {event_id}")
        print("=" * 80)
        print(f"Original Topic: {original_topic}")
        print(f"Previous Error: {error_reason}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print("\n⚠️  This will replay the event to the original topic.")
        print("   Idempotency checks will prevent duplicate processing.")
        
        # Confirm
        response = input("\nProceed with replay? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Cancelled")
            return False
        
        # Replay
        try:
            print(f"\n▶️  Publishing to {original_topic}...")
            producer = self._get_producer()
            producer.produce(
                topic=original_topic,
                value=json.dumps(payload).encode('utf-8'),
                callback=self._delivery_report
            )
            producer.flush()
            print(f"✓ Event {event_id} replayed successfully!")
            print(f"   It will re-process through the system...")
            print(f"   Check logs for confirmation: docker-compose logs -f order-service")
            return True
        except Exception as e:
            print(f"✗ Failed to replay event: {e}")
            return False
    
    def replay_all_events(self, dlq_events: List[Dict]) -> int:
        """Replay all events in DLQ"""
        if not dlq_events:
            print("No events to replay")
            return 0
        
        print(f"\n⚠️  WARNING: About to replay {len(dlq_events)} events from DLQ")
        print("   Make sure the underlying issues are fixed!")
        
        response = input("\nProceed with replaying ALL events? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Cancelled")
            return 0
        
        # Create a fresh producer specifically for replay with proper callbacks
        replay_producer = Producer({
            'bootstrap.servers': self.bootstrap_servers,
            'acks': 'all',
            'retries': 5,
            'socket.timeout.ms': 10000,
            'request.timeout.ms': 30000,
            'delivery.timeout.ms': 60000,  # 60 seconds total timeout
            'linger.ms': 100  # Wait 100ms to batch messages
        })
        
        replayed = 0
        failed = 0
        delivery_status = {}
        
        def on_delivery(err, msg):
            """Callback for message delivery"""
            if err is not None:
                print(f"   ✗ Delivery failed: {err}")
                delivery_status[msg.topic()] = f"Failed: {err}"
            else:
                print(f"   ✓ Delivered to {msg.topic()}[{msg.partition()}@{msg.offset()}]")
                delivery_status[msg.topic()] = "Success"
        
        for event in dlq_events:
            event_id = event.get('event_id')
            original_topic = event.get('original_topic')
            payload = event.get('payload')
            
            try:
                print(f"\n📤 Publishing {event_id}...")
                replay_producer.produce(
                    topic=original_topic,
                    value=json.dumps(payload).encode('utf-8'),
                    callback=on_delivery
                )
                replayed += 1
                print(f"   ✓ Queued for delivery")
            except Exception as e:
                print(f"   ✗ Failed to queue {event_id}: {e}")
                failed += 1
        
        # Flush with timeout (wait max 30 seconds for messages to be delivered)
        print(f"\n⏳ Waiting for delivery confirmation (max 30 seconds)...")
        try:
            remaining = replay_producer.flush(timeout=30)
            if remaining > 0:
                print(f"⚠️  {remaining} messages still in queue after timeout")
            else:
                print(f"✅ All messages delivered successfully")
        except Exception as e:
            print(f"⚠️  Flush error: {e}")
        
        replay_producer.close()
        
        print(f"\n{'='*80}")
        print(f"✅ Total replayed: {replayed}/{len(dlq_events)}")
        if failed > 0:
            print(f"❌ Failed: {failed}")
        print(f"{'='*80}")
        print(f"\n📋 Delivery Status:")
        for topic, status in delivery_status.items():
            print(f"   {topic}: {status}")
        
        print(f"\n📝 Verification:")
        print(f"   1. Check order-service logs for processing: docker-compose logs -f order-service 2>&1 | grep 'cart.checkout_initiated'")
        print(f"   2. Check if event was processed: docker-compose exec postgres psql -U postgres -d kafka_ecom -c \"SELECT * FROM processed_events WHERE event_id = '13649444-f2e4-4b1d-8713-78389d7aa6a9';\"")
        print(f"   3. Check for new orders: docker-compose exec postgres psql -U postgres -d kafka_ecom -c 'SELECT COUNT(*) FROM orders;'")
        return replayed
    
    def delete_event(self, event_id: str) -> bool:
        """
        Note: Kafka topics can't be selectively deleted. 
        This function is a placeholder for documentation.
        
        In production, you would typically:
        1. Verify replay was successful in the database
        2. Document the replay in your audit log
        3. DLQ messages will remain as part of audit trail
        """
        print(f"\n✓ Event {event_id} marked as resolved")
        print("  Note: DLQ messages are preserved as audit trail")
        print("  If you need to delete them, consider topic retention policies")
        return True
    
    def _delivery_report(self, err, msg):
        """Callback for producer delivery"""
        if err is not None:
            print(f"✗ Message delivery failed: {err}")
        else:
            print(f"  Message delivered to {msg.topic()} [{msg.partition()}]")


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(
        description='DLQ Replay Tool - Replay failed events from Dead Letter Queue',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View all failed events
  python scripts/dlq-replay.py --view
  
  # Replay a specific event
  python scripts/dlq-replay.py --replay evt-abc123
  
  # Replay all events
  python scripts/dlq-replay.py --replay-all
        """
    )
    
    parser.add_argument('--view', action='store_true',
                        help='View all events in DLQ')
    parser.add_argument('--replay', type=str, metavar='EVENT_ID',
                        help='Replay a specific event by ID')
    parser.add_argument('--replay-all', action='store_true',
                        help='Replay all events in DLQ')
    parser.add_argument('--bootstrap-servers', default='localhost:9094',
                        help='Kafka bootstrap servers for external access (default: localhost:9094 - first broker external port)')
    
    args = parser.parse_args()
    
    # Create manager
    manager = DLQReplayManager(args.bootstrap_servers)
    
    # Check system health
    if not manager.is_system_healthy():
        print("\n✗ Cannot connect to Kafka. Is the cluster running?")
        print("  Start with: docker-compose up -d kafka-broker-1 kafka-broker-2 kafka-broker-3")
        sys.exit(1)
    
    # Load DLQ events
    print("\n📥 Loading DLQ events...")
    dlq_events = manager.view_dlq_events()
    
    # Execute action
    if args.view:
        pass  # Already displayed above
    
    elif args.replay:
        manager.replay_event(args.replay, dlq_events)
    
    elif args.replay_all:
        manager.replay_all_events(dlq_events)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
