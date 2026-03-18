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
#   ./scripts/spark/start-spark-jobs.sh              # Just start jobs
#   ./scripts/spark/start-spark-jobs.sh --with-monitor  # Start jobs + auto-monitoring
#
# OPTIONS:
#   --with-monitor    Start monitor-spark-jobs.sh in background to auto-restart jobs
#   --no-clear        Skip checkpoint clearing (keep job state)
#
# WHAT IT DOES:
#   1. Clears all checkpoints (unless --no-clear)
#   2. Submits all 5 jobs in background
#   3. Displays job submission status
#   4. Optionally starts monitoring daemon (if --with-monitor)
#   5. Shows monitoring instructions
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

# Parse command line arguments
WITH_MONITOR=false
CLEAR_CHECKPOINTS=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --with-monitor)
            WITH_MONITOR=true
            shift
            ;;
        --no-clear)
            CLEAR_CHECKPOINTS=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./scripts/spark/start-spark-jobs.sh [--with-monitor] [--no-clear]"
            exit 1
            ;;
    esac
done

# Clear checkpoints (unless disabled)
if [ "$CLEAR_CHECKPOINTS" = true ]; then
    echo -e "${YELLOW}Clearing checkpoints...${NC}"
    docker exec spark-worker-1 rm -rf /opt/spark-data/checkpoints 2>/dev/null
    docker exec spark-master rm -rf /opt/spark-data/checkpoints 2>/dev/null
    sleep 2
    echo -e "${GREEN}✅ Checkpoints cleared${NC}"
else
    echo -e "${YELLOW}Skipping checkpoint clearing (--no-clear)${NC}"
fi
echo ""

# Define jobs to start
JOBS=("fraud_detection" "revenue_streaming" "cart_abandonment" "inventory_velocity" "operational_metrics")

echo -e "${YELLOW}Starting ${#JOBS[@]} jobs...${NC}"
echo ""

SUCCESSFUL=0
FAILED=0

# Start each job in background
for job in "${JOBS[@]}"; do
    echo -e "${BLUE}▶${NC}  Starting ${GREEN}${job}${NC}..."
    ./scripts/spark/run-spark-job.sh "$job" > /tmp/spark_${job}.log 2>&1 &
    JOB_PID=$!
    echo "   PID: $JOB_PID (log: /tmp/spark_${job}.log)"
    
    # Wait a bit and check if submission was successful
    sleep 2
    if grep -q "✓ Job submitted successfully" /tmp/spark_${job}.log 2>/dev/null; then
        ((SUCCESSFUL++))
    else
        ((FAILED++))
    fi
    
    sleep 2  # Small delay between submissions
done

echo ""
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All ${SUCCESSFUL} jobs submitted successfully!${NC}"
else
    echo -e "${YELLOW}⚠️  ${SUCCESSFUL} submitted, ${FAILED} may have issues${NC}"
fi
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

# Optionally start monitoring
if [ "$WITH_MONITOR" = true ]; then
    echo -e "${YELLOW}Starting monitoring daemon...${NC}"
    ./scripts/spark/monitor-spark-jobs.sh > /tmp/spark-monitor.log 2>&1 &
    MONITOR_PID=$!
    echo -e "${GREEN}✅ Monitoring started (PID: $MONITOR_PID)${NC}"
    echo "   Watch monitoring: tail -f /tmp/spark-monitor.log"
    echo ""
else
    echo -e "${BLUE}ℹ️  Tip: To auto-restart jobs if they fail, use:${NC}"
    echo "   ./scripts/spark/start-spark-jobs.sh --with-monitor"
    echo ""
fi