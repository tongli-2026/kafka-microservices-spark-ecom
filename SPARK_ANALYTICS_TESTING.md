# Spark Analytics Dashboard - Testing & Data Population Guide

## Quick Answer
**Q: Do I need to start Spark jobs to see the dashboard?**

**A: YES and NO**
- ✅ You CAN view the dashboard immediately (it's ready now)
- ❌ But it will show 0 data until Spark jobs populate the analytics tables
- ✅ To see real data: Start the Spark jobs → They'll populate PostgreSQL → Metrics exporter reads data → Dashboard shows metrics

---

## Current System Status

### ✅ What's Running Now
```
✅ Spark Cluster: Master + 2 Workers (all healthy)
✅ Metrics Exporter: Running and exporting 21 metrics (port 9097)
✅ Prometheus: Scraping metrics every 30 seconds (port 9090)
✅ Grafana: Ready with Spark Analytics Dashboard (port 3000)
✅ PostgreSQL: Connected and ready to receive data (port 5432)

❌ What's NOT Running Yet
❌ Spark Analytics Jobs: 5 streaming jobs (need manual start)
❌ Data in Analytics Tables: Currently empty (0 rows)
```

### Current Metrics Status
```bash
# Check exported metrics
curl -s http://localhost:9097/metrics | grep spark_

# Current values (all 0.0):
spark_revenue_total_24h = 0.0
spark_order_count_24h = 0.0
spark_fraud_alerts_total = 0.0
spark_cart_abandoned_24h = 0.0
spark_job_success_total = 0.0
# ... (all other metrics = 0.0)
```

---

## Step 1: View the Empty Dashboard (Optional)

You can view the dashboard structure right now without data:

```
URL: http://localhost:3000/d/spark-analytics-dashboard
Username: admin
Password: admin
```

**What you'll see:**
- All panels and visualizations are ready
- Gauges showing 0.0 values
- Time series charts will be empty
- No data alerts (expected - tables are empty)

---

## Step 2: Start the Spark Analytics Jobs

### Option A: Start All 5 Jobs at Once (Recommended)

```bash
# Navigate to project root
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom

# Run the script
./scripts/spark/start-spark-jobs.sh

# This will:
# 1. Clear all checkpoints
# 2. Submit all 5 jobs: fraud_detection, revenue_streaming, cart_abandonment, inventory_velocity, operational_metrics
# 3. Show submission status
```

### Option B: Start Individual Jobs

```bash
# Start a single job (example: revenue_streaming)
./scripts/spark/run-spark-job.sh revenue_streaming

# Available jobs:
# - fraud_detection
# - revenue_streaming
# - cart_abandonment
# - inventory_velocity
# - operational_metrics
```

### Option C: Manual Spark Submit

```bash
# Revenue Streaming Job
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  --driver-memory 1g \
  --executor-memory 1g \
  /path/to/analytics/jobs/revenue_streaming.py

# Fraud Detection Job
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  --driver-memory 1g \
  --executor-memory 1g \
  /path/to/analytics/jobs/fraud_detection.py
```

---

## Step 3: Generate Test Data (Important!)

**Note:** Spark jobs process events from Kafka topics. They won't have data until:
1. Events are published to Kafka topics, OR
2. Historical data exists in PostgreSQL

### Generate Sample E-Commerce Traffic

```bash
# Option 1: Use the user simulator
python scripts/simulate-users.py --duration 300 --rate 10

# This will:
# - Simulate 10 users/second for 5 minutes
# - Generate order, payment, cart, inventory events
# - Publish to Kafka topics
```

### Option 2: Run the Complete Workflow Test

```bash
# This tests the entire system and generates sample data
./scripts/test-complete-workflow.sh

# This will:
# - Create test orders
# - Process payments
# - Update inventory
# - Generate events
```

---

## Step 4: Monitor Data Flow

### Check if Data is Being Processed

```bash
# 1. Check if events are in Kafka
docker exec kafka-ui curl -X GET http://kafka-ui:8080/api/clusters/1/topics/orders/partitions

# 2. Check if PostgreSQL analytics tables have data
docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM revenue_metrics;"
docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM fraud_alerts;"
docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM cart_abandonment;"

# 3. Check if metrics exporter is reading data
curl -s http://localhost:9097/metrics | grep spark_revenue_total_24h

# Expected output after data flows:
# spark_revenue_total_24h{service="spark-analytics"} 12345.67
```

### Monitor Spark Jobs

```bash
# Check job status
./scripts/spark/monitor-spark-jobs.sh

# Check Spark Master UI
# http://localhost:9080

# Check Spark Driver UI (when running)
# http://localhost:4040
```

### Monitor Metrics Exporter

```bash
# Check logs
docker logs -f spark-metrics-exporter

# Expected output every 30 seconds:
# Successfully updated all metrics
```

---

## Step 5: View Data in Dashboard

Once data is flowing:

```
1. Open http://localhost:3000
2. Navigate to Spark Analytics Dashboard
3. You'll see live metrics updating every 30 seconds:
   - Revenue metrics: 24h totals, trends, per-minute rate
   - Fraud alerts: Total alerts, by type, rate/hour
   - Inventory: Units sold, top products
   - Cart abandonment: Abandoned count, abandonment rate
   - Job operations: Success/failure counts, duration trends
```

---

## Complete Testing Timeline

### Timeline for Full Data Population

```
T+0s:   Start Spark jobs
T+5s:   Jobs connect to Kafka and PostgreSQL
T+10s:  First events are consumed from Kafka
T+30s:  Metrics exporter updates (reads ~0 data first run)
T+60s:  Metrics exporter updates again (should see data now)
T+90s:  Dashboard refreshes (30s + 60s latency)
T+120s: Full data visible in dashboard with trends

Total: ~2 minutes from job start to dashboard populated
```

### Expected Metrics Over Time

**After 1 minute:**
- Revenue: > 0 (if orders were processed)
- Order count: > 0
- Fraud alerts: 0-N (depends on test data)
- Cart abandonment: 0-N
- Job success: 5 (all jobs running successfully)

**After 5 minutes:**
- Revenue: Significant value (many orders processed)
- Trends visible in time series charts
- Top products ranked by units and revenue
- Fraud patterns emerging

**After 30 minutes:**
- Full 24h window of data
- Multiple completed job cycles
- Clear patterns and trends
- All dashboard panels fully populated

---

## Testing Checklist

- [ ] Spark cluster running: `docker ps | grep spark`
- [ ] Metrics exporter running: `docker logs spark-metrics-exporter`
- [ ] Prometheus scraping: `http://localhost:9090/targets`
- [ ] Grafana accessible: `http://localhost:3000`
- [ ] Dashboard exists: `http://localhost:3000/d/spark-analytics-dashboard`
- [ ] Spark jobs started: `./scripts/spark/start-spark-jobs.sh`
- [ ] Test data generated: `python scripts/simulate-users.py`
- [ ] PostgreSQL has data: `docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM revenue_metrics;"`
- [ ] Metrics exporter reading data: `curl -s http://localhost:9097/metrics | grep spark_revenue`
- [ ] Prometheus has metrics: `http://localhost:9090/graph?query=spark_revenue_total_24h`
- [ ] Dashboard shows data: `http://localhost:3000/d/spark-analytics-dashboard`

---

## Quick Commands Reference

```bash
# Start everything
docker-compose up -d
./scripts/spark/start-spark-jobs.sh
python scripts/simulate-users.py

# Monitor
./scripts/spark/monitor-spark-jobs.sh
docker logs -f spark-metrics-exporter
curl http://localhost:9097/metrics | grep spark_

# View dashboard
open http://localhost:3000/d/spark-analytics-dashboard

# Check data
docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT * FROM revenue_metrics LIMIT 10;"
```

---

## Troubleshooting

### Dashboard Shows No Data
1. Check if Spark jobs are running: `./scripts/spark/monitor-spark-jobs.sh`
2. Check if PostgreSQL has data: `docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM revenue_metrics;"`
3. Check metrics exporter: `curl http://localhost:9097/metrics | grep spark_`
4. Restart exporter: `docker restart spark-metrics-exporter`

### Spark Jobs Not Starting
1. Check logs: `docker logs spark-master`
2. Check disk space: Checkpoints use disk
3. Clear checkpoints: `./scripts/spark/cleanup-checkpoints.sh`
4. Restart Spark: `docker-compose restart spark-master spark-worker-1 spark-worker-2`

### No Data in PostgreSQL
1. Check if Kafka has events: `docker exec kafka-ui curl -s http://localhost:8080/api/clusters/1/topics`
2. Check Spark job logs: `docker logs spark-master | grep ERROR`
3. Restart jobs: `./scripts/spark/restart-job.sh <job-name>`

---

## Summary

**To see the Spark Analytics Dashboard with real data:**

1. ✅ **Everything is ready** - Dashboard exists, metrics exporter running
2. 🚀 **Start Spark jobs**: `./scripts/spark/start-spark-jobs.sh`
3. 📊 **Generate data**: `python scripts/simulate-users.py`
4. ⏳ **Wait 1-2 minutes** for data to flow through the system
5. 📈 **View dashboard**: `http://localhost:3000/d/spark-analytics-dashboard`

**Duration: ~2 minutes from start to full dashboard**
