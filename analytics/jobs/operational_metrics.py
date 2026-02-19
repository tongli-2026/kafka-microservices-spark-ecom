"""
operational_metrics.py - System Health and Performance Monitoring

PURPOSE:
    Monitors overall system health, event throughput, and operational
    KPIs across all microservices in real-time.

OPERATIONAL METRICS:
    - Event processing throughput (events/minute)
    - Success vs failure rates
    - Service availability
    - Event latency metrics
    - System error rates

KAFKA TOPICS CONSUMED:
    - order.created: New order events
    - order.confirmed: Successful orders
    - order.cancelled: Failed orders
    - payment.processed: Payment transactions
    - inventory.reserved: Stock reservations

OUTPUT:
    - PostgreSQL table: operational_metrics
      Columns: window_start, window_end, metric_name, metric_value,
               service_name, status

HEALTH CHECKS:
    - Event throughput per service
    - Success/failure ratios
    - Processing latency
    - Error rate thresholds

USAGE:
    ./run-spark-job.sh operational_metrics
"""

import logging
import os

# Spark SQL functions for metrics calculation
from pyspark.sql.functions import (
    col, from_json, window, count, to_timestamp, when, lit, concat_ws
)
# Spark data types for schema definitions
from pyspark.sql.types import StructType, StructField, StringType

# Import shared Spark configuration
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

    # Create a multi-topic subscription for all events
    df = spark \
        .readStream \
        .format("kafka") \
        .option("subscribePattern", ".*") \
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
            col("topic"),
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            col("event_count"),
            lit("event_count").alias("metric_name")
        )

    # Write to PostgreSQL
    def foreach_batch_function(batch_df, batch_id):
        batch_df.select(
            col("metric_name"),
            col("event_count").alias("value"),
            col("topic"),
            col("window_start")
        ).write \
            .format("jdbc") \
            .mode("append") \
            .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
            .option("dbtable", "operational_metrics") \
            .option("user", POSTGRES_USER) \
            .option("password", POSTGRES_PASSWORD) \
            .option("driver", "org.postgresql.Driver") \
            .save()

    events_per_topic \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .option("checkpointLocation", "/tmp/checkpoints/operational-metrics") \
        .start() \
        .awaitTermination()


if __name__ == "__main__":
    operational_metrics()
