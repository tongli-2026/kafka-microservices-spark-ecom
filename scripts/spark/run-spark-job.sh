#!/bin/bash

################################################################################
# run-spark-job.sh - Spark Job Submission Helper Script
################################################################################
#
# PURPOSE:
#   Simplifies submitting PySpark streaming jobs to the Spark cluster.
#   Handles all spark-submit parameters and package dependencies.
#
# USAGE:
#   ./run-spark-job.sh <job_name>
#
# EXAMPLES:
#   ./run-spark-job.sh revenue_streaming
#   ./run-spark-job.sh fraud_detection
#   ./run-spark-job.sh cart_abandonment
#   ./run-spark-job.sh inventory_velocity
#   ./run-spark-job.sh operational_metrics
#
# WHAT IT DOES:
#   1. Validates job name parameter
#   2. Checks if job file exists in analytics/jobs/
#   3. Verifies Spark cluster is running
#   4. Submits job to Spark cluster via spark-worker-1
#   5. Includes required packages (Kafka, PostgreSQL)
#   6. Displays submission status and monitoring links
#
# REQUIREMENTS:
#   - Docker containers must be running
#   - Spark cluster must be healthy
#   - Job file must exist in analytics/jobs/ directory
#
################################################################################

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
    echo ""
    echo "Usage: $0 <job_name>"
    echo ""
    echo "Available jobs:"
    echo "  - revenue_streaming"
    echo "  - fraud_detection"
    echo "  - cart_abandonment"
    echo "  - inventory_velocity"
    echo "  - operational_metrics"
    echo ""
    echo "Example:"
    echo "  $0 revenue_streaming"
    exit 1
fi

# Define job file path (inside container)
JOB_FILE="/opt/spark-apps/jobs/${JOB_NAME}.py"

# Check if job file exists (in local directory)
if [ ! -f "analytics/jobs/${JOB_NAME}.py" ]; then
    echo -e "${RED}Error: Job file not found: analytics/jobs/${JOB_NAME}.py${NC}"
    echo ""
    echo "Available jobs in analytics/jobs/:"
    ls -1 analytics/jobs/*.py 2>/dev/null | xargs -n1 basename | sed 's/.py$//' | sed 's/^/  - /'
    exit 1
fi

# Check if Docker container is running
if ! docker ps | grep -q spark-worker-1; then
    echo -e "${RED}Error: spark-worker-1 container is not running${NC}"
    echo "Start containers with: docker-compose up -d"
    exit 1
fi

# Check if Spark master is running
if ! docker ps | grep -q spark-master; then
    echo -e "${RED}Error: spark-master container is not running${NC}"
    echo "Start containers with: docker-compose up -d"
    exit 1
fi

# Display submission info
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  ${GREEN}Submitting Spark Job: ${JOB_NAME}${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Job File:${NC} ${JOB_FILE}"
echo -e "${YELLOW}Spark Master:${NC} spark://spark-master:7077"
echo -e "${YELLOW}Deploy Mode:${NC} client"
echo -e "${YELLOW}Packages:${NC} Kafka Connector, PostgreSQL JDBC"
echo -e "${YELLOW}Driver Memory:${NC} 2g"
echo -e "${YELLOW}Executor Memory:${NC} 2g"
echo -e "${YELLOW}Total Executor Cores:${NC} 4"
echo ""
echo -e "${BLUE}Starting job submission...${NC}"
echo ""

# Submit Spark job with correct PYTHONPATH and resource allocation
docker exec spark-worker-1 bash -c "
  cd /opt/spark-apps && \
  export PYTHONPATH=/opt/spark-apps:\$PYTHONPATH && \
  /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --deploy-mode client \
    --driver-memory 2g \
    --executor-memory 2g \
    --total-executor-cores 4 \
    --conf spark.driver.bindAddress=0.0.0.0 \
    --conf spark.driver.host=0.0.0.0 \
    --conf spark.ui.hostname=0.0.0.0 \
    --conf spark.sql.streaming.checkpointLocation=/opt/spark-data/checkpoints/${JOB_NAME} \
    --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1 \
    --py-files /opt/spark-apps/spark_session.py \
    ${JOB_FILE}
"

# Capture exit code
EXIT_CODE=$?

# Display result
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Job submitted successfully!${NC}"
    echo ""
    echo -e "${YELLOW}Monitor job:${NC}"
    echo "  - Spark Driver UI: http://localhost:4040"
    echo "  - Spark Master UI: http://localhost:9080"
    echo "  - Streaming query details: Check 'Structured Streaming' tab in Driver UI"
else
    echo -e "${RED}✗ Job submission failed (exit code: $EXIT_CODE)${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo "  1. Check Spark cluster: docker logs spark-master"
    echo "  2. Check worker logs: docker logs spark-worker-1"
    echo "  3. Verify job syntax: Check Python file for errors"
    echo "  4. Check Spark Master UI: http://localhost:9080"
fi

exit $EXIT_CODE
