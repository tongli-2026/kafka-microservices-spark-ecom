# Spark Analytics Dashboard - Testing Guide

## Overview

This guide provides comprehensive instructions for testing the Spark Analytics Dashboard, including setup, data generation, validation, and troubleshooting.

**Dashboard UID:** `spark-analytics-dashboard`  
**Dashboard URL:** `http://localhost:3000/d/spark-analytics-dashboard`  
**Metrics Source:** PostgreSQL (via Spark Metrics Exporter)  
**Update Frequency:** 30 seconds

---

## Prerequisites

Before testing, ensure all components are running:

### 1. Core Services
```bash
# Check if all services are running
docker-compose ps

# Expected services (status: running):
# - postgres
# - kafka (broker 1, 2, 3)
# - spark-master
# - spark-worker-1, spark-worker-2
# - prometheus
# - grafana
# - spark-metrics-exporter (NEW)
# - (cart-service, order-service, payment-service, inventory-service, notification-service)
```

### 2. Spark Analytics Jobs
```bash
# Check if analytics jobs are running
docker-compose logs spark-master | grep -i "Submitted"
docker-compose logs spark-worker-1 | grep -i "Task"

# Or check via Spark UI
# Visit: http://localhost:8080 (Spark Master)
# Visit: http://localhost:8081 (Spark Worker 1)
# Visit: http://localhost:8082 (Spark Worker 2)
```

### 3. Metrics Exporter
```bash
# Verify metrics exporter is running
docker-compose ps | grep spark-metrics-exporter

# Check metrics endpoint
curl http://localhost:9091/metrics | head -20

# Should see Spark metrics like:
# spark_revenue_total_24h
# spark_fraud_alerts_total
# spark_cart_abandoned_24h
# etc.
```

### 4. Grafana Access
```bash
# Access Grafana
# URL: http://localhost:3000
# Credentials: admin / admin

# Verify Prometheus datasource is connected
# Go to: Configuration → Data Sources → Prometheus
# Should show: "Data source is working"
```

---

## Testing Strategy

### Level 1: Infrastructure Validation ✅
Verify all components are healthy and connected

### Level 2: Data Flow Validation 📊
Verify data flows from Spark jobs → PostgreSQL → Metrics Exporter → Prometheus

### Level 3: Metrics Validation 📈
Verify individual metrics are being exported and queried correctly

### Level 4: Dashboard Validation 🎯
Verify dashboard panels display correct data and visualizations

### Level 5: End-to-End Testing 🔄
Generate test traffic and verify dashboard updates in real-time

---

## Level 1: Infrastructure Validation

### 1.1 Check Docker Compose Status

```bash
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom

# Start all services (if not running)
docker-compose up -d

# Verify all services are running
docker-compose ps

# Expected output:
# CONTAINER ID   IMAGE                    STATUS       PORTS
# ...            postgres:15              Up 2 minutes
# ...            kafka:latest             Up 2 minutes
# ...            spark-master             Up 2 minutes
# ...            spark-worker-1           Up 2 minutes
# ...            spark-worker-2           Up 2 minutes
# ...            prometheus:latest        Up 2 minutes
# ...            grafana:latest           Up 2 minutes
# ...            metrics-exporter         Up 2 minutes
```

### 1.2 Verify Spark Metrics Exporter

```bash
# Check exporter logs
docker-compose logs -f spark-metrics-exporter

# Expected logs:
# 2026-03-17 10:00:00 - Starting Spark Metrics Exporter
# 2026-03-17 10:00:01 - Connected to PostgreSQL: postgresql://user:password@postgres:5432/ecommerce
# 2026-03-17 10:00:02 - Starting HTTP server on 0.0.0.0:9090
# 2026-03-17 10:00:02 - Metrics update cycle: every 30 seconds
# 2026-03-17 10:00:32 - Updated metrics (query took 0.125s)
```

### 1.3 Verify Metrics Endpoint

