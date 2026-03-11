#!/bin/bash

# Load environment variables
if [ -f "$(dirname "$0")/../../.env" ]; then
    source "$(dirname "$0")/../../.env"
fi

################################################################################
# start-spark-jobs.sh - Start all 5 Spark streaming jobs
################################################################################
#
# PURPOSE:
#   Start all 5 Spark streaming jobs concurrently in the background
#
# USAGE:
#   ./scripts/spark/start-spark-jobs.sh
#
# WHAT IT DOES:
#   1. Clears all checkpoints
#   2. Submits all 5 jobs in background
#   3. Displays job submission status
#   4. Shows monitoring instructions
#

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  ${GREEN}Starting All Spark Streaming Jobs${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Clear all checkpoints
echo -e "${YELLOW}Clearing checkpoints...${NC}"
docker exec spark-worker-1 rm -rf /opt/spark-data/checkpoints 2>/dev/null
docker exec spark-master rm -rf /opt/spark-data/checkpoints 2>/dev/null
sleep 2
echo -e "${GREEN}✅ Checkpoints cleared${NC}"
echo ""

# Define jobs to start
JOBS=("revenue_streaming" "fraud_detection" "cart_abandonment" "inventory_velocity" "operational_metrics")

echo -e "${YELLOW}Starting jobs...${NC}"
echo ""

# Start each job in background
for job in "${JOBS[@]}"; do
    echo -e "${BLUE}▶${NC}  Starting ${GREEN}${job}${NC}..."
    ./scripts/spark/run-spark-job.sh "$job" > /tmp/spark_${job}.log 2>&1 &
    JOB_PID=$!
    echo "   PID: $JOB_PID (log: /tmp/spark_${job}.log)"
    sleep 3  # Small delay between submissions
done

echo ""
echo -e "${GREEN}✅ All jobs submitted!${NC}"
echo ""
echo -e "${YELLOW}Monitor jobs:${NC}"
echo "  - Spark Master UI: ${BLUE}http://localhost:9080/${NC}"
echo "  - Spark Driver UI: ${BLUE}http://localhost:4040/${NC}"
echo ""
echo -e "${YELLOW}Check job status:${NC}"
echo "  - Running applications: http://localhost:9080/ (look for 'RUNNING APPLICATIONS')"
echo ""
echo -e "${YELLOW}View logs:${NC}"
for job in "${JOBS[@]}"; do
    echo "  - tail -f /tmp/spark_${job}.log"
done
echo ""
echo -e "${YELLOW}Generate test data:${NC}"
echo "  ./scripts/simulate-users.py --mode wave --users 20 --abandonment-rate 0.5"
echo ""
echo -e "${YELLOW}Query results:${NC}"
echo "  docker-compose exec postgres psql -U postgres -d kafka_ecom"
echo ""
