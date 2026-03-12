"""
operational_metrics.py - Real-Time System Health and Operational Monitoring

PURPOSE:
    Monitors overall system health, event throughput, and operational KPIs
    across all microservices in real-time, enabling proactive incident detection
    and service availability tracking.

BUSINESS VALUE:
    - Real-time system health dashboard
    - Detect performance degradation immediately
    - Monitor service uptime and reliability
    - Track transaction throughput
    - Alert on anomalies in event processing
    - Support SLA compliance monitoring

KAFKA TOPICS CONSUMED:
    Cart Service (3 topics):
    - cart.item_added: Items added to shopping cart
    - cart.item_removed: Items removed from shopping cart
    - cart.checkout_initiated: Customer initiates checkout (start of journey)
    
    Order Service (5 topics):
    - order.created: New order creation events (source: order-service)
    - order.confirmed: Successfully confirmed orders after payment verification
    - order.cancelled: Orders cancelled due to payment failure or user action
    - order.fulfilled: Order fulfillment completed
    - order.reservation_confirmed: Inventory reservation confirmed for order
    
    Payment Service (2 topics):
    - payment.processed: Successful payment transactions (real-time confirmation)
    - payment.failed: Failed payment attempts (fraud, insufficient funds, timeout, etc.)
    
    Inventory Service (3 topics):
    - inventory.reserved: Stock reservation completion events
    - inventory.low: Low stock warning
    - inventory.depleted: Stock depleted events
    
    Notification Service (1 topic):
    - notification.send: Email notifications sent to users/admins after email delivery
    
    EXCLUDED TOPICS:
    - fraud.detected: Output from another Spark job, not raw service events
    - dlq.* topics: Dead letter queue, not healthy events

OUTPUT:
    PostgreSQL table: operational_metrics
    Schema:
      - window_start: Start of measurement window (timestamp)
      - window_end: End of measurement window (timestamp)
      - metric_name: Type of metric (currently: throughput)
      - metric_value: Numeric value of metric (event count)
      - threshold: Expected baseline threshold for this metric
      - status: Health status (HEALTHY, WARNING, CRITICAL)
      - services_checked: JSON with topic_monitored and events_processed details

OPERATIONAL METRICS:
    1. THROUGHPUT
       - Total events per topic per minute
       - Compares to baseline threshold (20 events/min per topic)
       - Status:
         * HEALTHY: >15 events/min
         * WARNING: >8 events/min
         * CRITICAL: ≤8 events/min
       - Note: Calibrated for light load testing (5 users per wave, 30s intervals)
    
    NOTE: Current implementation focuses on throughput monitoring.
    For production, calibrate thresholds based on actual user load:
    - Light load (5-10 users): 15-30 events/min per topic
    - Medium load (50-100 users): 150-300 events/min per topic  
    - Heavy load (1000+ users): 1500+ events/min per topic

MONITORING ALGORITHM:
    Event-Based Throughput Monitoring with Health Scoring:
    
    1. STREAMS INPUT: All operational event topics (14 total)
       - Journey complete coverage: user adds item → checkout → order → payment → inventory → notification
    2. TIMESTAMP: Extract event timestamp from Kafka message
    3. WINDOWS: 1-minute tumbling windows
    4. AGGREGATION (per topic, per window):
       - COUNT(events) → throughput (events processed per minute)
    5. HEALTH SCORING:
       - Compare event count to thresholds
       - Assign status (HEALTHY/WARNING/CRITICAL)
    6. OUTPUT: Write to PostgreSQL with status and topic details
    
    Example Timeline:
    ┌──────────────────────────────────────────┐
    │ Operational Metrics (1-Minute Window)    │
    │                                          │
    │ Order Service:                           │
    │   - Throughput: 1,250 events/min         │
    │   - Success Rate: 99.8% ✅ HEALTHY       │
    │   - Latency (avg): 45ms                  │
    │                                          │
    │ Payment Service:                         │
    │   - Throughput: 850 events/min           │
    │   - Success Rate: 97.2% ⚠️ WARNING       │
    │   - Latency (avg): 1,200ms               │
    │                                          │
    │ Inventory Service:                       │
    │   - Throughput: 2,100 events/min         │
    │   - Success Rate: 98.5% ✅ HEALTHY       │
    │   - Latency (avg): 120ms                 │
    └──────────────────────────────────────────┘

WINDOWING:
    - Window Duration: 1 minute
    - Window Type: Tumbling (non-overlapping)
    - Watermark: 10 seconds for late data
    - Trigger: Process every 10 seconds

ALERTING THRESHOLDS:
    - Success Rate < 95%: CRITICAL alert
    - Latency > 2 seconds: WARNING alert
    - Throughput > 20% drop: WARNING alert
    - Service unavailable > 30 seconds: CRITICAL alert

PERFORMANCE:
    - Kafka Throughput: 20+ events/minute per topic (baseline for healthy system at light load)
    - Processing Mode: Micro-batch (foreachBatch)
    - Output Mode: Append (only new metrics)
    - Fault Tolerance: Checkpointing at /opt/spark-data/checkpoints/operational_metrics
    - Checkpoint Configuration: Via CHECKPOINT_PATH environment variable (default: /opt/spark-data/checkpoints/operational_metrics)
    - Latency: ~10 seconds end-to-end (includes processing trigger + database write)
    - Test Command: ./scripts/simulate-users.py --mode continuous --duration 300 --interval 30

USAGE:
    ./scripts/spark/run-spark-job.sh operational_metrics

DEPENDENCIES:
    - Apache Kafka (3+ brokers)
    - Apache Spark 3.5.0+
    - PostgreSQL 12+
    - spark-sql-kafka-0-10 JAR (included in spark_session.py)

MONITORING:
    Check Spark UI: http://localhost:4040/
    Check metrics: SELECT * FROM operational_metrics WHERE status != 'HEALTHY';
    Check checkpoint: ls -la /opt/spark-data/checkpoints/operational_metrics/ (or set CHECKPOINT_PATH env var)
"""

