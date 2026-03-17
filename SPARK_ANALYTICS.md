# Spark Analytics - Complete Operations & Testing Guide

> **Status:** ✅ FULLY OPERATIONAL  
> **Last Updated:** March 17, 2026  
> **System Version:** Spark 3.5.0, PySpark 3.5.0  
> **Monitoring:** Prometheus + Grafana Dashboard Ready

**Consolidated Reference:** All Spark operations, analytics jobs, testing, monitoring, and troubleshooting in one place.

---

## Table of Contents

1. [TL;DR - Quick Commands](#tldr---quick-commands)
2. [System Status](#system-status)
3. [Getting Started](#getting-started)
4. [Job Operations](#job-operations)
5. [Testing & Data Generation](#testing--data-generation)
6. [Monitoring & Analytics Dashboard](#monitoring--analytics-dashboard)
7. [Architecture & Deep Dive](#architecture--deep-dive)
8. [Job Scheduling](#job-scheduling)
9. [Troubleshooting](#troubleshooting)
10. [Background & Implementation](#background--implementation)

---

## TL;DR - Quick Commands

### Most Common Operations

```bash
# ✅ Check system status (MOST IMPORTANT)
./scripts/spark/quick-status.sh

# ✅ Start all 5 analytics jobs
./scripts/spark/start-spark-jobs.sh

# ✅ Restart a specific job
./scripts/spark/restart-job.sh <job_name>

# ✅ Generate test data (simulate users)
python scripts/simulate-users.py --mode continuous --duration 300 --interval 15

# ✅ View Spark Master UI
open http://localhost:9080

# ✅ View Grafana Dashboard
open http://localhost:3000/d/spark-analytics-dashboard

# ✅ View raw metrics
curl http://localhost:9097/metrics | grep spark_

# ✅ Check PostgreSQL analytics data
docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM revenue_metrics;"

# ✅ Monitor metrics exporter logs
docker logs -f spark-metrics-exporter

# ✅ Monitor Spark jobs
./scripts/spark/monitor-spark-jobs.sh
```

---

## System Status

### ✅ Currently Running Components

```
✅ Spark Cluster:
   - Spark Master (port 7077, UI: 9080)
   - Spark Worker 1 (port 4040, UI: 8081)
   - Spark Worker 2 (port 8081 UI, 4040 driver)

✅ Analytics Infrastructure:
   - Metrics Exporter (port 9097, queries PostgreSQL every 30s)
   - Prometheus (port 9090, scrapes metrics every 30s)
   - Grafana (port 3000, admin/admin)
   - PostgreSQL (port 5432, 5 analytics tables)
   - Redis (port 6379, caching)

❌ NOT Running Yet (Manual Start Required):
   - 5 Spark Analytics Jobs:
     * fraud_detection
     * revenue_streaming
     * cart_abandonment
     * inventory_velocity
     * operational_metrics
   - Analytics Data (empty tables, waiting for job output)
```

### Expected Metrics Status

**Before starting jobs:**
```
All Spark metrics = 0.0
curl http://localhost:9097/metrics | grep spark_
# Output: spark_revenue_total_24h = 0.0, spark_order_count_24h = 0.0, etc.
```

**After starting jobs + generating data (1-2 minutes):**
```
All Spark metrics = actual values
curl http://localhost:9097/metrics | grep spark_
# Output: spark_revenue_total_24h = 12345.67, spark_order_count_24h = 42, etc.
```

---

## Getting Started

### Step 1: Verify Everything is Running

```bash
# Check all Spark services
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "spark|exporter|prometheus|grafana"

# Expected output:
# spark-master          Up 5 minutes
# spark-worker-1        Up 5 minutes
# spark-worker-2        Up 5 minutes
# spark-metrics-exporter Up 5 minutes (healthy)
# prometheus            Up 5 minutes (healthy)
# grafana               Up 5 minutes (healthy)
```

### Step 2: Start Analytics Jobs

```bash
# Option A: Start all 5 jobs at once (RECOMMENDED)
./scripts/spark/start-spark-jobs.sh

# Option B: Start individual job
./scripts/spark/run-spark-job.sh revenue_streaming

# Option C: Manual spark-submit
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  /path/to/analytics/jobs/revenue_streaming.py
```

### Step 3: Generate Test Data

```bash
# Generate continuous e-commerce traffic for 5 minutes
python scripts/simulate-users.py --mode continuous --duration 300 --interval 15

# Alternative: Single order test
python scripts/simulate-users.py --mode single

# Alternative: Full workflow test
./scripts/test-complete-workflow.sh
```

### Step 4: Monitor Data Flow (1-2 minutes)

```bash
# Watch metrics exporter collecting data
docker logs -f spark-metrics-exporter

# Expected: "Successfully updated all metrics" every 30 seconds

# Or check if data is in PostgreSQL
watch "docker exec postgres psql -U postgres -d kafka_ecom -c 'SELECT COUNT(*) FROM revenue_metrics;'"

# Or query Prometheus for metrics
curl 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h'
```

### Step 5: View Dashboard

```
1. Open http://localhost:3000
2. Go to Dashboards → Spark Analytics Dashboard
3. Metrics will update every 30 seconds
```

---

## Job Operations

### 5 Spark Analytics Jobs

| Job Name | Purpose | Window | Update Freq | Output Table |
|----------|---------|--------|------------|--------------|
| **revenue_streaming** | Track revenue, orders, AOV | 1 minute | 1 min | revenue_metrics |
| **fraud_detection** | Detect suspicious transactions | 5 minutes | 5 min | fraud_alerts |
| **inventory_velocity** | Monitor product velocity | 1 hour | 1 hr | inventory_velocity |
| **cart_abandonment** | Detect abandoned carts | 15 minutes | 15 min | cart_abandonment |
| **operational_metrics** | Spark job execution tracking | Per-job | Continuous | operational_metrics |

### Start All Jobs

```bash
./scripts/spark/start-spark-jobs.sh

# This script:
# 1. Clears all checkpoints (for fresh start)
# 2. Submits all 5 jobs in background
# 3. Shows submission status
# 4. Displays monitoring instructions
```

### Restart Individual Job

```bash
./scripts/spark/restart-job.sh fraud_detection

# Or manually:
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  /path/to/analytics/jobs/fraud_detection.py
```

### Monitor Job Status

```bash
./scripts/spark/monitor-spark-jobs.sh

# Or view Spark Master UI: http://localhost:9080
# - Shows running applications
# - Job status (running/completed)
# - Task progress
# - Executor logs
```

### Stop a Job

```bash
# Find application ID from Spark UI (http://localhost:9080)
# Then kill it:
docker exec spark-master /opt/spark/bin/spark-shell <<EOF
sc.cancelAllJobs()
EOF
```

---

## Testing & Data Generation

### Why Generate Test Data?

Spark jobs process events from Kafka topics. Without data:
- PostgreSQL analytics tables stay empty
- Metrics exporter returns 0.0 values
- Dashboard shows no data

### Data Generation Options

#### Option 1: User Simulator (Recommended for Testing)

```bash
# Generate continuous traffic for 5 minutes
python scripts/simulate-users.py \
  --mode continuous \
  --duration 300 \
  --interval 15 \
  --users 10

# This generates:
# - Orders, Payments, Carts, Inventory events
# - Published to Kafka topics
# - Spark jobs consume and aggregate
# - Metrics appear in dashboard after 1-2 minutes
```

#### Option 2: Single Order Test

```bash
# Quick test - single order through entire flow
python scripts/simulate-users.py --mode single

# Check if it succeeded:
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT COUNT(*) FROM orders;"
```

#### Option 3: Complete Workflow Test

```bash
# Full end-to-end test script
./scripts/test-complete-workflow.sh

# This:
# - Creates test data
# - Processes through microservices
# - Verifies results
# - Checks PostgreSQL tables
```

### Testing Timeline

```
T+0s:     Start Spark jobs
T+5s:     Jobs connect to Kafka and PostgreSQL
T+10s:    First events consumed from Kafka
T+30s:    First metrics update from exporter
T+60s:    Metrics appear in Prometheus
T+90s:    Dashboard refreshes with data
T+120s:   Full data visible with trends

Duration: ~2 minutes from job start to populated dashboard
```

### Verify Data is Flowing

```bash
# 1. Check Kafka topics have events
docker exec kafka-ui curl -s http://localhost:8080/api/clusters/1/topics | grep -E "orders|payments"

# 2. Check PostgreSQL analytics tables
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT 'revenue_metrics' as table_name, COUNT(*) as row_count FROM revenue_metrics
   UNION ALL
   SELECT 'fraud_alerts', COUNT(*) FROM fraud_alerts
   UNION ALL
   SELECT 'cart_abandonment', COUNT(*) FROM cart_abandonment
   UNION ALL
   SELECT 'inventory_velocity', COUNT(*) FROM inventory_velocity;"

# Expected output (after 1-2 minutes):
#       table_name    | row_count
# ──────────────────────────────────
#  revenue_metrics    |       150
#  fraud_alerts       |        12
#  cart_abandonment   |        42
#  inventory_velocity |       500

# 3. Check metrics exporter is reading data
curl -s http://localhost:9097/metrics | grep spark_revenue_total_24h
# Expected: spark_revenue_total_24h{service="spark-analytics"} 12345.67

# 4. Check Prometheus has metrics
curl 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h'
# Expected: {"status":"success","data":{"result":[{"value":["timestamp","12345.67"]}]}}
```

---

## Monitoring & Analytics Dashboard

### Dashboard Access

```
URL: http://localhost:3000/d/spark-analytics-dashboard
Username: admin
Password: admin
Refresh Interval: 30 seconds (auto-refresh)
Time Range: Last 6 hours (default, configurable)
```

### 21 Spark Metrics Visualized

**Revenue Analytics (4 metrics)**
- `spark_revenue_total_24h` - 24-hour total revenue (USD)
- `spark_order_count_24h` - 24-hour order count
- `spark_avg_order_value` - Average order value (USD)
- `spark_revenue_per_minute` - Current revenue rate

**Fraud Detection (3 metrics)**
- `spark_fraud_alerts_total` - Total fraud alerts (24h)
- `spark_fraud_by_type_total` - Alerts by type
- `spark_fraud_alerts_rate_per_hour` - Alert rate (per hour)

**Inventory Analytics (3 metrics)**
- `spark_inventory_velocity_units_sold_24h` - Units sold (24h)
- `spark_top_product_units_sold` - Top 10 products by units
- `spark_top_product_revenue` - Top 10 products by revenue

**Cart Abandonment (3 metrics)**
- `spark_cart_abandoned_24h` - Abandoned carts detected
- `spark_cart_abandonment_rate` - Abandonment rate (%)
- `spark_cart_recovery_rate` - Recovery rate (%)

**Spark Job Operations (8 metrics)**
- `spark_job_success_total` - Successful job executions
- `spark_job_failure_total` - Failed job executions
- `spark_job_duration{job_name=...}` - Duration by job (5 metrics)
- `spark_job_records_processed_total` - Total records processed

### Dashboard Sections

1. **Revenue KPIs** (Top Row) - 4 gauges showing key revenue metrics
2. **Revenue Trends** - Time series of revenue and orders over 6h
3. **Fraud Monitoring** - Fraud alert totals, by type, and rate
4. **Inventory Performance** - Units sold, top products by units & revenue
5. **Cart Abandonment** - Abandoned count, abandonment rate, recovery rate, trends
6. **Spark Job Health** - Success/failure counts, job duration trends

### Metrics Export Endpoint

```bash
# Raw Prometheus metrics (every 30 seconds)
curl http://localhost:9097/metrics | grep spark_

# Query Prometheus API
curl 'http://localhost:9090/api/v1/query?query=spark_fraud_alerts_rate_per_hour'
curl 'http://localhost:9090/api/v1/query_range?query=spark_revenue_total_24h&start=<time>&end=<time>&step=30s'

# Grafana API
curl 'http://localhost:3000/api/datasources'
```

### Alert Configuration

**Recommended Alerts to Create:**

```yaml
# Alert 1: High Fraud Rate
condition: spark_fraud_alerts_rate_per_hour > 10 alerts/hour
severity: Warning
notification: Security team

# Alert 2: High Cart Abandonment
condition: spark_cart_abandonment_rate > 60%
severity: Warning
notification: Marketing team

# Alert 3: Spark Job Failure
condition: spark_job_failure_total > 5 in 1 hour
severity: Critical
notification: PagerDuty

# Alert 4: Revenue Anomaly
condition: spark_revenue_total_24h < avg(spark_revenue_total_24h) * 0.8
severity: Warning
notification: Finance team
```

---

## Architecture & Deep Dive

### System Architecture

```
Microservices → Kafka Broker Cluster → Spark Structured Streaming
                                            ↓
                                    5 Analytics Jobs (Parallel)
                                            ↓
                                    PostgreSQL Analytics Tables
                                            ↓
                                    Metrics Exporter (polls every 30s)
                                            ↓
                            Prometheus (scrapes every 30s)
                                            ↓
                        Grafana Dashboards (refreshes every 30s)
```

### How Spark Structured Streaming Works

Spark treats streaming data as an **infinite table** with continuous appends:

```python
# Kafka stream is treated as:
stream = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "orders") \
    .load()

# Write results as batches to PostgreSQL
query = stream \
    .groupBy(window("timestamp", "1 minute")) \
    .agg(sum("amount").alias("total_revenue"), count("*").alias("order_count")) \
    .writeStream \
    .format("jdbc") \
    .option("url", "jdbc:postgresql://postgres:5432/kafka_ecom") \
    .option("dbtable", "revenue_metrics") \
    .option("checkpointLocation", "/data/checkpoints/revenue") \
    .start()
```

### Windowing Strategies

Different jobs use different windows optimized for their analysis:

| Job | Window Type | Duration | Reason |
|-----|------------|----------|--------|
| revenue_streaming | Tumbling | 1 minute | High-frequency revenue tracking |
| fraud_detection | Tumbling + Sliding | 5 min window, 1 min slide | Overlapping windows for pattern detection across boundaries |
| inventory_velocity | Tumbling | 1 hour | Inventory trends over longer period |
| cart_abandonment | Stream-Stream Join | 30 minute join window | Left join: keep items without matching checkout within 30 minutes (abandoned) |
| operational_metrics | Tumbling | 1 minute | Event-based throughput monitoring per topic |

### Checkpoints & State Management

Spark uses checkpoints for **fault tolerance**:

```bash
# Checkpoint locations
/data/checkpoints/revenue/
/data/checkpoints/fraud_detection/
/data/checkpoints/inventory_velocity/
/data/checkpoints/cart_abandonment/
/data/checkpoints/operational_metrics/

# Clear checkpoints (for fresh start)
./scripts/spark/cleanup-checkpoints.sh

# Or manually:
docker exec spark-master rm -rf /data/checkpoints/*
```

### Event Schema

**Order Event (Kafka):**
```json
{
  "order_id": "O123456",
  "customer_id": "C789",
  "amount": 150.50,
  "items": [{"product_id": "P1", "quantity": 2}],
  "timestamp": "2026-03-17T14:30:00Z"
}
```

**Aggregated Result (PostgreSQL):**
```sql
-- revenue_metrics table
window_start | total_revenue | order_count | avg_order_value | product_id | revenue
2026-03-17 14:30:00 | 1500.00 | 10 | 150.00 | P1 | 300.00
```

---

## Job Scheduling

### Cron Job for Inventory Velocity

Inventory velocity job runs on a schedule (not continuous):

```bash
# View scheduled jobs
crontab -l | grep inventory

# Expected:
# */15 * * * * /path/to/schedule-inventory-velocity.sh

# Or manually trigger:
./scripts/schedule-inventory-velocity.sh

# View job output
docker logs spark-worker-1 | grep "inventory_velocity"
```

### Manual Job Scheduling

To run a job on a schedule (every 15 minutes):

```bash
# Create cron entry
(crontab -l; echo "*/15 * * * * /Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/spark/run-spark-job.sh inventory_velocity") | crontab -

# Monitor scheduled runs
watch "docker exec postgres psql -U postgres -d kafka_ecom -c 'SELECT window_start, SUM(units_sold) FROM inventory_velocity GROUP BY window_start ORDER BY window_start DESC LIMIT 5;'"
```

---

## Troubleshooting

### Problem: Dashboard Shows No Data

**Symptoms:** All metrics = 0.0, charts are empty

**Diagnosis Steps:**

```bash
# 1. Check if Spark jobs are running
./scripts/spark/monitor-spark-jobs.sh
# Expected: 5 jobs running (fraud_detection, revenue_streaming, cart_abandonment, inventory_velocity, operational_metrics)

# 2. Check if PostgreSQL tables have data
docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM revenue_metrics;"
# Expected: > 0 (if no data, jobs aren't writing)

# 3. Check if metrics exporter can read data
curl -s http://localhost:9097/metrics | grep spark_revenue_total_24h
# Expected: spark_revenue_total_24h{service="spark-analytics"} > 0.0

# 4. Check Spark job logs
docker logs spark-master | grep ERROR

# 5. Check Prometheus has metrics
curl 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h'
# Expected: Valid JSON response with value
```

**Solutions:**

```bash
# Solution A: Start Spark jobs
./scripts/spark/start-spark-jobs.sh

# Solution B: Generate test data
python scripts/simulate-users.py --mode continuous --duration 300

# Solution C: Restart metrics exporter
docker restart spark-metrics-exporter

# Solution D: Clear and restart everything
docker-compose down -v
docker-compose up -d
./scripts/spark/start-spark-jobs.sh
```

### Problem: Spark Jobs Not Starting

**Symptoms:** Jobs fail to submit or crash immediately

**Diagnosis:**

```bash
# 1. Check Spark Master is running
docker ps | grep spark-master
# If not: docker-compose restart spark-master

# 2. Check Spark Master UI
open http://localhost:9080
# Look for error messages in "Applications" section

# 3. Check logs
docker logs spark-master | tail -50

# 4. Check disk space for checkpoints
docker exec spark-master df -h /data/checkpoints/
# If full: ./scripts/spark/cleanup-checkpoints.sh

# 5. Check PostgreSQL connectivity
docker exec spark-master psql -h postgres -U postgres -d kafka_ecom -c "SELECT 1;"
```

**Solutions:**

```bash
# Solution A: Clear checkpoints and restart
./scripts/spark/cleanup-checkpoints.sh
./scripts/spark/start-spark-jobs.sh

# Solution B: Restart Spark cluster
docker-compose restart spark-master spark-worker-1 spark-worker-2

# Solution C: Full reset
docker-compose down -v
docker-compose up -d spark-master spark-worker-1 spark-worker-2
./scripts/spark/start-spark-jobs.sh
```

### Problem: Metrics Exporter Unhealthy

**Symptoms:** `docker ps` shows exporter as "unhealthy"

**Diagnosis:**

```bash
# Check exporter logs
docker logs spark-metrics-exporter

# Check if it can reach PostgreSQL
docker exec spark-metrics-exporter psql -h postgres -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM revenue_metrics;"

# Check if metrics endpoint works
curl -v http://localhost:9097/metrics
```

**Solutions:**

```bash
# Solution A: Restart exporter
docker restart spark-metrics-exporter

# Solution B: Rebuild exporter
docker-compose up -d --build spark-metrics-exporter

# Solution C: Check PostgreSQL is running
docker-compose restart postgres
docker restart spark-metrics-exporter
```

### Problem: Port Conflicts

**Symptoms:** "Port is already allocated" error

**Port Mapping Reference:**
```
Spark: 7077 (master comm), 4040 (driver UI), 8081-8082 (worker UI)
Prometheus: 9090
Grafana: 3000
Spark Metrics Exporter: 9097
Kafka Brokers: 9091-9096 (various)
PostgreSQL: 5432
Redis: 6379
```

**Solution:**
```bash
# Check what's using the port
lsof -i :7077

# If Docker container: docker inspect <container> | grep -i port
# If host process: kill <pid>

# Or use alternative port in docker-compose.yml
```

---

## Background & Implementation

### Project History

This Spark analytics system was built to provide real-time business intelligence for the Kafka microservices e-commerce platform:

- **Phase 1:** Microservices foundation (5 services, Kafka, PostgreSQL)
- **Phase 2:** Spark analytics layer (5 streaming jobs, windowed aggregations)
- **Phase 3:** Monitoring stack (Prometheus, Grafana, metrics exporter)
- **Phase 4:** Dashboards (6 comprehensive dashboards for different teams)

### Implementation Notes

**Database Schema Corrections Applied:**

During implementation, several database schema mismatches were discovered and fixed:

```
1. fraud_alerts: Used wrong column 'timestamp' → Fixed to 'alert_timestamp'
2. cart_abandonment: Used non-existent 'window_start' → Fixed to 'detected_at'
3. cart_abandonment: No 'status' column exists → Removed status filter
4. operational_metrics: No 'job_name' column → Extract from 'metric_name'
5. operational_metrics: No 'duration' column → Use 'metric_value' instead
```

All corrections verified against actual PostgreSQL schema and tested.

### Deployment Checklist

- ✅ Spark cluster deployed (Master + 2 Workers)
- ✅ 5 analytics jobs implemented (fraud, revenue, inventory, cart, operational)
- ✅ PostgreSQL analytics tables created (5 tables)
- ✅ Metrics exporter implemented (21 metrics exported)
- ✅ Prometheus configured (scraping all services)
- ✅ Grafana dashboards created (6 dashboards, 100+ panels)
- ✅ Port conflicts resolved (all unique ports, 24 total)
- ✅ Documentation complete (this file + additional references)
- ✅ Testing verified (all components healthy)

---

## Quick Reference

### Essential URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Spark Master UI | http://localhost:9080 | None |
| Spark Worker 1 UI | http://localhost:8081 | None |
| Spark Driver UI | http://localhost:4040 | None (when job running) |
| Prometheus | http://localhost:9090 | None |
| Grafana | http://localhost:3000 | admin/admin |
| Grafana - Spark Dashboard | http://localhost:3000/d/spark-analytics-dashboard | admin/admin |
| Kafka UI | http://localhost:8080 | None |
| Metrics Exporter | http://localhost:9097/metrics | None (raw metrics) |

### Useful Metrics Queries

```bash
# Total revenue in last 24 hours
curl 'http://localhost:9090/api/v1/query?query=spark_revenue_total_24h'

# Fraud alert rate
curl 'http://localhost:9090/api/v1/query?query=spark_fraud_alerts_rate_per_hour'

# Top product by revenue
curl 'http://localhost:9090/api/v1/query?query=topk(1,spark_top_product_revenue)'

# Job success rate
curl 'http://localhost:9090/api/v1/query?query=rate(spark_job_success_total[5m])'

# Average job duration
curl 'http://localhost:9090/api/v1/query?query=avg(spark_job_duration)'
```

### Common Issues & Quick Fixes

| Issue | Quick Fix |
|-------|-----------|
| No data in dashboard | `./scripts/spark/start-spark-jobs.sh && python scripts/simulate-users.py` |
| Spark job crashed | `docker-compose restart spark-master && ./scripts/spark/start-spark-jobs.sh` |
| Metrics exporter unhealthy | `docker restart spark-metrics-exporter` |
| Port conflict | `lsof -i :<port> && kill <pid>` or use alternative port |
| Database full | Clear checkpoints: `./scripts/spark/cleanup-checkpoints.sh` |

---

## Next Steps

1. ✅ Start Spark jobs: `./scripts/spark/start-spark-jobs.sh`
2. ✅ Generate test data: `python scripts/simulate-users.py`
3. ✅ View dashboard: http://localhost:3000/d/spark-analytics-dashboard
4. ✅ Set up alerts (optional): Configure alert rules in Grafana
5. ✅ Monitor regularly: Check dashboard during development/testing

---

## Support

For questions or issues:
1. Check the Troubleshooting section above
2. Review Spark Master UI: http://localhost:9080
3. Check logs: `docker logs <service-name>`
4. Review source code: `analytics/jobs/*.py`