```bash
# Check metrics are being exported
curl -s http://localhost:9091/metrics | head -30

# Expected output (should contain):
# # HELP spark_revenue_total_24h 24 hour total revenue
# # TYPE spark_revenue_total_24h gauge
# spark_revenue_total_24h 0.0
# # HELP spark_fraud_alerts_total Total fraud alerts detected
# # TYPE spark_fraud_alerts_total gauge
# spark_fraud_alerts_total 0
# ... (more metrics)

# Count total metrics
curl -s http://localhost:9091/metrics | grep "^spark_" | wc -l
# Should show: 21 (if all Spark metrics are present)
```

### 1.4 Verify Prometheus Scrape

```bash
# Check if Prometheus can scrape the exporter
curl -s http://localhost:9090/api/v1/targets?state=active | jq '.data.activeTargets[] | select(.labels.job == "spark-metrics-exporter")'

# Expected output:
# {
#   "discoveredLabels": { ... },
#   "labels": {
#     "job": "spark-metrics-exporter",
#     "instance": "spark-metrics-exporter:9090"
#   },
#   "scrapePool": "spark-metrics-exporter",
#   "scrapeUrl": "http://spark-metrics-exporter:9090/metrics",
#   "globalUrl": "http://localhost:9090/metrics?job=spark-metrics-exporter"
# }

# Verify no scrape errors
curl -s 'http://localhost:9090/api/v1/query?query=up{job="spark-metrics-exporter"}' | jq '.data.result[]'

# Expected output:
# {
#   "metric": {
#     "__name__": "up",
#     "job": "spark-metrics-exporter",
#     "instance": "spark-metrics-exporter:9090"
#   },
#   "value": [ 1710000000, "1" ]  # Value 1 = scrape successful
# }
```

### 1.5 Verify PostgreSQL Connectivity

```bash
# Check PostgreSQL connection from exporter
docker-compose exec spark-metrics-exporter python -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='postgres',
        port=5432,
        database='ecommerce',
        user='postgres',
        password='postgres'
    )
    cursor = conn.cursor()
    
    # Check each analytics table
    for table in ['revenue_metrics', 'fraud_alerts', 'inventory_velocity', 'cart_abandonment', 'operational_metrics']:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        count = cursor.fetchone()[0]
        print(f'{table}: {count} rows')
    
    conn.close()
    print('✓ PostgreSQL connection successful')
except Exception as e:
    print(f'✗ PostgreSQL connection failed: {e}')
"
```

---

## Level 2: Data Flow Validation

### 2.1 Verify Spark Jobs Have Run

```bash
# Check PostgreSQL for recent data from Spark jobs
docker-compose exec postgres psql -U postgres -d ecommerce -c "
SELECT 
    'revenue_metrics' as table_name,
    COUNT(*) as row_count,
    MAX(window_start) as latest_window
FROM revenue_metrics

UNION ALL

SELECT 
    'fraud_alerts',
    COUNT(*),
    MAX(alert_timestamp)
FROM fraud_alerts

UNION ALL

SELECT 
    'inventory_velocity',
    COUNT(*),
    MAX(window_start)
FROM inventory_velocity

UNION ALL

SELECT 
    'cart_abandonment',
    COUNT(*),
    MAX(detected_at)
FROM cart_abandonment

UNION ALL

SELECT 
    'operational_metrics',
    COUNT(*),
    MAX(window_start)
FROM operational_metrics;
"

# Expected output (at least some rows in each table):
# table_name          | row_count | latest_window
# revenue_metrics     | 50        | 2026-03-17 10:00:00
# fraud_alerts        | 12        | 2026-03-17 10:05:15
# inventory_velocity  | 25        | 2026-03-17 10:02:30
# cart_abandonment    | 8         | 2026-03-17 10:04:45
# operational_metrics | 15        | 2026-03-17 10:03:10
```

### 2.2 Check Data Flow: PostgreSQL → Metrics Exporter

