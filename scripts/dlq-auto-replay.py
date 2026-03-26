#!/usr/bin/env python3
"""
DLQ Auto-Replay Script with Threshold-based Triggering

Purpose:
- Monitors DLQ message count continuously
- Automatically triggers replay when threshold is exceeded
- Performs system health checks before replay
- Publishes metrics to Prometheus for monitoring
- Can run as daemon or one-time check

Usage:
    # One-time check (replay if > 50 messages)
    python scripts/dlq-auto-replay.py --threshold 50

    # Run as background daemon (check every 5 minutes)
    python scripts/dlq-auto-replay.py --daemon --interval 300 --threshold 50

    # Verbose logging
    python scripts/dlq-auto-replay.py --threshold 50 --verbose

Environment Variables:
    KAFKA_BOOTSTRAP_SERVERS: Kafka broker addresses
    POSTGRES_HOST, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB: DB connection

Metrics Published to Prometheus:
    dlq_message_count: Current number of messages in DLQ
    dlq_auto_replay_triggered: Counter of auto-replay attempts
    dlq_auto_replay_success: Counter of successful replays
    dlq_auto_replay_failed: Counter of failed replays
    dlq_system_health_check_passed: System health status (0/1)
"""

import os
import sys
import json
import time
import subprocess
import logging
from datetime import datetime
from typing import Dict, List, Tuple
from argparse import ArgumentParser

# Prometheus metrics
from prometheus_client import Counter, Gauge, CollectorRegistry, push_to_gateway

# Kafka and DB imports
try:
    from kafka import KafkaConsumer, KafkaAdminClient
    from kafka.admin import ConfigResource, ConfigResourceType
except ImportError:
    print("ERROR: kafka-python not installed. Run: pip install kafka-python")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
registry = CollectorRegistry()
dlq_message_count = Gauge('dlq_message_count', 'Current DLQ message count', registry=registry)
dlq_auto_replay_triggered = Counter(
    'dlq_auto_replay_triggered_total',
    'Number of auto-replay attempts triggered',
    registry=registry
)
dlq_auto_replay_success = Counter(
    'dlq_auto_replay_success_total',
    'Number of successful auto-replays',
    registry=registry
)
dlq_auto_replay_failed = Counter(
    'dlq_auto_replay_failed_total',
    'Number of failed auto-replays',
    registry=registry
)
dlq_system_health = Gauge(
    'dlq_system_health_check_passed',
    'System health check status (1=healthy, 0=unhealthy)',
    registry=registry
)


