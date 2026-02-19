"""
inventory_velocity.py - Product Sales Velocity Analytics

PURPOSE:
    Tracks product sales velocity to optimize inventory management,
    identify trending products, and prevent stockouts.

BUSINESS VALUE:
    - Calculate units sold per hour/day
    - Identify fast-moving vs slow-moving products
    - Predict inventory needs
    - Optimize reorder points
    - Detect trending products early

KAFKA TOPICS CONSUMED:
    - order.confirmed: Successfully completed orders with product details

OUTPUT:
    - PostgreSQL table: inventory_velocity
      Columns: window_start, window_end, product_id, units_sold, 
               revenue, velocity_score, rank

VELOCITY METRICS:
    - Units sold per time window (1 hour)
    - Revenue per product
    - Velocity score (sales rate ranking)
    - Product ranking by sales volume

USAGE:
    ./run-spark-job.sh inventory_velocity
"""

import logging
import os

# Spark SQL functions for aggregation and ranking
from pyspark.sql.functions import (
    col, from_json, window, sum, to_timestamp, dense_rank, desc
)
# Spark data types for schema definitions
from pyspark.sql.types import StructType, StructField, StringType, LongType
# Window functions for ranking operations
from pyspark.sql.window import Window

# Import shared Spark session utilities
from spark_session import get_spark_session, get_kafka_options

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "kafka_ecom")


def inventory_velocity():
    """
    Job 4: Inventory velocity and demand.
    Track which products are selling fastest.
    """
    logger.info("Starting inventory velocity job...")
    
    spark = get_spark_session("inventory-velocity")
    kafka_options = get_kafka_options()

    # Read inventory.reserved events
    df = spark \
        .readStream \
        .format("kafka") \
        .option("subscribe", "inventory.reserved") \
        .options(**kafka_options) \
        .load()

    # Parse JSON
    schema = StructType([
        StructField("product_id", StringType()),
        StructField("quantity", LongType()),
        StructField("timestamp", StringType()),
    ])

    parsed_df = df.select(
        from_json(col("value").cast("string"), schema).alias("data")
    ).select(
        col("data.product_id"),
        col("data.quantity"),
        to_timestamp(col("data.timestamp")).alias("event_timestamp")
    )

    # Apply watermark and tumbling window
    windowed_df = parsed_df \
        .withWatermark("event_timestamp", "10 seconds") \
        .groupBy(
            col("product_id"),
            window(col("event_timestamp"), "1 hour")
        ) \
        .agg(sum("quantity").alias("units_sold")) \
        .select(
            col("product_id"),
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            "units_sold"
        )

    # Write to PostgreSQL (ranking is done in batch mode)
    def foreach_batch_function(batch_df, batch_id):
        if batch_df.count() > 0:
            # Rank top 10 products per window (done in batch mode)
            window_spec = Window.partitionBy("window_start").orderBy(desc("units_sold"))
            ranked_df = batch_df \
                .withColumn("rank", dense_rank().over(window_spec)) \
                .filter(col("rank") <= 10)
            
            ranked_df.write \
                .format("jdbc") \
                .mode("append") \
                .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
                .option("dbtable", "inventory_velocity") \
                .option("user", POSTGRES_USER) \
                .option("password", POSTGRES_PASSWORD) \
                .option("driver", "org.postgresql.Driver") \
                .save()

    windowed_df \
        .writeStream \
        .foreachBatch(foreach_batch_function) \
        .outputMode("append") \
        .option("checkpointLocation", "/tmp/checkpoints/inventory-velocity") \
        .start() \
        .awaitTermination()


if __name__ == "__main__":
    inventory_velocity()
