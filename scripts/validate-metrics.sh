#!/bin/bash

# ============================================================================
# validate-metrics.sh - Monitoring Stack Validation Script
# ============================================================================
# This script validates the entire Prometheus & Grafana monitoring stack.
# It checks:
# - Service connectivity
# - Prometheus target health
# - Active metric collection
# - Dashboard configuration
# - Grafana datasource status
#
# Usage: ./scripts/validate-metrics.sh
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Monitoring Stack Validation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check endpoint
check_endpoint() {
    local name=$1
    local url=$2
    local expected_status=${3:-200}
    
    echo -n "Checking $name ... "
    
    status=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    
    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}✓ OK${NC} (HTTP $status)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC} (HTTP $status, expected $expected_status)"
        ((FAILED++))
        return 1
    fi
}

# Function to check JSON response
check_json_response() {
    local name=$1
    local url=$2
    local json_field=$3
    
    echo -n "Checking $name ... "
    
    response=$(curl -s "$url" 2>/dev/null || echo "{}")
    
    if echo "$response" | jq . &>/dev/null; then
        if echo "$response" | jq -e "$json_field" &>/dev/null; then
            echo -e "${GREEN}✓ OK${NC}"
            ((PASSED++))
            return 0
        else
            echo -e "${RED}✗ FAILED${NC} (Missing field: $json_field)"
            ((FAILED++))
            return 1
        fi
    else
        echo -e "${RED}✗ FAILED${NC} (Invalid JSON response)"
        ((FAILED++))
        return 1
    fi
}

# ============================================================================
# 1. Check Core Services
# ============================================================================
echo -e "${YELLOW}1. Core Services Health${NC}"
echo "---"

check_endpoint "Prometheus" "http://localhost:9090/-/healthy"
check_endpoint "Grafana" "http://localhost:3000/api/health"
echo ""

# ============================================================================
# 2. Check Service Metrics Endpoints
# ============================================================================
echo -e "${YELLOW}2. Service Metrics Endpoints${NC}"
echo "---"

check_endpoint "Payment Service Metrics" "http://localhost:8003/metrics"
check_endpoint "Order Service Metrics" "http://localhost:8002/metrics"
check_endpoint "Inventory Service Metrics" "http://localhost:8004/metrics"
check_endpoint "Notification Service Metrics" "http://localhost:8005/metrics"
check_endpoint "Cart Service Metrics" "http://localhost:8001/metrics"
echo ""

# ============================================================================
# 3. Check Service Health Endpoints
# ============================================================================
echo -e "${YELLOW}3. Service Health Endpoints${NC}"
echo "---"

check_endpoint "Payment Service Health" "http://localhost:8003/health"
check_endpoint "Order Service Health" "http://localhost:8002/health"
check_endpoint "Inventory Service Health" "http://localhost:8004/health"
check_endpoint "Notification Service Health" "http://localhost:8005/health"
check_endpoint "Cart Service Health" "http://localhost:8001/health"
echo ""

# ============================================================================
# 4. Check Prometheus Targets
# ============================================================================
echo -e "${YELLOW}4. Prometheus Targets${NC}"
echo "---"

echo "Fetching active Prometheus targets..."
targets=$(curl -s "http://localhost:9090/api/v1/query?query=up" 2>/dev/null || echo "{}")

if echo "$targets" | jq . &>/dev/null; then
    active_targets=$(echo "$targets" | jq '.data.result | length')
    echo -n "Active targets: "
    
    if [ "$active_targets" -ge 5 ]; then
        echo -e "${GREEN}✓ $active_targets targets UP${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED - Only $active_targets targets (expected >= 5)${NC}"
        ((FAILED++))
    fi
    
    # Show target details
    echo ""
    echo "Target Details:"
    echo "$targets" | jq -r '.data.result[] | "\(.metric.job): \(.value[1])"' | while read line; do
        if [[ $line == *"1"* ]]; then
            echo -e "  ${GREEN}✓${NC} $line"
        else
            echo -e "  ${RED}✗${NC} $line"
        fi
    done