class DLQAutoReplay:
    """Auto-replay manager for DLQ messages"""

    def __init__(self, threshold: int = 50, kafka_servers: str = None, verbose: bool = False):
        """
        Initialize DLQ auto-replay manager

        Args:
            threshold: Trigger replay when DLQ message count exceeds this
            kafka_servers: Comma-separated Kafka broker addresses
            verbose: Enable verbose logging
        """
        self.threshold = threshold
        self.kafka_servers = kafka_servers or os.getenv(
            'KAFKA_BOOTSTRAP_SERVERS',
            'kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092'
        )
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.debug(f"Verbose logging enabled")
        
        logger.info(f"🔧 DLQ Auto-Replay initialized")
        logger.info(f"   Threshold: {self.threshold} messages")
        logger.info(f"   Kafka Brokers: {self.kafka_servers}")

    def get_dlq_message_count(self) -> int:
        """
        Get current message count in DLQ topic

        Returns:
            Number of messages in dlq.events topic
        """
        try:
            consumer = KafkaConsumer(
                'dlq.events',
                bootstrap_servers=self.kafka_servers.split(','),
                auto_offset_reset='earliest',
                consumer_timeout_ms=5000,
                group_id='dlq-auto-replay-counter'
            )
            
            partitions = consumer.partitions_for_topic('dlq.events')
            if not partitions:
                logger.warning("⚠️  DLQ topic 'dlq.events' not found")
                return 0
            
            message_count = 0
            for partition in partitions:
                tp = consumer.partitions_for_topic('dlq.events')
                consumer.assign([consumer.TopicPartition('dlq.events', partition)])
                consumer.seek_to_end(consumer.TopicPartition('dlq.events', partition))
                message_count += consumer.position(consumer.TopicPartition('dlq.events', partition))
            
            consumer.close()
            return message_count
            
        except Exception as e:
            logger.error(f"❌ Failed to get DLQ message count: {e}")
            return -1

    def check_postgres_health(self) -> bool:
        """Check if PostgreSQL is accessible"""
        try:
            import psycopg2
            conn_params = {
                'host': os.getenv('POSTGRES_HOST', 'postgres'),
                'port': os.getenv('POSTGRES_PORT', '5432'),
                'database': os.getenv('POSTGRES_DB', 'kafka_ecom'),
                'user': os.getenv('POSTGRES_USER', 'postgres'),
                'password': os.getenv('POSTGRES_PASSWORD', 'postgres'),
            }
            conn = psycopg2.connect(**conn_params)
            conn.close()
            logger.debug("✅ PostgreSQL: Healthy")
            return True
        except Exception as e:
            logger.warning(f"❌ PostgreSQL: Unhealthy - {e}")
            return False

    def check_kafka_health(self) -> bool:
        """Check if Kafka cluster is accessible"""
        try:
            admin = KafkaAdminClient(
                bootstrap_servers=self.kafka_servers.split(','),
                client_id='dlq-health-check',
                request_timeout_ms=5000
            )
            admin.list_topics()
            admin.close()
            logger.debug("✅ Kafka: Healthy")
            return True
        except Exception as e:
            logger.warning(f"❌ Kafka: Unhealthy - {e}")
            return False

    def check_services_health(self) -> Dict[str, bool]:
        """Check if microservices are responding"""
        services = {
            'cart': 'http://localhost:8001/health',
            'order': 'http://localhost:8002/health',
            'payment': 'http://localhost:8003/health',
            'inventory': 'http://localhost:8004/health',
            'notification': 'http://localhost:8005/health',
        }
        
        health_status = {}
        for service_name, url in services.items():
            try:
                import requests
                response = requests.get(url, timeout=2)
                is_healthy = response.status_code == 200
                health_status[service_name] = is_healthy
                status_icon = "✅" if is_healthy else "❌"
                logger.debug(f"{status_icon} {service_name.capitalize()} Service: {response.status_code}")
            except Exception as e:
                health_status[service_name] = False
                logger.debug(f"❌ {service_name.capitalize()} Service: Unreachable - {str(e)[:50]}")
        
        return health_status

    def check_system_health(self) -> Tuple[bool, Dict]:
        """
        Comprehensive system health check

        Returns:
            Tuple of (is_healthy: bool, health_details: dict)
        """
        logger.info("🔍 Performing system health check...")
        
        postgres_ok = self.check_postgres_health()
        kafka_ok = self.check_kafka_health()
        services_ok = self.check_services_health()
        
        # System is healthy if critical components (Postgres, Kafka) are OK
        # At least 3 out of 5 microservices should be healthy
        critical_ok = postgres_ok and kafka_ok
        services_healthy_count = sum(1 for v in services_ok.values() if v)
        services_ok_overall = services_healthy_count >= 3
        
        system_healthy = critical_ok and services_ok_overall
        
        health_details = {
            'postgres': postgres_ok,
            'kafka': kafka_ok,
            'services': services_ok,
            'services_healthy_count': services_healthy_count,
            'overall': system_healthy,
        }
        
        status_icon = "✅" if system_healthy else "❌"
        logger.info(f"{status_icon} System Health: {'HEALTHY' if system_healthy else 'UNHEALTHY'}")
        logger.info(f"   PostgreSQL: {'✅' if postgres_ok else '❌'}")
        logger.info(f"   Kafka: {'✅' if kafka_ok else '❌'}")
        logger.info(f"   Microservices: {services_healthy_count}/5 healthy")
        
        dlq_system_health.set(1 if system_healthy else 0)
        return system_healthy, health_details

    def trigger_replay(self) -> bool:
        """
        Trigger DLQ replay using dlq-replay.py script

        Returns:
            True if replay succeeded, False otherwise
        """
        logger.info("🔄 Triggering DLQ replay...")
        
        try:
            result = subprocess.run(
                ['python', 'scripts/dlq-replay.py', '--replay-all', '--verbose'],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                capture_output=True,
                timeout=300,  # 5-minute timeout
                text=True
            )
            
            if result.returncode == 0:
                logger.info("✅ DLQ replay completed successfully")
                dlq_auto_replay_success.inc()
                return True
            else:
                logger.error(f"❌ DLQ replay failed with exit code {result.returncode}")
                logger.error(f"   STDERR: {result.stderr[:200]}")
                dlq_auto_replay_failed.inc()
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ DLQ replay timed out (5 minutes)")
            dlq_auto_replay_failed.inc()
            return False
        except Exception as e:
            logger.error(f"❌ Failed to trigger replay: {e}")
            dlq_auto_replay_failed.inc()
            return False

    def check_and_replay(self) -> Dict:
        """
        Check DLQ message count and replay if threshold exceeded

        Returns:
            Status dictionary with results
        """
        logger.info("=" * 70)
        logger.info(f"DLQ Auto-Replay Check - {datetime.now().isoformat()}")
        logger.info("=" * 70)
        
        # Step 1: Get DLQ message count
        dlq_count = self.get_dlq_message_count()
        dlq_message_count.set(dlq_count)
        
        if dlq_count < 0:
            return {
                'success': False,
                'reason': 'Failed to get DLQ message count',
                'dlq_count': dlq_count,
                'threshold': self.threshold,
                'action_taken': 'NONE'
            }
        
        logger.info(f"📊 DLQ Status: {dlq_count} messages (threshold: {self.threshold})")
        
        # Step 2: Check if threshold exceeded
        if dlq_count <= self.threshold:
            logger.info(f"✅ DLQ healthy (under threshold)")
            return {
                'success': True,
                'reason': 'DLQ count under threshold',
                'dlq_count': dlq_count,
                'threshold': self.threshold,
                'action_taken': 'NONE'
            }
        
        logger.warning(f"⚠️  DLQ threshold exceeded! ({dlq_count} > {self.threshold})")
        dlq_auto_replay_triggered.inc()
        
        # Step 3: Check system health
        system_healthy, health_details = self.check_system_health()
        
        if not system_healthy:
            logger.error("❌ System unhealthy. Aborting replay.")
            logger.error("   Fix these issues before replaying:")
            if not health_details['postgres']:
                logger.error("   - PostgreSQL is down or unreachable")
            if not health_details['kafka']:
                logger.error("   - Kafka cluster is down or unreachable")
            
            unhealthy_services = [
                name for name, status in health_details['services'].items() if not status
            ]
            if unhealthy_services:
                logger.error(f"   - Unhealthy services: {', '.join(unhealthy_services)}")
            
            return {
                'success': False,
                'reason': 'System health check failed',
                'dlq_count': dlq_count,
                'threshold': self.threshold,
                'health_details': health_details,
                'action_taken': 'NONE'
            }
        
        # Step 4: Trigger replay
        logger.info(f"✅ System health check passed. Proceeding with replay...")
        replay_success = self.trigger_replay()
        
        return {
            'success': replay_success,
            'reason': 'Replay completed' if replay_success else 'Replay failed',
            'dlq_count': dlq_count,
            'threshold': self.threshold,
            'action_taken': 'REPLAY_EXECUTED',
            'replay_success': replay_success
        }

    def run_daemon(self, interval: int):
        """
        Run as background daemon, checking periodically

        Args:
            interval: Check interval in seconds
        """
        logger.info(f"🚀 Starting DLQ Auto-Replay daemon (check every {interval}s)")
        
        try:
            iteration = 0
            while True:
                iteration += 1
                logger.info(f"\n[Iteration {iteration}] Running health check...")
                
                result = self.check_and_replay()
                
                if result['action_taken'] == 'REPLAY_EXECUTED':
                    if result['replay_success']:
                        logger.info(f"✅ Auto-replay completed. Next check in {interval}s")
                    else:
                        logger.warning(f"⚠️  Auto-replay failed. Next check in {interval}s")
                
                logger.info(f"⏱️  Sleeping for {interval} seconds...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("\n⏹️  Daemon stopped by user")
            sys.exit(0)


def main():
    parser = ArgumentParser(description='DLQ Auto-Replay with threshold-based triggering')
    parser.add_argument(
        '--threshold',
        type=int,
        default=50,
        help='Trigger replay when DLQ message count exceeds this (default: 50)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Check interval in seconds for daemon mode (default: 300)'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as background daemon'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--kafka-servers',
        type=str,
        help='Comma-separated Kafka broker addresses'
    )
    
    args = parser.parse_args()
    
    replay_manager = DLQAutoReplay(
        threshold=args.threshold,
        kafka_servers=args.kafka_servers,
        verbose=args.verbose
    )
    
    if args.daemon:
        replay_manager.run_daemon(interval=args.interval)
    else:
        result = replay_manager.check_and_replay()
        logger.info("\n" + "=" * 70)
        logger.info("FINAL RESULT:")
        logger.info(f"  Success: {result['success']}")
        logger.info(f"  Reason: {result['reason']}")
        logger.info(f"  DLQ Messages: {result['dlq_count']}")
        logger.info(f"  Threshold: {result['threshold']}")
        logger.info(f"  Action Taken: {result['action_taken']}")
        logger.info("=" * 70)
        
        # Exit with appropriate code
        sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
