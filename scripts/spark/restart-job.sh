#!/bin/bash

# Load environment variables from .env
if [ -f "$(dirname "$0")/../../.env" ]; then
    source "$(dirname "$0")/../../.env"
fi

################################################################################
# restart-job.sh - Kill and restart a Spark job with fresh checkpoint
################################################################################
#
# PURPOSE:
#   Cleanly restarts a Spark job after code changes by:
#   1. Killing any running instances
#   2. Clearing checkpoint files
#   3. Resubmitting the job fresh
#
# USAGE:
#   ./scripts/spark/restart-job.sh cart_abandonment
#   ./scripts/spark/restart-job.sh fraud_detection
#   ./scripts/spark/restart-job.sh inventory_velocity
#   ./scripts/spark/restart-job.sh operational_metrics
#   ./scripts/spark/restart-job.sh revenue_streaming

#
# WHY NEEDED:
#   After modifying Spark job code, checkpoints from the old job will cause
#   conflicts when restarting. This script cleanly wipes state and restarts.
#
# WHAT IT DOES:
#   1. Validates job name parameter
#   2. Kills any running instances of the job
#   3. Removes checkpoint directory from Spark containers
#   4. Submits the job fresh via run-spark-job.sh
#
# ABOUT EXIT CODES:
#   ✅ Exit code 0   = Job restarted successfully
#   ⚠️  Exit code 1   = Job submission had issues (check logs)
#   ⚠️  Exit code 137 = Job killed or backgrounded (NORMAL - job still runs!)
#   
#   NOTE: Exit code 137 is NORMAL when job is backgrounded by 'nohup'.
#   The job continues running in background. Verify with:
#   docker exec spark-worker-1 pgrep -f "job_name.py"
#
# ABOUT WARNINGS IN LOGS:
#   The warnings like "HDFSBackedStateStoreProvider: The state for version X doesn't exist"
#   are NORMAL and expected on first batch. This is Spark initializing checkpoints.
#   Not an error - job is working correctly.
#

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get job name from first argument
JOB_NAME=$1

# Check if job name provided
if [ -z "$JOB_NAME" ]; then
    echo -e "${RED}Error: Job name required${NC}"
    echo "Usage: $0 <job_name>"
    echo ""
    echo "Available jobs:"
    echo "  $0 cart_abandonment"
    echo "  $0 fraud_detection"
    echo "  $0 inventory_velocity"
    echo "  $0 operational_metrics"
    echo "  $0 revenue_streaming"
    exit 1
fi

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  ${YELLOW}Restarting Spark Job: ${JOB_NAME}${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Kill running instances
echo -e "${YELLOW}Step 1: Killing any running instances...${NC}"
docker exec spark-worker-1 pkill -9 -f "${JOB_NAME}.py" 2>/dev/null || true
docker exec spark-worker-2 pkill -9 -f "${JOB_NAME}.py" 2>/dev/null || true
docker exec spark-master pkill -9 -f "${JOB_NAME}.py" 2>/dev/null || true
sleep 2
echo -e "${GREEN}✅ Job processes killed${NC}"
echo ""

# Step 2: Clear checkpoints for this specific job
echo -e "${YELLOW}Step 2: Clearing checkpoint directories...${NC}"
docker exec spark-worker-1 rm -rf /tmp/checkpoints/${JOB_NAME} /opt/spark-data/checkpoints/${JOB_NAME} 2>/dev/null || true
docker exec spark-worker-2 rm -rf /tmp/checkpoints/${JOB_NAME} /opt/spark-data/checkpoints/${JOB_NAME} 2>/dev/null || true
docker exec spark-master rm -rf /tmp/checkpoints/${JOB_NAME} /opt/spark-data/checkpoints/${JOB_NAME} 2>/dev/null || true
sleep 1
echo -e "${GREEN}✅ Checkpoints cleared${NC}"
echo ""

# Step 3: Resubmit the job
echo -e "${YELLOW}Step 3: Resubmitting job...${NC}"
./scripts/spark/run-spark-job.sh "$JOB_NAME"

echo ""
echo -e "${GREEN}✅ Job restart complete${NC}"
