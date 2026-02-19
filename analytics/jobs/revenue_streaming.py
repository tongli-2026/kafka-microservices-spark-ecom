"""
Revenue Streaming Analytics Job

Purpose:
    This Spark Structured Streaming job processes payment events from Kafka in real-time
    and aggregates revenue metrics into 1-minute windows. It demonstrates:
    - Real-time stream processing from Kafka
    - Time-based windowing aggregations
    - Continuous writes to PostgreSQL
    
Data Flow:
    Kafka (payment.processed) → Spark Streaming → PostgreSQL (revenue_metrics)
    
Output Metrics (per 1-minute window):
    - total_revenue: Sum of all payment amounts
    - order_count: Number of successful payments
    - avg_order_value: Average payment amount
    
Usage:
    spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 revenue_streaming.py
"""

import json
import logging
import os
from datetime import datetime

# Import Spark SQL functions for data transformations
from pyspark.sql.functions import (
    col,           # Reference DataFrame columns
    from_json,     # Parse JSON strings into structured data
    window,        # Create time-based windows for aggregation
    sum,           # Sum aggregation
    count,         # Count aggregation
    avg,           # Average aggregation
    to_timestamp   # Convert string timestamps to timestamp type
)
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType

# Import custom Spark session utilities
from spark_session import get_spark_session, get_kafka_options

# Configure logging to track job execution
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PostgreSQL connection configuration
# These environment variables are set in docker-compose.yml
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")      # Database hostname
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")          # Database port
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")      # Database username
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")  # Database password
POSTGRES_DB = os.getenv("POSTGRES_DB", "kafka_ecom")        # Database name


def write_to_postgres(df, table_name: str, mode: str = "append"):
    """
    Write a Spark DataFrame to PostgreSQL database.
    
    Args:
        df: Spark DataFrame to write
        table_name: Target PostgreSQL table name
        mode: Write mode - "append" (add rows) or "overwrite" (replace table)
        
    Note:
        Uses JDBC driver to connect to PostgreSQL
    """
    try:
        # Construct PostgreSQL JDBC connection URL
        url = f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
        
        # Write DataFrame to PostgreSQL using JDBC
        df.write \
            .format("jdbc") \
            .mode(mode) \
            .option("url", url) \
            .option("dbtable", table_name) \
            .option("user", POSTGRES_USER) \
            .option("password", POSTGRES_PASSWORD) \
            .option("driver", "org.postgresql.Driver") \
            .save()
        logger.info(f"Data written to {table_name}")
    except Exception as e:
        logger.error(f"Error writing to {table_name}: {e}")


def revenue_streaming():
    """
    Main revenue streaming analytics function.
    
    This function:
    1. Connects to Kafka and reads payment.processed events
    2. Parses JSON payment data
    3. Groups payments into 1-minute tumbling windows
    4. Calculates revenue aggregations (total, count, average)
    5. Writes results to PostgreSQL revenue_metrics table
    6. Runs continuously until terminated
    
    Streaming Configuration:
        - Window Size: 1 minute (tumbling window)
        - Watermark: 10 seconds (handles late data)
        - Output Mode: Append (only new complete windows)
        - Checkpoint: /tmp/checkpoints/revenue-streaming
    """
    logger.info("Starting revenue streaming job...")
    
    # Initialize Spark session with application name "revenue-streaming"
    spark = get_spark_session("revenue-streaming")
    
    # Get Kafka connection options (bootstrap servers, etc.)
    kafka_options = get_kafka_options()

    # Step 1: Read streaming data from Kafka topic "payment.processed"
    df = spark \
        .readStream \
        .format("kafka") \
        .option("subscribe", "payment.processed") \
        .options(**kafka_options) \
        .load()

    # Step 2: Define the schema for payment JSON data
    # This tells Spark how to parse the JSON string from Kafka
    schema = StructType([
        StructField("amount", DoubleType()),      # Payment amount
        StructField("user_id", StringType()),     # User who made the payment
        StructField("order_id", StringType()),    # Associated order ID
        StructField("timestamp", StringType()),   # When payment was processed
    ])

    # Step 3: Parse the JSON value from Kafka message
    # Kafka messages have key, value, timestamp, etc.
    # We extract the 'value' field which contains our JSON data
    parsed_df = df.select(
        from_json(col("value").cast("string"), schema).alias("data"),  # Parse JSON
        col("timestamp")  # Keep Kafka ingestion timestamp
    ).select(
        col("data.*"),  # Expand all fields from parsed JSON
        to_timestamp(col("data.timestamp")).alias("event_timestamp")  # Convert to timestamp
    )

    # Step 4: Apply watermark and create 1-minute windows
    # Watermark allows handling late data up to 10 seconds
    # Window groups events into 1-minute tumbling windows based on event_timestamp
    windowed_df = parsed_df \
        .withWatermark("event_timestamp", "10 seconds") \
        .groupBy(window(col("event_timestamp"), "1 minute")) \
        .agg(
            sum("amount").alias("total_revenue"),        # Total revenue in the window
            count("*").alias("order_count"),             # Number of payments in the window
            avg("amount").alias("avg_order_value")       # Average payment amount
        ) \
        .select(
            col("window.start").alias("window_start"),   # Window start time
            col("window.end").alias("window_end"),       # Window end time
            "total_revenue",
            "order_count",
            "avg_order_value"
        )

    # Step 5: Write results to PostgreSQL
    # foreachBatch allows us to write each micro-batch to PostgreSQL
    def foreach_batch_function(batch_df, batch_id):
        """
        Process each micro-batch of streaming data.
        
        Args:
            batch_df: DataFrame containing one micro-batch of results
            batch_id: Unique identifier for this batch
            
        This function is called for each micro-batch (typically every few seconds)
        """
        # Write this batch to PostgreSQL (append new windows to existing data)
        batch_df.write \
            .format("jdbc") \
            .mode("append") \
            .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
            .option("dbtable", "revenue_metrics") \
            .option("user", POSTGRES_USER) \
            .option("password", POSTGRES_PASSWORD) \
            .option("driver", "org.postgresql.Driver") \
            .save()

    # Step 6: Start the streaming query
    # This will continuously process data and call foreach_batch_function for each batch
    windowed_df \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .option("checkpointLocation", "/tmp/checkpoints/revenue-streaming") \
        .start() \
        .awaitTermination()


if __name__ == "__main__":
    # Entry point: Start the revenue streaming job
    revenue_streaming()
