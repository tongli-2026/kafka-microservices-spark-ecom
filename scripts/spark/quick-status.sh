#!/bin/bash

# Quick Status Check - Shows current Spark job status
# Usage: ./scripts/spark/quick-status.sh
#
# ABOUT WARNINGS IN SPARK LOGS:
# ═══════════════════════════════════════════════════════════════════════════════
#
# ⚠️  HDFSBackedStateStoreProvider warnings:
#     "The state for version X doesn't exist in loadedMaps..."
#     → NORMAL on first batch - Spark initializing checkpoints
#     → NOT AN ERROR - job is working correctly
#
# ⚠️  ProcessingTimeExecutor warnings:
#     "Current batch is falling behind. Trigger interval X but spent Y milliseconds"
#     → NORMAL during heavy load - Spark working hard on data
#     → System will catch up as load decreases
#     → Not a failure - expected behavior under stress
#
# ✅ Job submission exit code 137:
#     → NORMAL for backgrounded jobs (nohup)
#     → Job continues running despite exit code
#     → Verify with: docker exec spark-worker-1 pgrep -f "job_name.py"
#
# 🔥 What SUCCESS looks like:
#     "Successfully wrote X records with upsert (batch_id=Y)"
#     "Successfully wrote Y operational metrics (batch_id=Z)"
#     → Job is processing and writing data
#     → Events are flowing through Kafka → Spark → PostgreSQL
#
# ═══════════════════════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║          🚀 Spark Jobs System - Quick Status Check              ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}1. STREAMING JOBS:${NC}"
echo ""

RUNNING=0
TOTAL=0

for job in fraud_detection revenue_streaming cart_abandonment operational_metrics; do
    ((TOTAL++))
    if docker exec spark-worker-1 pgrep -f "${job}\.py" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $job${NC} - RUNNING"
        ((RUNNING++))
    else
        echo -e "${YELLOW}⏸️  $job${NC} - STOPPED"
    fi
done

echo ""
echo -e "${BLUE}2. BATCH JOBS:${NC}"
echo ""
echo -e "${YELLOW}⏰ inventory_velocity${NC} - Runs hourly (via cron/scheduler)"

echo ""
echo -e "${BLUE}3. INFRASTRUCTURE:${NC}"
echo ""

# Check containers
docker ps | grep -E 'kafka|postgres|spark' | wc -l > /tmp/container_count.txt
CONTAINER_COUNT=$(cat /tmp/container_count.txt)

if [ "$CONTAINER_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ Docker containers${NC} running: $CONTAINER_COUNT"
else
    echo -e "${RED}❌ No containers${NC} running"
fi

# Check Kafka
if docker ps | grep -q kafka; then
    echo -e "${GREEN}✅ Kafka${NC} - Running"
else
    echo -e "${RED}❌ Kafka${NC} - Not running"
fi

# Check PostgreSQL
if docker ps | grep -q postgres; then
    echo -e "${GREEN}✅ PostgreSQL${NC} - Running"
else
    echo -e "${RED}❌ PostgreSQL${NC} - Not running"
fi

echo ""
echo -e "${BLUE}4. SUMMARY:${NC}"
echo ""
echo -e "Streaming Jobs: ${GREEN}${RUNNING}/${TOTAL}${NC} running"

if [ "$RUNNING" -eq "$TOTAL" ]; then
    echo -e "${GREEN}✅ SYSTEM OPERATIONAL${NC}"
    echo ""
    echo "📊 TEST DATA GENERATION (Load Testing):"
    echo "  ⭐ RECOMMENDED - Medium load (10 users/wave):"
    echo "     ./scripts/simulate-users.py --mode continuous --duration 300 --interval 15 --users 10"
    echo ""
    echo "  Light load (5 users/wave):"
    echo "     ./scripts/simulate-users.py --mode continuous --duration 300 --interval 30 --users 5"
    echo ""
    echo "  Heavy load (20 users/wave):"
    echo "     ./scripts/simulate-users.py --mode continuous --duration 300 --interval 15 --users 20"
    echo ""
    echo "🔍 MONITORING:"
    echo "     • Spark Master UI: http://localhost:9080"
    echo "     • Spark Driver UI: http://localhost:4040"
    echo "     • Kafka UI: http://localhost:8080"
    echo ""
    echo "📈 CHECK RESULTS:"
    echo "     docker-compose exec postgres psql -U postgres -d kafka_ecom"
    echo "     SELECT COUNT(*) FROM orders;"
else
    echo -e "${YELLOW}⚠️  ${RUNNING}/${TOTAL} streaming jobs running${NC}"
    echo ""
    echo "To start all jobs:"
    echo "  ./scripts/spark/start-spark-jobs.sh"
fi

echo ""
echo -e "${BLUE}MONITORING URLS:${NC}"
echo "  • Spark Master: ${BLUE}http://localhost:9080${NC}"
echo "  • Spark Driver: ${BLUE}http://localhost:4040${NC}"
echo "  • Kafka UI (if available): ${BLUE}http://localhost:8080${NC}"
echo "  • pgAdmin (if available): ${BLUE}http://localhost:5050${NC}"
echo ""
