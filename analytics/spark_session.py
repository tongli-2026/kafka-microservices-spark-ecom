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
        "startingOffsets": "earliest",
        "failOnDataLoss": "false",
    }