```bash
# Query metrics exporter logs for successful queries
docker-compose logs spark-metrics-exporter 2>&1 | tail -50 | grep -E "(Updated metrics|error|exception)"

# Or run a manual metric update
docker-compose exec spark-metrics-exporter python -c "
from analytics.metrics_exporter import update_all_metrics
try:
    update_all_metrics()
    print('✓ Metrics updated successfully')
except Exception as e:
    print(f'✗ Metrics update failed: {e}')
    import traceback
    traceback.print_exc()
"
```

### 2.3 Check Data Flow: Metrics Exporter → Prometheus

```bash
# Query Prometheus for Spark metrics (should show recent data points)
curl -s 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h' | jq '.data.result[] | {metric: .metric, value: .value, timestamp: .value[0]}'

# Expected output:
# {
#   "metric": {
#     "__name__": "spark_revenue_total_24h",
#     "service": "spark-analytics"
#   },
#   "value": [1710000000, "15234.50"],
#   "timestamp": 1710000000
# }

# Verify metric timestamp is recent (within last 2-3 minutes)
date +%s  # Current timestamp
# Should be close to the metric timestamp
```

---

## Level 3: Metrics Validation

### 3.1 Query Individual Metrics

```bash
# Test Revenue Metrics
echo "=== Revenue Metrics ==="
curl -s 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'
curl -s 'http://localhost:9090/api/v1/query?query=spark_order_count_24h' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'
curl -s 'http://localhost:9090/api/v1/query?query=spark_avg_order_value' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'

# Test Fraud Metrics
echo "=== Fraud Metrics ==="
curl -s 'http://localhost:9090/api/v1/query?query=spark_fraud_alerts_total' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'
curl -s 'http://localhost:9090/api/v1/query?query=spark_fraud_alerts_rate_per_hour' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'

# Test Inventory Metrics
echo "=== Inventory Metrics ==="
curl -s 'http://localhost:9090/api/v1/query?query=spark_inventory_velocity_units_sold_24h' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'

# Test Cart Metrics
echo "=== Cart Metrics ==="
curl -s 'http://localhost:9090/api/v1/query?query=spark_cart_abandoned_24h' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'
curl -s 'http://localhost:9090/api/v1/query?query=spark_cart_abandonment_rate' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'

# Test Job Metrics
echo "=== Job Metrics ==="
curl -s 'http://localhost:9090/api/v1/query?query=spark_job_success_total' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'
curl -s 'http://localhost:9090/api/v1/query?query=spark_job_failure_total' | jq '.data.result[] | {metric: .metric.__name__, value: .value[1]}'
```

### 3.2 Verify Metric Data Types

```bash
# All Spark metrics should be either Gauge, Counter, or Histogram
curl -s http://localhost:9091/metrics | grep "^# TYPE spark_"

# Expected output:
# # TYPE spark_revenue_total_24h gauge
# # TYPE spark_order_count_24h gauge
# # TYPE spark_avg_order_value gauge
# # TYPE spark_revenue_per_minute gauge
# # TYPE spark_fraud_alerts_total gauge
# # TYPE spark_fraud_by_type_total gauge
# # TYPE spark_fraud_alerts_rate_per_hour gauge
# # TYPE spark_inventory_velocity_units_sold_24h gauge
# # TYPE spark_top_product_units_sold gauge
# # TYPE spark_top_product_revenue gauge
# # TYPE spark_cart_abandoned_24h gauge
# # TYPE spark_cart_abandonment_rate gauge
# # TYPE spark_cart_recovery_rate gauge
# # TYPE spark_job_success_total gauge
# # TYPE spark_job_failure_total gauge
# # TYPE spark_job_duration histogram
# # (etc.)
```

### 3.3 Check Metric Value Ranges

