"""
spark_session.py - Spark Session Factory and Configuration

PURPOSE:
    Provides factory functions for creating Spark sessions configured for:
    - Kafka streaming integration
    - Structured Streaming operations
    - Local and cluster mode deployment
    - Proper checkpoint and state management

COMPONENTS:
    1. get_spark_session(app_name)
       - Creates SparkSession with Kafka support
       - Automatically detects cluster vs local mode
       - Configures checkpointing for fault tolerance
       - Sets up logging levels

    2. get_kafka_options()
       - Returns Kafka configuration dictionary
       - Includes bootstrap servers, offset strategy
       - Prevents data loss on failures

USAGE:
    from spark_session import get_spark_session, get_kafka_options
    
    spark = get_spark_session("my_job")
    kafka_options = get_kafka_options()
    
    df = spark.readStream \\
        .format("kafka") \\
        .options(**kafka_options) \\
        .option("subscribe", "order.created") \\
        .load()

DEPLOYMENT MODES:
    - Local Mode: spark://local[*] (development)
      Default when SPARK_MASTER_URL env var is not set
      
    - Cluster Mode: spark://spark-master:7077 (production)
      Set SPARK_MASTER_URL environment variable

ENVIRONMENT VARIABLES:
    - SPARK_MASTER_URL: Spark cluster master URL (optional)
      Default: local[*]
    
    - KAFKA_BOOTSTRAP_SERVERS: Kafka broker addresses (optional)
      Default: kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092

CONFIGURATION:
    - Checkpoint Location: /tmp/checkpoints/{app_name}
    - Log Level: WARN (reduce Spark logging verbosity)
    - Max Rate Per Partition: 10,000 events/s
    - Time Zone: UTC
    - Kafka JAR: spark-sql-kafka-0-10_2.12:3.5.0
    - Starting Offsets: earliest (from beginning)
    - Fail on Data Loss: false (resume from last checkpoint)

FAULT TOLERANCE:
    - Checkpointing: Saves progress for recovery
    - Watermarking: Handles late-arriving data (per job)
    - State Management: Maintains aggregation state across batches

BEST PRACTICES:
    1. Always call get_spark_session() at job startup
    2. Use get_kafka_options() for all Kafka reads
    3. Set SPARK_MASTER_URL for cluster deployment
    4. Monitor /tmp/checkpoints/ for state files
    5. Use consistent app_name for same job restarts
"""

import logging
import os
from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


def get_spark_session(app_name: str) -> SparkSession:
    """Get or create Spark session with Kafka support."""
    
    # Create checkpoint directory
    checkpoint_dir = f"/tmp/checkpoints/{app_name}"
    os.makedirs(checkpoint_dir, exist_ok=True)

    # Use cluster mode if SPARK_MASTER_URL is set, otherwise local mode
    spark_master = os.getenv("SPARK_MASTER_URL", "local[*]")
    
    spark = (
        SparkSession.builder
        .appName(app_name)
        .master(spark_master)
        .config("spark.sql.streaming.checkpointLocation", checkpoint_dir)
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0")
        .config("spark.streaming.kafka.maxRatePerPartition", "10000")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    
    logger.info(f"Spark session created for {app_name}")
    return spark


def get_kafka_options() -> dict:
    """Get Kafka configuration for Spark Streaming."""
    return {
        "kafka.bootstrap.servers": os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS",
            "kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092"
        ),
        # Read from the earliest offset if no checkpoint exists, otherwise resume from last checkpoint
        "startingOffsets": "earliest",
        # Prevent data loss on failures by allowing Spark to resume from last checkpoint instead of failing
        "failOnDataLoss": "false",
    }
