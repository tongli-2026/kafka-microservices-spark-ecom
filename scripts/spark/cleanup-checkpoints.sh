#!/bin/bash

################################################################################
# cleanup-checkpoints.sh - Clean up all Spark checkpoint files
################################################################################
#
# PURPOSE:
#   Remove all checkpoint directories from Spark containers to allow
#   jobs to restart fresh. Useful when checkpoint files become corrupted
#   or when you want to reprocess all events.
#
# USAGE:
#   ./scripts/spark/cleanup-checkpoints.sh          # Clean all checkpoints
#   ./scripts/spark/cleanup-checkpoints.sh cart_abandonment  # Clean specific job
#
# WHY NEEDED:
#   - Checkpoint files can become corrupted if Spark crashes
#   - Multiple jobs can't share the same checkpoint directory
#   - Reprocessing all events requires fresh checkpoints
#

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

JOB_NAME=$1

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
if [ -z "$JOB_NAME" ]; then
    echo -e "${BLUE}║${NC}  ${YELLOW}Cleaning All Spark Checkpoints${NC}"
else
    echo -e "${BLUE}║${NC}  ${YELLOW}Cleaning Checkpoints for: ${JOB_NAME}${NC}"
fi
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Kill all running Spark jobs first
echo -e "${YELLOW}Killing all running Spark jobs...${NC}"
docker exec spark-worker-1 pkill -9 -f "\.py" 2>/dev/null || true
docker exec spark-worker-2 pkill -9 -f "\.py" 2>/dev/null || true
docker exec spark-master pkill -9 -f "\.py" 2>/dev/null || true
sleep 2
echo -e "${GREEN}✅ All Spark jobs terminated${NC}"
echo ""

# Clean up checkpoint directories
echo -e "${YELLOW}Removing checkpoint files...${NC}"

if [ -z "$JOB_NAME" ]; then
    # Clean ALL checkpoints
    echo "  Cleaning /tmp/checkpoints..."
    docker exec spark-worker-1 rm -rf /tmp/checkpoints 2>/dev/null || true
    docker exec spark-worker-2 rm -rf /tmp/checkpoints 2>/dev/null || true
    docker exec spark-master rm -rf /tmp/checkpoints 2>/dev/null || true
    
    echo "  Cleaning /opt/spark-data/checkpoints..."
    docker exec spark-worker-1 rm -rf /opt/spark-data/checkpoints 2>/dev/null || true
    docker exec spark-worker-2 rm -rf /opt/spark-data/checkpoints 2>/dev/null || true
    docker exec spark-master rm -rf /opt/spark-data/checkpoints 2>/dev/null || true
    
    echo -e "${GREEN}✅ All checkpoints removed${NC}"
else
    # Clean specific job checkpoints
    echo "  Cleaning checkpoints for ${JOB_NAME}..."
    docker exec spark-worker-1 rm -rf /tmp/checkpoints/${JOB_NAME} 2>/dev/null || true
    docker exec spark-worker-2 rm -rf /tmp/checkpoints/${JOB_NAME} 2>/dev/null || true
    docker exec spark-master rm -rf /tmp/checkpoints/${JOB_NAME} 2>/dev/null || true
    
    docker exec spark-worker-1 rm -rf /opt/spark-data/checkpoints/${JOB_NAME} 2>/dev/null || true
    docker exec spark-worker-2 rm -rf /opt/spark-data/checkpoints/${JOB_NAME} 2>/dev/null || true
    docker exec spark-master rm -rf /opt/spark-data/checkpoints/${JOB_NAME} 2>/dev/null || true
    
    echo -e "${GREEN}✅ Checkpoints for ${JOB_NAME} removed${NC}"
fi

sleep 1
echo ""
echo -e "${GREEN}✅ Cleanup complete${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
if [ -z "$JOB_NAME" ]; then
    echo "  Start jobs with: ./scripts/spark/start-spark-jobs.sh"
else
    echo "  Restart job with: ./scripts/spark/run-spark-job.sh ${JOB_NAME}"
fi
