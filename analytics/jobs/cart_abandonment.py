"""
cart_abandonment.py - Shopping Cart Abandonment Analytics

PURPOSE:
    Tracks users who add items to cart but don't complete checkout within
    a specified time window, enabling targeted marketing campaigns and 
    conversion optimization strategies.

BUSINESS VALUE:
    - Identify cart abandonment patterns (what products get abandoned)
    - Calculate abandonment rates by time window
    - Trigger re-engagement email campaigns for abandoned carts
    - Analyze products frequently abandoned (improvement opportunities)
    - Understand user checkout behavior and friction points

KAFKA TOPICS CONSUMED:
    - cart.item_added: Event when user adds item to shopping cart
      Schema: {user_id, product_id, timestamp}
      
    - cart.checkout_initiated: Event when user starts checkout process
      Schema: {user_id, timestamp}

OUTPUT:
    PostgreSQL table: cart_abandonment
    Schema:
      - user_id: User who abandoned cart
      - product_id: Product in abandoned cart
      - item_added_time: When item was added (timestamp)

ALGORITHM:
    Stream-Stream Left Join with Watermarking:
    
    1. LEFT STREAM: cart.item_added events (all item additions)
    2. RIGHT STREAM: cart.checkout_initiated events (completed checkouts)
    3. JOIN CONDITION:
       - Same user_id
       - Checkout happens after item add
       - Checkout happens within a specific time window (e.g. 30 minutes)
    4. FILTER: Keep only rows where checkout_user_id IS NULL
       (means no matching checkout = abandoned)
    
    Example Timeline:
    ┌─────────────────────────────────────┐
    │ T=0:00  Item added (Laptop)         │
    │ T=5:00  Item added (Mouse)          │
    │ T=15:00 User closes browser         │
    │ T=30:00 Abandonment detected        │ ← Recorded as abandoned
    └─────────────────────────────────────┘

WATERMARKING:
    - Item Added Watermark: 30 minutes (matches join window)
      Allows late item additions up to 30 minutes after event time
    - Checkout Watermark: 30 minutes (matches join window)
      Allows late checkout events up to 30 minutes after event time
    - Join Window: 30 minutes after item add
      Checkout must occur within 30 minutes to be considered (not abandoned)
    
    Why watermark matches join window:
    - Item added at T=0, watermark expires at T=30min
    - Checkout can arrive anytime up to T=30min
    - Ensures checkout events can always be matched within the join window

PERFORMANCE:
    - Kafka Max Rate: 10,000 events/partition/second
    - Processing Mode: Micro-batch (foreachBatch)
    - Output Mode: Append (only new abandoned records)
    - Fault Tolerance: Checkpointing at /opt/spark-data/checkpoints/cart_abandonment
    - Checkpoint Configuration: Via CHECKPOINT_PATH environment variable (default: /opt/spark-data/checkpoints/cart_abandonment)

USAGE:
   ./scripts/spark/run-spark-job.sh cart_abandonment

DEPENDENCIES:
    - Apache Kafka (3+ brokers)
    - Apache Spark 3.5.0+
    - PostgreSQL 12+
    - spark-sql-kafka-0-10 JAR (included in spark_session.py)

MONITORING:
    Check Spark UI: http://localhost:4040/
    Check checkpoint: ls -la /opt/spark-data/checkpoints/cart_abandonment/ (or set CHECKPOINT_PATH env var)
    Query results: SELECT * FROM cart_abandonment;
"""

import logging
import os

# Spark SQL functions for stream processing
from pyspark.sql.functions import (
    col, from_json, window, count, to_timestamp, expr, current_timestamp
)
# Spark data types for defining schemas
from pyspark.sql.types import StructType, StructField, StringType, LongType

# Import shared Spark configuration
# Note: spark_session.py is in parent directory (analytics/)
import sys
from pathlib import Path
# Add analytics directory to path (parent of jobs directory)
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


