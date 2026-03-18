"""
revenue_streaming.py - Real-Time Revenue Analytics

PURPOSE:
    Aggregates payment events from Kafka in real-time to compute revenue metrics
    across configurable time windows, enabling live business intelligence and
    revenue monitoring dashboards.

BUSINESS VALUE:
    - Real-time revenue tracking (update every 10 seconds)
    - Hourly/daily revenue aggregations
    - Order volume and average order value metrics
    - Detect revenue anomalies or drops immediately
    - Support live dashboards and alerts

KAFKA TOPICS CONSUMED:
    - payment.processed: Successful payment transaction events
      Schema: {order_id, user_id, amount, timestamp}

OUTPUT:
    PostgreSQL table: revenue_metrics
    Schema:
      - window_start: Start of aggregation window
      - window_end: End of aggregation window
      - total_revenue: Sum of all payment amounts in window
      - order_count: Number of successful payments in window
      - avg_order_value: Average payment amount in window

ALGORITHM:
    Time-Series Aggregation with Windowing:
    
    1. STREAM INPUT: payment.processed events (all successful payments)
    2. TIMESTAMP: Extract event timestamp for windowing
    3. WINDOW: Aggregate into configurable time windows (default: 1 minute)
    4. AGGREGATION:
       - SUM(amount) → total_revenue
       - COUNT(*) → order_count
       - AVG(amount) → avg_order_value
    5. OUTPUT: Write window results to PostgreSQL
    
    Example Timeline:
    ┌─────────────────────────────────────┐
    │ T=0:00-1:00   Collect 150 payments  │
    │ T=1:00        Aggregated results:   │
    │               - Revenue: $45,234.50 │
    │               - Orders: 150         │
    │               - Avg Order: $301.56  │ ← Written to DB
    └─────────────────────────────────────┘

WINDOWING:
    - Window Duration: 1 minute (configurable)
    - Window Type: Tumbling (non-overlapping)
    - Watermark: 10 seconds for late data
    - Trigger: Process every 10 seconds

PERFORMANCE:
    - Kafka Max Rate: 10,000 events/partition/second
    - Processing Mode: Micro-batch (foreachBatch)
    - Output Mode: Append (only new window results)
    - Fault Tolerance: Checkpointing at /opt/spark-data/checkpoints/revenue_streaming
    - Checkpoint Configuration: Via CHECKPOINT_PATH environment variable (default: /opt/spark-data/checkpoints/revenue_streaming)

USAGE:
    ./scripts/spark/run-spark-job.sh revenue_streaming

DEPENDENCIES:
    - Apache Kafka (3+ brokers)
    - Apache Spark 3.5.0+
    - PostgreSQL 12+
    - spark-sql-kafka-0-10 JAR (included in spark_session.py)

MONITORING:
    Check Spark UI: http://localhost:4040/
    Check checkpoint: ls -la /opt/spark-data/checkpoints/revenue_streaming/ (or set CHECKPOINT_PATH env var)
    Query results: SELECT * FROM revenue_metrics LIMIT 5;
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
    to_timestamp,  # Convert string timestamps to timestamp type
    current_timestamp  # Get current server timestamp
)
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType

# Import custom Spark session utilities
# Note: spark_session.py is in parent directory (analytics/)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
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


def revenue_streaming():
    """
    Main revenue streaming analytics function.
    
    This function:
    1. Connects to Kafka and reads payment.processed events
    2. Parses JSON payment data
    3. Groups payments into 1-minute tumbling windows
    4. Calculates revenue aggregations (total_revenue, order_count, avg_order_value)
    5. Writes results to PostgreSQL revenue_metrics table
    6. Runs continuously until terminated
    
    Streaming Configuration:
        - Window Size: 1 minute (tumbling window)
        - Watermark: 10 seconds (handles late data)
        - Output Mode: Append (only new complete windows)
        - Checkpoint: Configured via CHECKPOINT_PATH env var (default: /opt/spark-data/checkpoints/revenue_streaming)
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
            "avg_order_value",
            current_timestamp().alias("created_at")
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
        # Write this batch to PostgreSQL (overwrite to prevent duplicates on re-runs)
        batch_df.write \
            .format("jdbc") \
            .mode("overwrite") \
            .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
            .option("dbtable", "revenue_metrics") \
            .option("user", POSTGRES_USER) \
            .option("password", POSTGRES_PASSWORD) \
            .option("driver", "org.postgresql.Driver") \
            .save()

    # Step 6: Start the streaming query
    # This will continuously process data and call foreach_batch_function for each batch
    checkpoint_path = os.getenv("CHECKPOINT_PATH", "/opt/spark-data/checkpoints/revenue_streaming")
    
    windowed_df \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .option("checkpointLocation", checkpoint_path) \
        .start() \
        .awaitTermination()


if __name__ == "__main__":
    # Entry point: Start the revenue streaming job
    revenue_streaming()