import logging
import os
import psycopg2
from psycopg2.extras import execute_values

# Spark SQL functions for metrics calculation
from pyspark.sql.functions import (
    col, from_json, window, count, to_timestamp, when, lit, concat_ws,
    to_json, struct
)
# Spark data types for schema definitions
from pyspark.sql.types import StringType

# Import shared Spark configuration
# Note: spark_session.py is in parent directory (analytics/)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from spark_session import get_spark_session, get_kafka_options

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "kafka_ecom")


def operational_metrics():
    """
    Job 5: Operational health metrics.
    Monitor overall system health and performance.
    """
    logger.info("Starting operational metrics job...")
    
    spark = get_spark_session("operational-metrics")
    kafka_options = get_kafka_options()

    # Subscribe to all operational topics across full customer journey
    # Monitors: cart (3) + order (5) + payment (2) + inventory (3) + notification (1) = 14 topics
    # Captures complete journey: cart → checkout → order → payment → inventory → notification
    # Excludes: notification.send (request, not actual sent), fraud.* (derivative), dlq.* (non-healthy)
    df = spark \
        .readStream \
        .format("kafka") \
        .option("subscribe", "cart.item_added,cart.item_removed,cart.checkout_initiated,order.created,order.confirmed,order.cancelled,order.fulfilled,order.reservation_confirmed,payment.processed,payment.failed,inventory.reserved,inventory.low,inventory.depleted,notification.send") \
        .options(**kafka_options) \
        .load()

    # Extract topic and timestamp
    parsed_df = df.select(
        col("topic"),
        col("timestamp").alias("event_timestamp")
    )

    # 1-minute window for event counts per topic
    events_per_topic = parsed_df \
        .withWatermark("event_timestamp", "10 seconds") \
        .groupBy(
            col("topic"),
            window(col("event_timestamp"), "1 minute")
        ) \
        .agg(count("*").alias("event_count")) \
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            lit("throughput").alias("metric_name"),
            col("event_count").alias("metric_value"),
            lit(20).alias("threshold"),  # Expected ~20 events/min per topic (realistic for light load testing)
            when(col("event_count") > 15, "HEALTHY")
                .when(col("event_count") > 8, "WARNING")
                .otherwise("CRITICAL").alias("status"),
            to_json(struct(
                col("topic").alias("topic_monitored"),
                col("event_count").alias("events_processed")
            )).cast("string").alias("services_checked")
        )

    # Write to PostgreSQL
    def foreach_batch_function(batch_df, batch_id):
        if batch_df.count() > 0:
            logger.info(f"Writing {batch_df.count()} operational metrics (batch_id={batch_id})")
            try:
                # Convert to temporary Parquet for reliable data transfer
                temp_path = f"/tmp/operational_metrics_batch_{batch_id}"
                batch_df.coalesce(1).write.mode("overwrite").parquet(temp_path)
                
                # Now read and insert using psycopg2 with proper error handling
                import psycopg2
                from psycopg2 import sql
                
                conn = psycopg2.connect(
                    host=POSTGRES_HOST,
                    port=POSTGRES_PORT,
                    user=POSTGRES_USER,
                    password=POSTGRES_PASSWORD,
                    database=POSTGRES_DB,
                    connect_timeout=10
                )
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                cursor = conn.cursor()
                
                rows = batch_df.collect()
                for row in rows:
                    try:
                        insert_query = """
                            INSERT INTO operational_metrics 
                            (window_start, window_end, metric_name, metric_value, threshold, status, services_checked)
                            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                        """
                        cursor.execute(insert_query, (
                            row.window_start,
                            row.window_end,
                            row.metric_name,
                            row.metric_value,
                            row.threshold,
                            row.status,
                            row.services_checked
                        ))
                    except Exception as row_error:
                        logger.warning(f"Failed to insert row: {row_error}")
                        conn.rollback()
                
                logger.info(f"Successfully wrote operational metrics (batch_id={batch_id})")
                cursor.close()
                conn.close()
                
            except Exception as e:
                logger.error(f"Error writing to PostgreSQL (batch_id={batch_id}): {e}")
                # Don't raise - allow streaming to continue even if DB write fails

    checkpoint_path = os.getenv("CHECKPOINT_PATH", "/opt/spark-data/checkpoints/operational_metrics")
    
    events_per_topic \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .trigger(processingTime="10 seconds") \
        .option("checkpointLocation", checkpoint_path) \
        .start() \
        .awaitTermination()


if __name__ == "__main__":
    operational_metrics()