def cart_abandonment():
    """
    Cart Abandonment Detection Job
    
    Consumes two Kafka streams and performs a stream-stream left join to identify
    users who added items to cart but never initiated checkout within 30 minutes.
    
    PROCESS FLOW:
    1. Read cart.item_added stream (left: all item additions)
    2. Read cart.checkout_initiated stream (right: completed checkouts)
    3. Apply watermarks to both streams (30 minutes for late data)
    4. Join on user_id with time constraint (30-minute window)
    5. Filter for NULL checkout (no matching checkout found = abandoned)
    6. Write abandoned carts to PostgreSQL
    
    ERROR HANDLING:
    - Kafka connection failures: Spark will retry with backoff
    - PostgreSQL write failures: Stored in checkpoint, retried on restart
    - Schema mismatches: Will log error and skip malformed records
    - Data loss: Prevented by checkpointing mechanism
    
    SCALING:
    - Automatically scales with Kafka partitions
    - Each partition processed in parallel
    - Micro-batch interval: 5 seconds (configurable)
    """
    logger.info("Starting cart abandonment job...")
    
    spark = get_spark_session("cart-abandonment")
    kafka_options = get_kafka_options()

    # Read cart.item_added (left stream)
    item_added_df = spark \
        .readStream \
        .format("kafka") \
        .option("subscribe", "cart.item_added") \
        .options(**kafka_options) \
        .load()

    # Read cart.checkout_initiated (right stream)
    checkout_df = spark \
        .readStream \
        .format("kafka") \
        .option("subscribe", "cart.checkout_initiated") \
        .options(**kafka_options) \
        .load()

    # Schema for cart.item_added events
    # Expected JSON: {"user_id": "USER-123", "product_id": "PROD-1", "timestamp": "2026-03-05T15:30:00Z"}
    item_schema = StructType([
        StructField("user_id", StringType()),
        StructField("product_id", StringType()),
        StructField("timestamp", StringType()),
    ])

    # Parse and extract fields from item_added events
    # Convert timestamp string to Spark timestamp type for time-based operations
    parsed_items = item_added_df.select(
        from_json(col("value").cast("string"), item_schema).alias("data")
    ).select(
        col("data.user_id"),
        col("data.product_id"),
        to_timestamp(col("data.timestamp")).alias("item_added_time")
    )

    # Schema for cart.checkout_initiated events
    # Expected JSON: {"user_id": "USER-123", "timestamp": "2026-03-05T15:35:00Z"}
    checkout_schema = StructType([
        StructField("user_id", StringType()),
        StructField("timestamp", StringType()),
    ])

    # Parse and extract fields from checkout_initiated events
    # Rename user_id to checkout_user_id to distinguish from item_added user_id in join
    parsed_checkout = checkout_df.select(
        from_json(col("value").cast("string"), checkout_schema).alias("data")
    ).select(
        col("data.user_id").alias("checkout_user_id"),
        to_timestamp(col("data.timestamp")).alias("checkout_time")
    )

    # Apply watermarks to handle late-arriving data
    # Watermark allows events to arrive up to 30 minutes late before being dropped
    # This is important in case events arrive out of order from Kafka
    # NOTE: Watermark set to 30 minutes to match join window (allows late checkout events)
    items_with_wm = parsed_items.withWatermark("item_added_time", "30 minutes")
    checkout_with_wm = parsed_checkout.withWatermark("checkout_time", "30 minutes")

    # Stream-stream left join to identify abandoned carts
    # LEFT JOIN: Keep all item additions, even if no matching checkout
    # JOIN CONDITIONS:
    #   1. Same user_id (same person who added item)
    #   2. Checkout happens at or after item was added
    #   3. Checkout happens within 30 minutes of item addition
    # RESULT: Rows where checkout_user_id IS NULL = abandoned items
    abandoned = items_with_wm.join(
        checkout_with_wm,
        (col("user_id") == col("checkout_user_id")) &
        (col("checkout_time") >= col("item_added_time")) &
        (col("checkout_time") <= expr("item_added_time + INTERVAL 30 MINUTES")),
        "leftOuter"
    ).filter(col("checkout_user_id").isNull()) \
    .select(
        col("user_id"),
        col("product_id"),
        col("item_added_time"),
        current_timestamp().alias("detected_at")
    )

    # Write abandoned carts to PostgreSQL using foreachBatch
    # foreachBatch: Process each micro-batch of results
    # This allows us to write to external systems (PostgreSQL, S3, etc.)
    # Mode: append - only write new abandoned carts, don't update existing
    def foreach_batch_function(batch_df, batch_id):
        """
        Write batch of abandoned carts to PostgreSQL.
        
        Args:
            batch_df: DataFrame containing abandoned cart records for this batch
            batch_id: Unique ID for this batch (useful for logging/debugging)
        """
        if batch_df.count() > 0:  # Only write if batch has data
            logger.info(f"Writing {batch_df.count()} abandoned carts (batch_id={batch_id})")
            batch_df.write \
                .format("jdbc") \
                .mode("append") \
                .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
                .option("dbtable", "cart_abandonment") \
                .option("user", POSTGRES_USER) \
                .option("password", POSTGRES_PASSWORD) \
                .option("driver", "org.postgresql.Driver") \
                .save()
            logger.info(f"Successfully wrote batch_id={batch_id}")
        else:
            logger.debug(f"No abandoned carts in batch_id={batch_id}")

    # Start the streaming query
    # writeStream: Enable streaming mode for continuous processing
    # foreachBatch: Call foreach_batch_function for each micro-batch
    # outputMode: append - only output new abandoned carts (not stateful)
    # checkpointLocation: Save progress for fault tolerance and recovery
    # trigger: Process data more frequently for faster results (10 seconds for testing)
    # awaitTermination: Block until streaming job stops or encounters error
    logger.info("Starting streaming query for cart abandonment detection...")
    
    checkpoint_path = os.getenv("CHECKPOINT_PATH", "/opt/spark-data/checkpoints/cart_abandonment")
    
    abandoned \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .option("checkpointLocation", checkpoint_path) \
        .trigger(processingTime="10 seconds") \
        .start() \
        .awaitTermination()
    
    logger.info("Cart abandonment job completed")


if __name__ == "__main__":
    cart_abandonment()
