"""
inventory_velocity.py - Real-Time Product Velocity and Inventory Analytics

PURPOSE:
    Analyzes product sales velocity in real-time to optimize inventory management,
    identify trending products, and prevent stockouts or overstock situations.

BUSINESS VALUE:
    - Product popularity tracking via batch analysis of historical orders
    - Identify trending products before competitors
    - Optimize inventory reorder points
    - Prevent stockouts of high-velocity items
    - Identify slow-moving products for clearance
    - Forecast demand based on velocity trends

KAFKA TOPICS CONSUMED:
    None - reads directly from PostgreSQL orders table

OUTPUT:
    PostgreSQL table: inventory_velocity
    Schema:
      - window_start: Start of aggregation window (1-hour)
      - window_end: End of aggregation window
      - product_id: Product identifier
      - units_sold: Total units sold in window
      - revenue: Total revenue from product in window
      - velocity_rank: Product rank by sales volume (1=fastest, N=slowest, only top 10)

VELOCITY METRICS:
    - Units Sold: Raw unit count per time window
    - Revenue: Total revenue generated from product
    - Velocity Score: Sales rate percentile ranking
    - Trend: Increasing/decreasing/stable trend
    - Rank: Relative position vs all other products

DETECTION ALGORITHM:
    Batch SQL Aggregation with Ranking:
    
    1. DATA SOURCE: PostgreSQL orders table (status='FULFILLED')
    2. JSON EXPANSION: Parse items JSON array to individual product rows
    3. WINDOW: Aggregate into 1-hour tumbling windows (based on order created_at)
    4. AGGREGATION (per product, per window):
       - SUM(quantity) → units_sold
       - SUM(item_total) → revenue
    5. RANKING: Rank products by units_sold (descending) within each window
    6. FILTERING: Keep only top 10 products per window
    7. OUTPUT: Write to PostgreSQL with rankings
    
    Example Timeline:
    ┌─────────────────────────────────────┐
    │ 1-Hour Window (T=12:00-13:00)       │
    │ Product Rankings by Units Sold:     │
    │                                     │
    │ Rank 1: Widget A      5,000 units   │ ← Trending!
    │ Rank 2: Gadget B      3,200 units   │
    │ Rank 3: Doohickey C   1,500 units   │
    │ ...                                 │
    │ Rank N: Old Product   5 units       │ ← Clearance candidate
    └─────────────────────────────────────┘

WINDOWING:
    - Window Duration: 1 hour (tumbling windows on order creation time)
    - Window Type: Tumbling (non-overlapping)
    - Processing Mode: Batch SQL query executed once
    - Ranking: Top 10 products by units sold per window (DENSE_RANK)

PERFORMANCE:
    - Processing Mode: One-time batch SQL query via JDBC
    - Output Mode: Append (write results to PostgreSQL table)
    - Query Execution: PostgreSQL-side aggregation (efficient)
    - Data Volume: Reads all FULFILLED orders from PostgreSQL orders table

USAGE:
    ./scripts/spark/run-spark-job.sh inventory_velocity

DEPENDENCIES:
    - Apache Spark 3.5.0+
    - PostgreSQL 12+
    - PostgreSQL JDBC driver (included in spark_session.py)

MONITORING:
    Check Spark UI: http://localhost:4040/
    Check velocity rankings: SELECT * FROM inventory_velocity WHERE velocity_rank <= 10;
    Check latest window: SELECT DISTINCT window_start FROM inventory_velocity ORDER BY window_start DESC LIMIT 1;
"""

import logging
import os

# Import shared Spark session utilities
# Note: spark_session.py is in parent directory (analytics/)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from spark_session import get_spark_session

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
    Track which products are selling fastest by analyzing fulfilled orders.
    
    Data Source: PostgreSQL orders table with items JSON array
    Processing: Use SQL to explode items and aggregate by product
    Output: Product sales velocity rankings to PostgreSQL inventory_velocity table
    """
    logger.info("Starting inventory velocity job...")
    
    spark = get_spark_session("inventory-velocity")

    # Read pre-aggregated inventory velocity directly from PostgreSQL
    # using a SQL query that handles JSON expansion and aggregation
    logger.info("Computing inventory velocity from fulfilled orders...")
    
    # Read using SQL query that expands JSON array and aggregates
    query = """
    WITH expanded_items AS (
        SELECT 
            order_id,
            user_id,
            created_at,
            jsonb_array_elements(items::jsonb) as item
        FROM orders
        WHERE status = 'FULFILLED'
    ),
    product_aggregates AS (
        SELECT
            DATE_TRUNC('hour', created_at) as window_start,
            DATE_TRUNC('hour', created_at) + INTERVAL '1 hour' as window_end,
            item->>'product_id' as product_id,
            SUM((item->>'quantity')::int) as units_sold,
            SUM((item->>'item_total')::decimal) as total_revenue
        FROM expanded_items
        GROUP BY DATE_TRUNC('hour', created_at), item->>'product_id'
    ),
    ranked_products AS (
        SELECT
            window_start,
            window_end,
            product_id,
            units_sold,
            total_revenue as revenue,
            DENSE_RANK() OVER (PARTITION BY window_start ORDER BY units_sold DESC) as velocity_rank
        FROM product_aggregates
    )
    SELECT *
    FROM ranked_products
    WHERE velocity_rank <= 10
    """
    
    result_df = spark.read \
        .format("jdbc") \
        .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
        .option("query", query) \
        .option("user", POSTGRES_USER) \
        .option("password", POSTGRES_PASSWORD) \
        .option("driver", "org.postgresql.Driver") \
        .load()

    logger.info(f"Loaded {result_df.count()} velocity records")

    # Write to PostgreSQL in overwrite mode
    # Since we re-aggregate ALL historical orders each run, we replace old data
    # to avoid duplicates from repeated job executions
    result_df.write \
        .format("jdbc") \
        .mode("overwrite") \
        .option("url", f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}") \
        .option("dbtable", "inventory_velocity") \
        .option("user", POSTGRES_USER) \
        .option("password", POSTGRES_PASSWORD) \
        .option("driver", "org.postgresql.Driver") \
        .save()

    logger.info("✅ Inventory velocity job completed successfully")


if __name__ == "__main__":
    inventory_velocity()
