#!/bin/bash

################################################################################
# clean-database.sh - Reset PostgreSQL database to clean state
#
# PURPOSE:
#   Truncates all analytics and transactional tables to start fresh
#   Useful for debugging and running tests without accumulated data
#
# USAGE:
#   ./clean-database.sh
#
# WHAT IT DOES:
#   - Deletes all records from analytics tables
#   - Deletes all order/payment/event records
#   - Keeps table structure intact (no DROP)
#   - Preserves product catalog
#
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🧹 Cleaning PostgreSQL Database${NC}"
echo ""

# Kill any active connections that might hold locks
echo -e "${YELLOW}Killing any blocking connections...${NC}"
docker exec postgres psql -U postgres -d kafka_ecom -c "
SELECT pg_terminate_backend(pid) 
FROM pg_stat_activity 
WHERE datname = 'kafka_ecom' AND pid <> pg_backend_pid();
" 2>/dev/null || true

sleep 1

# List of tables to truncate (data deletion)
TRUNCATE_TABLES=(
    "cart_abandonment"
    "fraud_alerts"
    "inventory_velocity"
    "operational_metrics"
    "revenue_metrics"
    "payments"
    "orders"
    "outbox_events"
    "processed_events"
    "stock_reservations"
)

echo -e "${YELLOW}Truncating tables:${NC}"
for table in "${TRUNCATE_TABLES[@]}"; do
    docker exec postgres psql -U postgres -d kafka_ecom -c "TRUNCATE TABLE $table CASCADE;" 2>/dev/null
    echo -e "${GREEN}  ✓${NC} $table"
done

echo ""
echo -e "${GREEN}✓ Database cleaned successfully${NC}"
echo ""

# Show table record counts
echo -e "${YELLOW}Current record counts:${NC}"
docker exec postgres psql -U postgres -d kafka_ecom -c "
SELECT tablename as table_name, 
       (SELECT count(*) FROM pg_stat_user_tables WHERE relname = tablename) as record_count
FROM (
    VALUES 
    ('cart_abandonment'),
    ('fraud_alerts'),
    ('inventory_velocity'),
    ('operational_metrics'),
    ('revenue_metrics'),
    ('payments'),
    ('orders'),
    ('outbox_events'),
    ('processed_events'),
    ('stock_reservations')
) as tables(tablename)
ORDER BY tablename;
" 2>/dev/null || true

echo ""
echo -e "${YELLOW}✓ Ready to run clean test:${NC}"
echo "  ./test-complete-workflow.sh"