```bash
# Revenue should be positive and reasonable
echo "Revenue check:"
curl -s 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h' | jq '.data.result[] | .value[1] | tonumber' | awk '{if ($1 >= 0) print "✓ Valid"; else print "✗ Invalid (negative)"}'

# Order count should be integer
echo "Order count check:"
curl -s 'http://localhost:9090/api/v1/query?query=spark_order_count_24h' | jq '.data.result[] | .value[1] | tonumber' | awk '{if ($1 == int($1)) print "✓ Valid (integer)"; else print "✗ Invalid (not integer)"}'

# Rates should be between 0-100 or 0-1
echo "Abandonment rate check:"
curl -s 'http://localhost:9090/api/v1/query?query=spark_cart_abandonment_rate' | jq '.data.result[] | .value[1] | tonumber' | awk '{if ($1 >= 0 && $1 <= 100) print "✓ Valid range"; else print "✗ Invalid range"}'

# Job duration should be in milliseconds (positive)
echo "Job duration check:"
curl -s 'http://localhost:9090/api/v1/query?query=spark_job_duration{job_name="revenue_streaming"}' | jq '.data.result[] | .value[1] | tonumber' | awk '{if ($1 > 0 && $1 < 3600000) print "✓ Valid (1s - 1h)"; else print "✗ Invalid range"}'
```

---

## Level 4: Dashboard Validation

### 4.1 Verify Dashboard Exists

```bash
# Check if dashboard is registered in Grafana
curl -s -u admin:admin 'http://localhost:3000/api/dashboards/uid/spark-analytics-dashboard' | jq '.dashboard | {uid: .uid, title: .title, panels: (.panels | length)}'

# Expected output:
# {
#   "uid": "spark-analytics-dashboard",
#   "title": "Spark Analytics Dashboard",
#   "panels": 20
# }
```

### 4.2 Access Dashboard in Browser

1. Open Grafana: `http://localhost:3000`
2. Login: `admin / admin`
3. Navigate to **Dashboards** → **Browse**
4. Search for **"Spark Analytics"**
5. Click to open

Expected view:
- Dashboard title: "Spark Analytics Dashboard"
- Last refresh time shown (should be within last 30 seconds)
- 20 panels visible across 5 sections

### 4.3 Verify Dashboard Sections

Navigate through each section and verify panels load:

#### Section 1: Revenue Analytics
- [ ] **24h Total Revenue** (Blue Gauge) - Shows USD amount
- [ ] **24h Order Count** (Green Gauge) - Shows order count
- [ ] **Average Order Value** (Orange Gauge) - Shows USD per order
- [ ] **Revenue Per Minute** (Purple Gauge) - Shows USD/min
- [ ] **Revenue Trend (24h)** (Timeseries) - Shows historical trend
- [ ] **Order Count Trend (24h)** (Timeseries) - Shows order volume trend

#### Section 2: Fraud Detection
- [ ] **Total Fraud Alerts** (Red Gauge) - Shows alert count
- [ ] **Fraud Alerts by Type** (Stacked Bar) - Shows alert distribution
- [ ] **Fraud Alert Rate** (Timeseries) - Shows alerts/hour

#### Section 3: Inventory Analytics
- [ ] **24h Units Sold** (Green Gauge) - Shows unit count
- [ ] **Top 10 Products by Units Sold** (Bar Chart) - Shows product rankings
- [ ] **Top 10 Products by Revenue** (Bar Chart) - Shows revenue rankings

#### Section 4: Cart Abandonment
- [ ] **24h Abandoned Carts** (Orange Gauge) - Shows cart count
- [ ] **Cart Abandonment Rate** (Threshold Gauge) - Shows percentage
- [ ] **Cart Recovery Rate** (Threshold Gauge) - Shows percentage (likely 0%)
- [ ] **Cart Abandonment Trend** (Timeseries) - Shows trend

#### Section 5: Spark Job Operations
- [ ] **Total Successful Jobs** (Green Gauge) - Shows count
- [ ] **Total Failed Jobs** (Red Gauge) - Shows count
- [ ] **Job Success vs Failure Rate** (Stacked Area) - Shows comparison
- [ ] **Spark Job Execution Duration by Job** (Multi-line Timeseries) - Shows 5 job lines

### 4.4 Check for Data vs No Data

