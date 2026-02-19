"""
cart_abandonment.py - Shopping Cart Abandonment Analytics

PURPOSE:
    Tracks users who add items to cart but don't complete checkout,
    enabling targeted marketing campaigns and conversion optimization.

BUSINESS VALUE:
    - Identify cart abandonment patterns
    - Calculate abandonment rate by time window
    - Trigger re-engagement email campaigns
    - Analyze products frequently abandoned

KAFKA TOPICS CONSUMED:
    - cart.item_added: When user adds item to cart
    - cart.checkout_initiated: When user starts checkout

OUTPUT:
    - PostgreSQL table: cart_abandonment
      Columns: window_start, window_end, total_carts, abandoned_carts, 
               abandonment_rate, avg_cart_value

TRACKING LOGIC:
    - 10-minute tumbling windows
    - Cart considered abandoned if no checkout within 10 minutes
    - Watermarking: 15 seconds for late events

USAGE:
    ./run-spark-job.sh cart_abandonment
"""

import logging
import os

# Spark SQL functions for stream processing
from pyspark.sql.functions import (
    col, from_json, window, count, to_timestamp, expr
)
# Spark data types for defining schemas
from pyspark.sql.types import StructType, StructField, StringType, LongType

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


def cart_abandonment():
    """
    Job 3: Cart abandonment tracker.
    Identify users who added items but didn't checkout.
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

    # Parse item_added events
    item_schema = StructType([
        StructField("user_id", StringType()),
        StructField("product_id", StringType()),
        StructField("timestamp", StringType()),
    ])

    parsed_items = item_added_df.select(
        from_json(col("value").cast("string"), item_schema).alias("data")
    ).select(
        col("data.user_id"),
        col("data.product_id"),
        to_timestamp(col("data.timestamp")).alias("item_added_time")
    )

    # Parse checkout events
    checkout_schema = StructType([
        StructField("user_id", StringType()),
        StructField("timestamp", StringType()),
    ])

    parsed_checkout = checkout_df.select(
        from_json(col("value").cast("string"), checkout_schema).alias("data")
    ).select(
        col("data.user_id").alias("checkout_user_id"),
        to_timestamp(col("data.timestamp")).alias("checkout_time")
    )

    # Apply watermarks
    items_with_wm = parsed_items.withWatermark("item_added_time", "30 minutes")
    checkout_with_wm = parsed_checkout.withWatermark("checkout_time", "30 minutes")

    # Stream-stream left join
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
        col("item_added_time")
    )

    # Write to PostgreSQL
    def foreach_batch_function(batch_df, batch_id):
        batch_df.write \
            .format("jdbc") \
            .mode("append") \
            .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
            .option("dbtable", "cart_abandonment") \
            .option("user", POSTGRES_USER) \
            .option("password", POSTGRES_PASSWORD) \
            .option("driver", "org.postgresql.Driver") \
            .save()

    abandoned \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .option("checkpointLocation", "/tmp/checkpoints/cart-abandonment") \
        .start() \
        .awaitTermination()


if __name__ == "__main__":
    cart_abandonment()
