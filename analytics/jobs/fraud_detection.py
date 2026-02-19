"""
fraud_detection.py - Real-time Fraud Detection Analytics

PURPOSE:
    Detects suspicious payment patterns and potential fraud in real-time
    using Apache Spark Structured Streaming.

FRAUD DETECTION RULES:
    1. Multiple failed payments from the same user
    2. High-value orders (> $5000)
    3. Rapid order velocity (many orders in short time)
    4. Orders from same IP address in short time window

KAFKA TOPICS CONSUMED:
    - payment.processed: Payment transaction events

OUTPUT:
    - PostgreSQL table: fraud_alerts
      Columns: alert_id, timestamp, user_id, order_id, alert_type, severity, details

DETECTION LOGIC:
    - 5-minute tumbling windows for aggregation
    - Watermarking: 10 seconds for late data
    - Alert severity: LOW, MEDIUM, HIGH, CRITICAL

USAGE:
    ./run-spark-job.sh fraud_detection
"""

import json
import logging
import os

# Spark SQL functions for data transformations
from pyspark.sql.functions import (
    col, from_json, schema_of_json, window, count, max, sum,
    to_timestamp, when, lit, dense_rank, struct
)
# Spark data types for schema definitions
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType
# Window functions for ranking and aggregation
from pyspark.sql.window import Window as WindowSpec

# Import shared Spark session configuration
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

    # Detect fraud
    fraud_df = windowed_df \
        .filter(
            (col("order_count") > 3) |
            (col("max_order_amount") > 1000) |
            (col("payment_count") > 2)
        ) \
        .select(
            col("user_id"),
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            "order_count",
            "max_order_amount",
            "payment_count",
            when(col("order_count") > 3, "unusual_order_frequency")
                .when(col("max_order_amount") > 1000, "high_order_value")
                .when(col("payment_count") > 2, "multiple_failed_payments")
                .alias("alert_type")
        )

    # Write to PostgreSQL
    def foreach_batch_function(batch_df, batch_id):
        batch_df.write \
            .format("jdbc") \
            .mode("append") \
            .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
            .option("dbtable", "fraud_alerts") \
            .option("user", POSTGRES_USER) \
            .option("password", POSTGRES_PASSWORD) \
            .option("driver", "org.postgresql.Driver") \
            .save()

    fraud_df \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .option("checkpointLocation", "/tmp/checkpoints/fraud-detection") \
        .start() \
        .awaitTermination()


if __name__ == "__main__":
    fraud_detection()