If panels show **"No data"**:
1. Check if data exists in PostgreSQL (Level 2.1)
2. Check if metrics exporter is running (Level 1.3)
3. Check Prometheus scrape targets (Level 1.4)
4. Check panel queries (see Level 4.5)

### 4.5 Verify Panel Queries

Click on each panel and check the query:

```bash
# Example: Click "24h Total Revenue" panel
# → Click panel title or menu icon
# → View query (should show):
# Query: spark_revenue_total_24h
# Datasource: Prometheus
# Status: "✓ Data source working"

# Example: Click "Revenue Trend" panel
# → Should show query:
# Query: spark_revenue_total_24h
# Type: Timeseries
# With legend showing: mean, max, last
```

---

## Level 5: End-to-End Testing

### 5.1 Generate Test Traffic

```bash
# Option 1: Run simulation script
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom
python scripts/simulate-users.py --duration 300 --rate 10  # 5 min test, 10 users/sec

# Option 2: Run test workflow
bash scripts/test-complete-workflow.sh

# Option 3: Generate specific test scenarios
bash scripts/test-scenarios.sh --scenario high-fraud
bash scripts/test-scenarios.sh --scenario cart-abandonment
```

### 5.2 Monitor Data Ingestion

While test traffic is running:

```bash
# Terminal 1: Watch metrics exporter logs
docker-compose logs -f spark-metrics-exporter | grep -E "(Updated|error|Processing)"

# Terminal 2: Watch PostgreSQL data accumulation
watch "docker-compose exec postgres psql -U postgres -d ecommerce -c \"
SELECT 
    (SELECT COUNT(*) FROM revenue_metrics) as revenue_rows,
    (SELECT COUNT(*) FROM fraud_alerts) as fraud_rows,
    (SELECT COUNT(*) FROM inventory_velocity) as inventory_rows,
    (SELECT COUNT(*) FROM cart_abandonment) as cart_rows,
    (SELECT COUNT(*) FROM operational_metrics) as ops_rows;
\""

# Terminal 3: Watch Prometheus metrics
watch "curl -s 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h' | jq '.data.result[] | {value: .value[1]}'"

# Terminal 4: Monitor Spark jobs
docker-compose logs -f spark-master | grep -i "completed\|failed"
```

### 5.3 Refresh Dashboard

1. Open dashboard: `http://localhost:3000/d/spark-analytics-dashboard`
2. Set refresh to **5 seconds** (top right corner)
3. Watch panels update in real-time as data flows in
4. Verify all gauges and charts show changing values

### 5.4 Validate All Metrics Update

```bash
# Run this script to verify all 21 metrics have recent data
bash scripts/validate-spark-metrics.sh << 'EOF'
#!/bin/bash

metrics=(
    "spark_revenue_total_24h"
    "spark_order_count_24h"
    "spark_avg_order_value"
    "spark_revenue_per_minute"
    "spark_fraud_alerts_total"
    "spark_fraud_by_type_total"
    "spark_fraud_alerts_rate_per_hour"
    "spark_inventory_velocity_units_sold_24h"
    "spark_top_product_units_sold"
    "spark_top_product_revenue"
    "spark_cart_abandoned_24h"
    "spark_cart_abandonment_rate"
    "spark_cart_recovery_rate"
    "spark_job_success_total"
    "spark_job_failure_total"
    "spark_job_duration"
    "spark_job_records_processed_total"
)

echo "Validating all Spark metrics..."
echo ""

for metric in "${metrics[@]}"; do
    result=$(curl -s "http://localhost:9090/api/v1/query?query=$metric" | jq '.data.result | length')
    if [ "$result" -gt 0 ]; then
        echo "✓ $metric (has data)"
    else
        echo "✗ $metric (NO DATA)"
    fi
done
EOF
```

---

## Common Issues & Troubleshooting

### Issue 1: Dashboard Shows "No Data"