else
    echo -e "${RED}✗ FAILED${NC} (Could not fetch Prometheus targets)"
    ((FAILED++))
fi
echo ""

# ============================================================================
# 5. Check Prometheus Datasource
# ============================================================================
echo -e "${YELLOW}5. Grafana Datasources${NC}"
echo "---"

echo -n "Checking Prometheus Datasource ... "

# Check if datasource exists and is configured properly
datasource=$(curl -s -u admin:admin "http://localhost:3000/api/datasources" 2>/dev/null | jq '.[0]')

if echo "$datasource" | jq -e '.name == "Prometheus"' &>/dev/null; then
    echo -e "${GREEN}✓ OK${NC} (Prometheus datasource configured)"
    ((PASSED++))
else
    echo -e "${RED}✗ FAILED${NC} (Prometheus datasource not found)"
    ((FAILED++))
fi
echo ""

# ============================================================================
# 6. Check Metric Collection
# ============================================================================
echo -e "${YELLOW}6. Metric Collection Status${NC}"
echo "---"

echo "Checking key metrics collection..."

# Check HTTP request metrics
echo -n "HTTP requests total: "
http_requests=$(curl -s "http://localhost:9090/api/v1/query?query=http_requests_total" 2>/dev/null | jq '.data.result | length')
if [ "$http_requests" -gt 0 ]; then
    echo -e "${GREEN}✓ $http_requests series${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ No metrics collected${NC}"
    ((FAILED++))
fi

# Check HTTP duration metrics
echo -n "HTTP duration histogram: "
http_duration=$(curl -s "http://localhost:9090/api/v1/query?query=http_request_duration_seconds_bucket" 2>/dev/null | jq '.data.result | length')
if [ "$http_duration" -gt 0 ]; then
    echo -e "${GREEN}✓ $http_duration series${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ No metrics collected${NC}"
    ((FAILED++))
fi

# Check service errors
echo -n "Service errors total: "
service_errors=$(curl -s "http://localhost:9090/api/v1/query?query=service_errors_total" 2>/dev/null | jq '.data.result | length')
if [ "$service_errors" -ge 0 ]; then
    echo -e "${GREEN}✓ $service_errors series${NC}"
    ((PASSED++))
else
    echo -e "${RED}✗ Failed to query${NC}"
    ((FAILED++))
fi
echo ""

# ============================================================================
# 7. Check Dashboard Configuration
# ============================================================================
echo -e "${YELLOW}7. Dashboard Configuration${NC}"
echo "---"

if [ -f "monitoring/dashboards/microservices-dashboard.json" ]; then
    echo -n "Microservices Dashboard File: "
    
    if jq . "monitoring/dashboards/microservices-dashboard.json" &>/dev/null; then
        panels=$(jq '.panels | length' "monitoring/dashboards/microservices-dashboard.json")
        echo -e "${GREEN}✓ Found ($panels panels)${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Invalid JSON${NC}"
        ((FAILED++))
    fi
else
    echo -e "${RED}✗ Dashboard file not found${NC}"
    ((FAILED++))
fi

if [ -f "monitoring/dashboards/saga-dashboard.json" ]; then
    echo -n "Saga Orchestration Dashboard File: "
    
    if jq . "monitoring/dashboards/saga-dashboard.json" &>/dev/null; then
        panels=$(jq '.panels | length' "monitoring/dashboards/saga-dashboard.json")
        echo -e "${GREEN}✓ Found ($panels panels)${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Invalid JSON${NC}"
        ((FAILED++))
    fi
else
    echo -e "${YELLOW}⊘ Optional${NC} (Saga dashboard not created yet)"
fi
echo ""

# ============================================================================
# 8. Check Configuration Files
# ============================================================================
echo -e "${YELLOW}8. Configuration Files${NC}"
echo "---"

if [ -f "monitoring/prometheus.yml" ]; then
    echo -n "Prometheus Configuration: "
    
    if grep -q "scrape_interval: 15s" "monitoring/prometheus.yml"; then
        echo -e "${GREEN}✓ Found (15s interval)${NC}"
        ((PASSED++))
    else
        echo -e "${YELLOW}⊘ Found but check interval${NC}"
    fi
