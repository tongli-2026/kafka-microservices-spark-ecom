"""
fraud_detection.py - Real-Time Fraud Detection and Prevention

PURPOSE:
    Analyzes payment events in real-time to detect suspicious patterns and
    potential fraud, enabling immediate alerts and transaction blocking before
    money is transferred.

BUSINESS VALUE:
    - Real-time fraud detection (alerts within seconds)
    - Prevent financial losses from fraudulent transactions
    - Detect coordinated fraud patterns across users
    - Track high-risk payment behaviors
    - Support compliance and risk management

KAFKA TOPICS CONSUMED:
    - payment.processed: Successful payment transaction events
      Schema: {amount, user_id, order_id, timestamp}
    - order.created: Order placement events
      Schema: {total_amount, user_id, order_id, timestamp}

OUTPUT:
    PostgreSQL table: fraud_alerts
    Schema:
      - alert_id: Unique alert identifier (format: user_id_window_start_timestamp)
      - alert_timestamp: When alert was triggered (window start time)
      - user_id: User involved in suspicious activity
      - order_id: Order associated with alert (NULL - aggregated alerts span multiple orders)
      - alert_type: Type of fraud detected (HIGH_ORDER_VALUE, UNUSUAL_ORDER_FREQUENCY, MULTIPLE_PAYMENT_EVENTS)
      - severity: Alert severity level (MEDIUM, HIGH, CRITICAL)
      - details: JSON object containing {order_frequency, max_amount, failed_count, window_start, window_end}

FRAUD DETECTION RULES:
    1. HIGH_ORDER_VALUE: Order amount > $1,000 in any 5-minute window
       - Indicates unusually large transaction
       - Severity: CRITICAL if amount > $5,000, HIGH if > $1,000
    
    2. UNUSUAL_ORDER_FREQUENCY: >3 orders within 5 minutes from same user
       - Indicates rapid automated ordering or account compromise
       - Severity: HIGH
    
    3. MULTIPLE_PAYMENT_EVENTS: >2 payment events within 5 minutes
       - Indicates velocity in payment processing (retry loops)
       - Severity: MEDIUM (triggering threshold), CRITICAL if >5

DETECTION ALGORITHM:
    Stream Aggregation with Rule Engine:
    
    1. STREAM INPUT: 
       - payment.processed events (successful payments)
       - order.created events (order placement)
    
    2. AGGREGATION: 5-minute tumbling windows with 1-minute sliding step:
       Creates overlapping analysis windows that slide every minute:
       
       Timeline:  0:00 ─────────────────────────────────→ 10:00
       
       Window 1:  [0:00────5:00]
       Window 2:       [1:00────6:00]
       Window 3:            [2:00────7:00]
       Window 4:                 [3:00────8:00]
       Window 5:                      [4:00────9:00]
       Window 6:                           [5:00────10:00]
       
       Benefits: Better fraud detection (catches patterns across boundaries),
                 more frequent checks (every 1 min vs 5 min), smoother latency
       
       Per-window aggregation:
       - order_count: Number of orders in window
       - max_order_amount: Largest order amount in window
       - payment_count: Number of payment events in window
    
    3. RULES EVALUATION (per user, per window):
       - HIGH_ORDER_VALUE: If max_order_amount > $1,000
       - UNUSUAL_ORDER_FREQUENCY: If order_count > 3
       - MULTIPLE_PAYMENT_EVENTS: If payment_count > 2
    
    4. ALERT: Generate alert if ANY rule triggered
    
    5. SEVERITY DETERMINATION:
       - CRITICAL: order_count > 5 OR amount > $5,000 OR payment_count > 5
       - HIGH: order_count > 3 OR amount > $1,000
       - MEDIUM: Otherwise
    
    6. OUTPUT: Write to PostgreSQL fraud_alerts table
    
    Example Detection:
    ┌─────────────────────────────────────┐
    │ T=14:30:00  Order $1,500            │ → HIGH_ORDER_VALUE alert
    │ T=14:30:15  Order $1,200            │ 
    │ T=14:30:45  Order $900              │ → UNUSUAL_ORDER_FREQUENCY alert
    │             (3 orders in 45 sec)    │    Severity: HIGH
    │             plus payment events     │
    └─────────────────────────────────────┘

WINDOWING:
    - Detection Window: 5-minute tumbling windows with 1-minute sliding step (for velocity analysis)
    - Watermark: 10 seconds for late data tolerance
    - Trigger: Process every 10 seconds (micro-batch interval)
    - Output Mode: Append (only new alerts)

PERFORMANCE:
    - Kafka Max Rate: 10,000 events/partition/second
    - Processing Mode: Micro-batch (foreachBatch)
    - Output Mode: Append (only new alerts)
    - Fault Tolerance: Checkpointing at /opt/spark-data/checkpoints/fraud_detection
    - Checkpoint Configuration: Via CHECKPOINT_PATH environment variable (default: /opt/spark-data/checkpoints/fraud_detection)

USAGE:
    ./scripts/spark/run-spark-job.sh fraud_detection

DEPENDENCIES:
    - Apache Kafka (3+ brokers)
    - Apache Spark 3.5.0+
    - PostgreSQL 12+
    - spark-sql-kafka-0-10 JAR (included in spark_session.py)

MONITORING:
    Check Spark UI: http://localhost:4040/
    Check alerts: SELECT * FROM fraud_alerts WHERE severity='CRITICAL';
    Check checkpoint: ls -la /opt/spark-data/checkpoints/fraud_detection/ (or set CHECKPOINT_PATH env var)
"""

import json
import logging
import os