**Diagnosis:**
```bash
# Check if metrics exporter is running
docker-compose ps | grep spark-metrics-exporter

# Check if PostgreSQL has data
docker-compose exec postgres psql -U postgres -d ecommerce -c "SELECT COUNT(*) FROM revenue_metrics"

# Check Prometheus can scrape
curl -s 'http://localhost:9090/api/v1/query?query=up{job="spark-metrics-exporter"}' | jq '.data.result[].value[1]'
```

**Solutions:**
1. Ensure `spark-metrics-exporter` container is running: `docker-compose up -d spark-metrics-exporter`
2. Check exporter logs: `docker-compose logs spark-metrics-exporter`
3. Verify PostgreSQL connectivity: `docker-compose exec postgres psql -U postgres -d ecommerce -c "SELECT 1"`
4. Manually trigger metrics update: `docker-compose exec spark-metrics-exporter python -c "from analytics.metrics_exporter import update_all_metrics; update_all_metrics()"`

### Issue 2: Metrics Exporter Connection Error

**Error:**
```
psycopg2.OperationalError: could not connect to server: Connection refused
```

**Solution:**
```bash
# Ensure PostgreSQL is running
docker-compose up -d postgres

# Wait 30 seconds for PostgreSQL to start
sleep 30

# Restart metrics exporter
docker-compose restart spark-metrics-exporter
```

### Issue 3: Prometheus Cannot Scrape Metrics Exporter

**Diagnosis:**
```bash
# Check scrape status
curl -s 'http://localhost:9090/api/v1/targets?state=unhealthy' | jq '.'
```

**Solution:**
```bash
# Verify exporter is listening on correct port
docker-compose exec spark-metrics-exporter curl -s http://localhost:9090/metrics | head -5

# Check Docker network
docker network inspect kafka-network | grep spark-metrics-exporter

# Restart if needed
docker-compose restart spark-metrics-exporter prometheus
```

### Issue 4: Dashboard Panels Load Slowly

**Optimization:**
1. Increase Prometheus retention: `--storage.tsdb.retention.time=30d`
2. Reduce query complexity (use shorter time ranges)
3. Adjust dashboard refresh rate to 1 minute instead of 30 seconds
4. Check Prometheus server resources: `docker stats prometheus`

### Issue 5: Cart Recovery Rate Always Shows 0%

**Expected Behavior:** ✓ This is correct! 

Current PostgreSQL schema does not track cart recovery - only detections. See DASHBOARDS_COMPLETE_SUITE.md "Known Limitations" section for schema enhancement needed.

---

## Automated Testing

### Create Comprehensive Test Script

```bash
#!/bin/bash
# test-spark-dashboard.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Spark Analytics Dashboard Test ===${NC}\n"

# Test 1: Infrastructure
echo "Test 1: Infrastructure Validation..."
docker-compose ps | grep spark-metrics-exporter > /dev/null && echo -e "${GREEN}✓ Exporter running${NC}" || echo -e "${RED}✗ Exporter not running${NC}"

# Test 2: Metrics Endpoint
echo "Test 2: Metrics Endpoint..."
curl -s http://localhost:9091/metrics | grep spark_revenue_total_24h > /dev/null && echo -e "${GREEN}✓ Metrics available${NC}" || echo -e "${RED}✗ No metrics${NC}"

# Test 3: Prometheus Scrape
echo "Test 3: Prometheus Scrape..."
curl -s 'http://localhost:9090/api/v1/query?query=up{job="spark-metrics-exporter"}' | jq '.data.result[].value[1]' | grep "1" > /dev/null && echo -e "${GREEN}✓ Scraping OK${NC}" || echo -e "${RED}✗ Scrape failed${NC}"

# Test 4: Dashboard Exists
echo "Test 4: Dashboard Exists..."
curl -s -u admin:admin 'http://localhost:3000/api/dashboards/uid/spark-analytics-dashboard' | jq '.dashboard.title' | grep "Spark Analytics" > /dev/null && echo -e "${GREEN}✓ Dashboard found${NC}" || echo -e "${RED}✗ Dashboard not found${NC}"

# Test 5: Metrics Data
echo "Test 5: Metrics Data..."
metric_count=$(curl -s 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h' | jq '.data.result | length')
[ $metric_count -gt 0 ] && echo -e "${GREEN}✓ Data present (${metric_count} metrics)${NC}" || echo -e "${RED}✗ No data${NC}"

echo -e "\n${BLUE}=== All Tests Complete ===${NC}"
```

