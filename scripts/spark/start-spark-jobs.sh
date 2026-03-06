#!/bin/bash

################################################################################
# start-spark-jobs.sh - Start Spark Streaming Jobs (Detached)
#
# PURPOSE:
#   Starts Spark streaming jobs in Docker containers in detached mode
#   so they continue running even after the script exits.
#
# USAGE:
#   ./start-spark-jobs.sh
#
# NOTES:
#   Jobs run inside Docker containers and continue even if shell exits.
#   View logs with: docker logs spark-job-revenue, etc.
#
################################################################################

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting Spark Streaming Jobs in Docker${NC}"
echo ""

# Check if Spark cluster is running
if ! docker ps | grep -q spark-master; then
    echo -e "${RED}Error: Spark cluster not running${NC}"
    echo "Start with: docker-compose up -d"
    exit 1
fi

echo -e "${YELLOW}Starting revenue_streaming job...${NC}"
docker run -d \
  --name spark-job-revenue \
  --network kafka-ecom \
  -v /opt/spark-apps:/opt/spark-apps \
  -v /opt/spark-data:/opt/spark-data \
  --entrypoint bash \
  spark-custom:latest \
  -c "cd /opt/spark-apps && PYTHONPATH=/opt/spark-apps:\$PYTHONPATH /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --driver-memory 2g \
    --executor-memory 2g \
    --total-executor-cores 4 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/revenue_streaming \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/revenue_streaming.py" 2>&1 | tee /tmp/spark-revenue.log || true

echo -e "${YELLOW}Starting fraud_detection job...${NC}"
docker run -d \
  --name spark-job-fraud \
  --network kafka-ecom \
  -v /opt/spark-apps:/opt/spark-apps \
  -v /opt/spark-data:/opt/spark-data \
  --entrypoint bash \
  spark-custom:latest \
  -c "cd /opt/spark-apps && PYTHONPATH=/opt/spark-apps:\$PYTHONPATH /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --driver-memory 2g \
    --executor-memory 2g \
    --total-executor-cores 4 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/fraud_detection \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/fraud_detection.py" 2>&1 | tee /tmp/spark-fraud.log || true

echo -e "${YELLOW}Starting cart_abandonment job...${NC}"
docker run -d \
  --name spark-job-cart \
  --network kafka-ecom \
  -v /opt/spark-apps:/opt/spark-apps \
  -v /opt/spark-data:/opt/spark-data \
  --entrypoint bash \
  spark-custom:latest \
  -c "cd /opt/spark-apps && PYTHONPATH=/opt/spark-apps:\$PYTHONPATH /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --driver-memory 2g \
    --executor-memory 2g \
    --total-executor-cores 4 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/cart_abandonment \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/cart_abandonment.py" 2>&1 | tee /tmp/spark-cart.log || true

echo ""
echo -e "${GREEN}✓ Spark jobs started in Docker containers${NC}"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo "  docker logs -f spark-job-revenue"
echo "  docker logs -f spark-job-fraud"
echo "  docker logs -f spark-job-cart"
echo ""
echo -e "${YELLOW}Monitor at:${NC}"
echo "  http://localhost:8080 (Spark Master UI)"
echo "  http://localhost:4040 (Driver UI - appears once jobs connect)"
echo ""
echo -e "${YELLOW}Stop jobs:${NC}"
echo "  docker stop spark-job-revenue spark-job-fraud spark-job-cart"
echo "  docker rm spark-job-revenue spark-job-fraud spark-job-cart"
