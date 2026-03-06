#!/bin/bash

################################################################################
# start-spark-jobs-with-ui.sh - Start Spark jobs with accessible Driver UI
#
# This script properly configures Spark to make port 4040 accessible from
# your host machine by ensuring the driver listens on 0.0.0.0:4040
#
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}Starting Spark Jobs with Accessible Driver UI${NC}"
echo ""

# Stop any running jobs first
echo -e "${YELLOW}Cleaning up existing jobs...${NC}"
docker exec spark-worker-1 pkill -9 -f "python.*jobs" 2>/dev/null || true
sleep 2

echo -e "${GREEN}✓ Starting jobs${NC}"
echo ""

# Start first job - fraud_detection
echo -e "${YELLOW}Starting fraud_detection job...${NC}"
docker exec -d spark-worker-1 bash -c "
  cd /opt/spark-apps && \
  export SPARK_DRIVER_BIND_ADDRESS=0.0.0.0 && \
  export SPARK_WEBUI_HOST=0.0.0.0 && \
  PYTHONPATH=/opt/spark-apps:\$PYTHONPATH \
  /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --driver-memory 2g \
    --executor-memory 2g \
    --total-executor-cores 4 \
    --conf spark.driver.bindAddress=0.0.0.0 \
    --conf spark.driver.host=0.0.0.0 \
    --conf spark.ui.port=4040 \
    --conf spark.ui.hostname=0.0.0.0 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/fraud_detection \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/fraud_detection.py
" > /tmp/spark-fraud.log 2>&1 &

FRAUD_PID=$!
echo -e "${GREEN}✓ Fraud detection job started (background PID: $FRAUD_PID)${NC}"

sleep 5

# Start second job - cart_abandonment  
echo -e "${YELLOW}Starting cart_abandonment job...${NC}"
docker exec -d spark-worker-1 bash -c "
  cd /opt/spark-apps && \
  export SPARK_DRIVER_BIND_ADDRESS=0.0.0.0 && \
  export SPARK_WEBUI_HOST=0.0.0.0 && \
  PYTHONPATH=/opt/spark-apps:\$PYTHONPATH \
  /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --driver-memory 2g \
    --executor-memory 2g \
    --total-executor-cores 4 \
    --conf spark.driver.bindAddress=0.0.0.0 \
    --conf spark.driver.host=0.0.0.0 \
    --conf spark.ui.port=4041 \
    --conf spark.ui.hostname=0.0.0.0 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/cart_abandonment \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/cart_abandonment.py
" > /tmp/spark-cart.log 2>&1 &

CART_PID=$!
echo -e "${GREEN}✓ Cart abandonment job started (background PID: $CART_PID)${NC}"

sleep 5

# Start third job - revenue_streaming
echo -e "${YELLOW}Starting revenue_streaming job...${NC}"
docker exec -d spark-worker-1 bash -c "
  cd /opt/spark-apps && \
  export SPARK_DRIVER_BIND_ADDRESS=0.0.0.0 && \
  export SPARK_WEBUI_HOST=0.0.0.0 && \
  PYTHONPATH=/opt/spark-apps:\$PYTHONPATH \
  /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --driver-memory 2g \
    --executor-memory 2g \
    --total-executor-cores 4 \
    --conf spark.driver.bindAddress=0.0.0.0 \
    --conf spark.driver.host=0.0.0.0 \
    --conf spark.ui.port=4042 \
    --conf spark.ui.hostname=0.0.0.0 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/revenue_streaming \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    jobs/revenue_streaming.py
" > /tmp/spark-revenue.log 2>&1 &

REVENUE_PID=$!
echo -e "${GREEN}✓ Revenue streaming job started (background PID: $REVENUE_PID)${NC}"

echo ""
echo -e "${YELLOW}Waiting for drivers to initialize (20 seconds)...${NC}"
for i in {20..1}; do
    echo -ne "\rSeconds remaining: $i"
    sleep 1
done
echo -e "\n"

echo -e "${GREEN}✓ Jobs initialized${NC}"
echo ""
echo -e "${YELLOW}Access Driver UIs:${NC}"
echo "  • Primary (fraud_detection): http://localhost:4040"
echo "  • Secondary (cart_abandonment): http://localhost:4041"
echo "  • Tertiary (revenue_streaming): http://localhost:4042"
echo ""
echo -e "${YELLOW}Monitor all jobs:${NC}"
echo "  • Spark Master UI: http://localhost:8080"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo "  • tail -f /tmp/spark-fraud.log"
echo "  • tail -f /tmp/spark-cart.log"
echo "  • tail -f /tmp/spark-revenue.log"
echo ""
echo -e "${CYAN}Jobs running in background. Use 'pkill -f spark-submit' to stop all.${NC}"