---

## Performance Benchmarks

### Expected Query Response Times

| Query | Expected Time | Tool |
|-------|---|---|
| Single gauge metric | < 100ms | Browser |
| Timeseries (6h data) | < 500ms | Browser |
| Full dashboard load | < 2s | Browser |
| Dashboard refresh (30s) | < 1s | Browser |

### Expected Resource Usage

| Component | CPU | Memory | Network |
|-----------|-----|--------|---------|
| spark-metrics-exporter | < 5% | < 100MB | < 1Mbps |
| PostgreSQL queries | < 10% | (depends) | (local) |
| Prometheus scrape | < 5% | < 500MB | < 1Mbps |
| Grafana (6 dashboards) | < 2% | < 200MB | (varies) |

---

## Validation Checklist

Use this checklist to verify complete functionality:

### Infrastructure ✓
- [ ] All Docker containers running
- [ ] Spark metrics exporter logs show "Updated metrics"
- [ ] PostgreSQL has data in all 5 analytics tables
- [ ] Metrics exporter HTTP endpoint responds with metrics
- [ ] Prometheus scrape job marked as "UP"

### Metrics ✓
- [ ] All 21 Spark metrics appear in `/metrics` endpoint
- [ ] Each metric has current data (not stale)
- [ ] Metric values are in expected ranges (see Level 3.3)
- [ ] Revenue metrics show positive values
- [ ] Job metrics show success/failure counts
- [ ] Fraud metrics show alert counts

### Dashboard ✓
- [ ] Dashboard accessible via `http://localhost:3000/d/spark-analytics-dashboard`
- [ ] All 20 panels visible
- [ ] No "No data" errors on panels
- [ ] Gauges show appropriate colors (green/orange/red)
- [ ] Timeseries charts show trend lines
- [ ] Thresholds and comparisons look correct

### Data Flow ✓
- [ ] PostgreSQL data updates over time
- [ ] Metrics exporter queries complete within 5 seconds
- [ ] Prometheus metrics update every 30 seconds
- [ ] Dashboard auto-refreshes and shows new data
- [ ] Test traffic increases metric values
- [ ] Time ranges filter data correctly

### Alerts (Optional) ✓
- [ ] Can create alert rules on metrics
- [ ] Alert threshold logic works correctly
- [ ] Notifications can be configured

---

## Additional Resources

- **Spark Jobs Documentation:** `SPARK_OPERATIONS.md`
- **Dashboard Documentation:** `DASHBOARDS_COMPLETE_SUITE.md`
- **Metrics Exporter Code:** `analytics/metrics_exporter.py`
- **Prometheus Queries:** `monitoring/prometheus.yml`
- **Database Schema:** `shared/database.py`

---

## Next Steps After Validation

Once dashboard testing is complete:

1. ✅ Set up alert rules for critical metrics
2. ✅ Configure team access to dashboards
3. ✅ Document SLA targets and thresholds
4. ✅ Schedule regular dashboard reviews
5. ✅ Plan schema enhancements (cart recovery tracking)
6. ✅ Consider adding more specialized dashboards as needed

---

## Quick Test Command

Run this one-liner for a quick validation:

```bash
echo "Testing Spark Analytics Dashboard..." && \
docker-compose ps | grep spark-metrics-exporter && \
curl -s http://localhost:9091/metrics | grep -c spark_ && \
curl -s 'http://localhost:3000/api/dashboards/uid/spark-analytics-dashboard' | jq '.dashboard.title' && \
echo "✓ All systems operational"
```

Expected output:
```
Testing Spark Analytics Dashboard...
spark-metrics-exporter   Up X minutes
21
"Spark Analytics Dashboard"
✓ All systems operational
```
