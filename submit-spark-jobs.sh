#!/bin/bash

################################################################################
# submit-spark-jobs.sh - Properly submit Spark jobs to the cluster
#
# This script submits Spark jobs directly to the cluster in a way that allows
# the Driver UI to be accessible via localhost:4040
#
# USAGE:
#   ./submit-spark-jobs.sh
#
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Submitting Spark Jobs to Cluster${NC}"
echo ""

# Check if Spark cluster is running
if ! docker ps | grep -q spark-master; then
    echo -e "${RED}Error: Spark cluster not running${NC}"
    exit 1
fi

# Kill any existing jobs from previous runs
echo -e "${YELLOW}Stopping any existing Spark jobs...${NC}"
docker exec spark-worker-1 pkill -9 -f "spark-submit.*jobs/" 2>/dev/null || true
sleep 1

echo -e "${GREEN}✓ Ready to submit jobs${NC}"
echo ""

# Submit fraud_detection job
echo -e "${YELLOW}Submitting fraud_detection job...${NC}"
docker exec -d spark-master bash -c "cd /opt/spark-apps && \
    PYTHONPATH=/opt/spark-apps:\$PYTHONPATH \
    /opt/spark/bin/spark-submit \
    --master spark://localhost:7077 \
    --deploy-mode cluster \
    --driver-cores 2 \
    --driver-memory 2g \
    --executor-cores 2 \
    --executor-memory 2g \
    --num-executors 2 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/fraud_detection \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/fraud_detection.py > /tmp/fraud_submit.log 2>&1"

sleep 2

# Submit revenue_streaming job
echo -e "${YELLOW}Submitting revenue_streaming job...${NC}"
docker exec -d spark-master bash -c "cd /opt/spark-apps && \
    PYTHONPATH=/opt/spark-apps:\$PYTHONPATH \
    /opt/spark/bin/spark-submit \
    --master spark://localhost:7077 \
    --deploy-mode cluster \
    --driver-cores 2 \
    --driver-memory 2g \
    --executor-cores 2 \
    --executor-memory 2g \
    --num-executors 2 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/revenue_streaming \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/revenue_streaming.py > /tmp/revenue_submit.log 2>&1"

sleep 2

# Submit cart_abandonment job
echo -e "${YELLOW}Submitting cart_abandonment job...${NC}"
docker exec -d spark-master bash -c "cd /opt/spark-apps && \
    PYTHONPATH=/opt/spark-apps:\$PYTHONPATH \
    /opt/spark/bin/spark-submit \
    --master spark://localhost:7077 \
    --deploy-mode cluster \
    --driver-cores 2 \
    --driver-memory 2g \
    --executor-cores 2 \
    --executor-memory 2g \
    --num-executors 2 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/cart_abandonment \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/cart_abandonment.py > /tmp/cart_submit.log 2>&1"

echo ""
echo -e "${GREEN}✓ Jobs submitted to cluster${NC}"
echo ""
echo -e "${CYAN}Waiting for jobs to initialize...${NC}"
for i in {20..1}; do
    echo -ne "\rSeconds remaining: $i"
    sleep 1
done
echo -e "\n"

echo -e "${YELLOW}Monitor jobs at:${NC}"
echo "  • Spark Master UI: http://localhost:8080"
echo "  • Driver UI: http://localhost:4040 (once job starts)"
echo ""
echo -e "${YELLOW}View submission logs:${NC}"
echo "  • tail /tmp/fraud_submit.log"
echo "  • tail /tmp/revenue_submit.log"
echo "  • tail /tmp/cart_submit.log"
echo ""
echo -e "${CYAN}Check if jobs are running:${NC}"
echo "  curl http://localhost:8080/api/v1/applications"