else
    echo -e "${RED}✗ prometheus.yml not found${NC}"
    ((FAILED++))
fi

if [ -f "monitoring/Dockerfile.prometheus" ]; then
    echo -n "Prometheus Dockerfile: "
    
    if grep -q "prom/prometheus:v2.45.0" "monitoring/Dockerfile.prometheus"; then
        echo -e "${GREEN}✓ Found (v2.45.0)${NC}"
        ((PASSED++))
    else
        echo -e "${YELLOW}⊘ Found (check version)${NC}"
    fi
else
    echo -e "${RED}✗ Dockerfile.prometheus not found${NC}"
    ((FAILED++))
fi

if [ -f "monitoring/Dockerfile.grafana" ]; then
    echo -n "Grafana Dockerfile: "
    
    if grep -q "grafana/grafana:10.0.0" "monitoring/Dockerfile.grafana"; then
        echo -e "${GREEN}✓ Found (v10.0.0)${NC}"
        ((PASSED++))
    else
        echo -e "${YELLOW}⊘ Found (check version)${NC}"
    fi
else
    echo -e "${RED}✗ Dockerfile.grafana not found${NC}"
    ((FAILED++))
fi
echo ""

# ============================================================================
# 9. Check Shared Metrics Module
# ============================================================================
echo -e "${YELLOW}9. Shared Metrics Module${NC}"
echo "---"

if [ -f "shared/metrics.py" ]; then
    echo -n "Metrics Module File: "
    echo -e "${GREEN}✓ Found${NC}"
    ((PASSED++))
    
    # Check for key functions
    echo -n "  - normalize_endpoint function: "
    if grep -q "def normalize_endpoint" "shared/metrics.py"; then
        echo -e "${GREEN}✓ Found${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Missing${NC}"
        ((FAILED++))
    fi
    
    echo -n "  - add_metrics_middleware function: "
    if grep -q "def add_metrics_middleware" "shared/metrics.py"; then
        echo -e "${GREEN}✓ Found${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Missing${NC}"
        ((FAILED++))
    fi
    
    echo -n "  - track_operation decorator: "
    if grep -q "def track_operation" "shared/metrics.py"; then
        echo -e "${GREEN}✓ Found${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Missing${NC}"
        ((FAILED++))
    fi
    
    echo -n "  - get_metrics_response function: "
    if grep -q "def get_metrics_response" "shared/metrics.py"; then
        echo -e "${GREEN}✓ Found${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ Missing${NC}"
        ((FAILED++))
    fi
else
    echo -e "${RED}✗ shared/metrics.py not found${NC}"
    ((FAILED++))
fi
echo ""

# ============================================================================
# 10. Check Service Integrations
# ============================================================================
echo -e "${YELLOW}10. Service Metrics Integration${NC}"
echo "---"

for service in payment order inventory notification cart; do
    path="services/${service}-service/main.py"
    if [ -f "$path" ]; then
        echo -n "$service-service: "
        
        if grep -q "add_metrics_middleware" "$path"; then
            echo -e "${GREEN}✓ Instrumented${NC}"
            ((PASSED++))
        else
            echo -e "${RED}✗ Not instrumented${NC}"
            ((FAILED++))
        fi
    fi
done
echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Validation Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

TOTAL=$((PASSED + FAILED))
PERCENTAGE=$((PASSED * 100 / TOTAL))

echo -e "Passed:  ${GREEN}$PASSED${NC}"
echo -e "Failed:  ${RED}$FAILED${NC}"
echo -e "Total:   $TOTAL"
echo -e "Score:   $PERCENTAGE%"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All validations passed!${NC}"
    echo ""
    echo "Your monitoring stack is ready for production:"
    echo "  - Prometheus: http://localhost:9090"
    echo "  - Grafana: http://localhost:3000 (admin/admin)"
    echo "  - Microservices Dashboard: http://localhost:3000/d/microservices-dashboard"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Some validations failed${NC}"
    echo ""
    echo "Please fix the above issues and re-run this script."
    echo ""
    exit 1
fi