# Spark SQL functions for data transformations
from pyspark.sql.functions import (
    col, from_json, schema_of_json, window, count, max, sum,
    to_timestamp, when, lit, dense_rank, struct, concat, 
    unix_timestamp, to_json
)
# Spark data types for schema definitions
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType
# Window functions for ranking and aggregation
from pyspark.sql.window import Window as WindowSpec

# Import shared Spark session configuration
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


def fraud_detection():
    """
    Job 2: Fraud detection aggregation.
    Monitor for suspicious patterns in payment and order data.
    """
    logger.info("Starting fraud detection job...")
    
    spark = get_spark_session("fraud-detection")
    kafka_options = get_kafka_options()

    # Read payment.processed
    payment_df = spark \
        .readStream \
        .format("kafka") \
        .option("subscribe", "payment.processed") \
        .options(**kafka_options) \
        .load()

    # Read order.created
    order_df = spark \
        .readStream \
        .format("kafka") \
        .option("subscribe", "order.created") \
        .options(**kafka_options) \
        .load()

    # Parse payment events
    payment_schema = StructType([
        StructField("amount", DoubleType()),
        StructField("user_id", StringType()),
        StructField("order_id", StringType()),
        StructField("timestamp", StringType()),
    ])

    parsed_payment = payment_df.select(
        from_json(col("value").cast("string"), payment_schema).alias("data")
    ).select(
        col("data.amount"),
        col("data.user_id"),
        col("data.order_id"),
        lit("payment").alias("source"),
        to_timestamp(col("data.timestamp")).alias("event_timestamp")
    )

    # Parse order events
    order_schema = StructType([
        StructField("total_amount", DoubleType()),
        StructField("user_id", StringType()),
        StructField("order_id", StringType()),
        StructField("timestamp", StringType()),
    ])

    parsed_order = order_df.select(
        from_json(col("value").cast("string"), order_schema).alias("data"),
        col("timestamp")
    ).select(
        col("data.total_amount").alias("amount"),
        col("data.user_id"),
        col("data.order_id"),
        lit("order").alias("source"),
        to_timestamp(col("data.timestamp")).alias("event_timestamp")
    )

    # Union streams
    combined_df = parsed_payment.union(parsed_order)

    # Apply watermark and sliding window
    windowed_df = combined_df \
        .withWatermark("event_timestamp", "10 seconds") \
        .groupBy(
            col("user_id"),
            window(col("event_timestamp"), "5 minutes", "1 minute")
        ) \
        .agg(
            count("*").alias("event_count"),
            count(when(col("source") == "order", 1)).alias("order_count"),
            max("amount").alias("max_order_amount"),
            sum(when(col("source") == "payment", 1)).alias("payment_count")
        )

    # Detect fraud and format for database
    fraud_df = windowed_df \
        .filter(
            (col("order_count") > 3) |
            (col("max_order_amount") > 1000) |
            (col("payment_count") > 2)
        ) \
        .select(
            concat(col("user_id"), lit("_"), unix_timestamp(col("window.start")).cast("string")).alias("alert_id"),
            col("window.start").alias("alert_timestamp"),
            col("user_id"),
            lit(None).cast("string").alias("order_id"),
            when(col("order_count") > 3, "UNUSUAL_ORDER_FREQUENCY")
                .when(col("max_order_amount") > 1000, "HIGH_ORDER_VALUE")
                .when(col("payment_count") > 2, "MULTIPLE_PAYMENT_EVENTS")
                .alias("alert_type"),
            when(col("order_count") > 5, "CRITICAL")
                .when(col("max_order_amount") > 5000, "CRITICAL")
                .when(col("payment_count") > 5, "CRITICAL")
                .when(col("order_count") > 3, "HIGH")
                .when(col("max_order_amount") > 1000, "HIGH")
                .otherwise("MEDIUM").alias("severity"),
            to_json(struct(
                col("order_count").alias("order_frequency"),
                col("max_order_amount").alias("max_amount"),
                col("payment_count").alias("failed_count"),
                col("window.start").alias("window_start"),
                col("window.end").alias("window_end")
            )).alias("details")
        )

    # Write to PostgreSQL with upsert to handle duplicate batches
    def foreach_batch_function(batch_df, batch_id):
        if batch_df.count() > 0:
            logger.info(f"Writing {batch_df.count()} fraud alerts (batch_id={batch_id})")
            
            # Use psycopg2 to run upsert query directly
            import psycopg2
            
            try:
                # Collect the data from Spark DataFrame
                rows = batch_df.collect()
                
                conn = psycopg2.connect(
                    host=POSTGRES_HOST,
                    port=POSTGRES_PORT,
                    database=POSTGRES_DB,
                    user=POSTGRES_USER,
                    password=POSTGRES_PASSWORD
                )
                cursor = conn.cursor()
                
                # Insert with ON CONFLICT DO UPDATE (upsert)
                for row in rows:
                    cursor.execute("""
                        INSERT INTO fraud_alerts (alert_id, user_id, alert_type, severity, details, alert_timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (alert_id) DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            alert_type = EXCLUDED.alert_type,
                            severity = EXCLUDED.severity,
                            details = EXCLUDED.details,
                            alert_timestamp = EXCLUDED.alert_timestamp
                    """, (
                        row.alert_id,
                        row.user_id,
                        row.alert_type,
                        row.severity,
                        row.details,
                        row.alert_timestamp
                    ))
                
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"Successfully wrote {len(rows)} fraud alerts with upsert (batch_id={batch_id})")
            except Exception as e:
                logger.error(f"Error writing fraud alerts: {e}")
                raise

    checkpoint_path = os.getenv("CHECKPOINT_PATH", "/opt/spark-data/checkpoints/fraud_detection")
    
    fraud_df \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .option("checkpointLocation", checkpoint_path) \
        .trigger(processingTime="10 seconds") \
        .start() \
        .awaitTermination()


if __name__ == "__main__":
    fraud_detection()
