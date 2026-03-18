#!/bin/bash

# Load environment variables from .env
if [ -f "$(dirname "$0")/../../.env" ]; then
    source "$(dirname "$0")/../../.env"
fi

################################################################################
# kill-spark-jobs.sh - Stop all running Spark jobs
################################################################################
#
# PURPOSE:
#   Cleanly stop all running Spark streaming jobs without restarting or cleanup
#
# USAGE:
#   ./scripts/spark/kill-spark-jobs.sh                    # Stop all jobs
#   ./scripts/spark/kill-spark-jobs.sh cart_abandonment   # Stop specific job
#   ./scripts/spark/kill-spark-jobs.sh --all              # Force kill all (same as no args)
#
# EXAMPLES:
#   # Stop all Spark jobs
#   ./scripts/spark/kill-spark-jobs.sh
#
#   # Stop only cart_abandonment
#   ./scripts/spark/kill-spark-jobs.sh cart_abandonment
#
#   # Stop only revenue_streaming
#   ./scripts/spark/kill-spark-jobs.sh revenue_streaming
#
# AVAILABLE JOBS:
#   - cart_abandonment
#   - fraud_detection
#   - inventory_velocity
#   - operational_metrics
#   - revenue_streaming
#
# NOTES:
#   - Checkpoints are preserved (jobs can resume from last batch)
#   - To restart a job after stopping: ./scripts/spark/run-spark-job.sh job_name
#   - To clear checkpoints and restart fresh: ./scripts/spark/restart-job.sh job_name
#   - Killing is non-destructive (no data loss)
#

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get job name from argument (optional)
JOB_NAME="${1}"

# Function to kill all jobs
kill_all_jobs() {
    echo -e "${YELLOW}Stopping all Spark jobs...${NC}"
    
    # Kill on all Spark containers
    docker exec spark-worker-1 pkill -9 -f "\.py" 2>/dev/null || true
    docker exec spark-worker-2 pkill -9 -f "\.py" 2>/dev/null || true
    docker exec spark-master pkill -9 -f "\.py" 2>/dev/null || true
    
    echo -e "${GREEN}✅ All Spark jobs stopped${NC}"
}

# Function to kill specific job
kill_specific_job() {
    local job=$1
    echo -e "${YELLOW}Stopping Spark job: $job...${NC}"
    
    # Kill on all Spark containers
    docker exec spark-worker-1 pkill -9 -f "${job}.py" 2>/dev/null || true
    docker exec spark-worker-2 pkill -9 -f "${job}.py" 2>/dev/null || true
    docker exec spark-master pkill -9 -f "${job}.py" 2>/dev/null || true
    
    echo -e "${GREEN}✅ Job '$job' stopped${NC}"
}

# Check if docker containers are running
if ! docker ps | grep -q spark-master; then
    echo -e "${RED}❌ Error: Spark containers not running${NC}"
    echo "Start containers with: docker-compose up -d"
    exit 1
fi

# Handle job name argument
if [ -z "$JOB_NAME" ] || [ "$JOB_NAME" = "--all" ]; then
    kill_all_jobs
else
    # Validate job name
    case "$JOB_NAME" in
        cart_abandonment|fraud_detection|inventory_velocity|operational_metrics|revenue_streaming)
            kill_specific_job "$JOB_NAME"
            ;;
        *)
            echo -e "${RED}❌ Error: Unknown job '$JOB_NAME'${NC}"
            echo ""
            echo "Available jobs:"
            echo "  - cart_abandonment"
            echo "  - fraud_detection"
            echo "  - inventory_velocity"
            echo "  - operational_metrics"
            echo "  - revenue_streaming"
            echo ""
            echo "Usage: ./scripts/spark/kill-spark-jobs.sh [job_name]"
            exit 1
            ;;
    esac
fi

# Show status
echo ""
echo -e "${YELLOW}Checking remaining Spark processes...${NC}"
RUNNING=$(docker exec spark-worker-1 pgrep -f "\.py" 2>/dev/null || echo "")
if [ -z "$RUNNING" ]; then
    echo -e "${GREEN}✅ No Spark jobs running${NC}"
else
    echo -e "${YELLOW}⚠️  Some processes still running (may be stopping):${NC}"
    docker exec spark-worker-1 ps aux | grep -E "python|spark" | grep -v grep || true
fi

exit 0
