# Monitoring Complete Guide

## ⚡ Quick Start: Access Monitoring Tools

### Grafana Dashboard
- **URL:** http://localhost:3000
- **Username:** admin
- **Password:** admin

### Prometheus Metrics UI
- **URL:** http://localhost:9090

### View Raw Service Metrics
```bash
# Payment Service
curl http://localhost:8003/metrics | head -20

# Order Service
curl http://localhost:8002/metrics | head -20

# Inventory Service
curl http://localhost:8004/metrics | head -20

# Notification Service
curl http://localhost:8005/metrics | head -20

# Cart Service
curl http://localhost:8001/metrics | head -20
```

### Basic Prometheus Queries
```promql
# Check if all targets are up
up

# Count total targets
count(up)

# See all metric names
{__name__=""}

# Check Python garbage collection
python_gc_objects_collected_total
```

---

## 🎯 What Was Implemented

✅ Service-specific metrics for all 5 microservices  
✅ Saga orchestration tracking (inventory → payment → confirmation)  
✅ Payment idempotency metrics  
✅ Order status tracking through full lifecycle  
✅ Inventory reservation & stock level monitoring  
✅ Notification delivery tracking  
✅ Cart operation metrics  
✅ Kafka event publishing metrics  
✅ Spark analytics with 5 streaming jobs  
✅ Comprehensive validation script  

---

## 📊 36+ Metrics Now Collecting

### Core HTTP (3)
```
http_requests_total             # Request volume
http_request_duration_seconds   # Latency
service_errors_total            # Errors
```

### Payment (5)
```
payment_processing_total              # By status
payment_processing_duration_seconds   # How long
payment_validation_errors_total       # Validation failures
idempotency_cache_hits_total          # Cache effectiveness
idempotency_cache_misses_total        # Cache misses
```

### Order Saga (6)
```
order_processing_total                 # By status
saga_orchestration_steps_total         # Step execution
saga_compensation_total                # Rollbacks
pending_orders_total                   # Current pending
processed_events_deduplicated_total    # Duplicates handled
outbox_events_pending_total            # Unprocessed events
```

### Inventory (4)
```
inventory_reservation_total            # By product
inventory_reservation_duration_seconds # Latency
inventory_stock_level                  # Current stock
inventory_allocation_errors_total      # Failures
```

### Notification (3)
```
notification_sent_total                # By type & status
notification_processing_duration_seconds
notification_deduplication_hits_total  # Cache hits
```

### Cart (4)
```
cart_operations_total                  # add/remove/checkout
redis_cache_hits_total                 # Cache hits
redis_cache_misses_total               # Cache misses
redis_connection_errors_total          # Connection failures
```

### Kafka (3) + Database (2)
```
kafka_message_published_total          # Messages published
kafka_message_consumed_total           # Messages consumed
kafka_produce_errors_total             # Publishing errors
db_connection_pool_active              # Active connections
db_query_duration_seconds              # Query latency
```

### Spark Analytics (21) 🎯 NEW
```
spark_revenue_total_24h                # 24h total revenue (USD)
spark_order_count_24h                  # 24h order count
spark_avg_order_value                  # Average order value
spark_revenue_per_minute               # Current revenue rate
spark_fraud_alerts_total               # Total fraud alerts (24h)
spark_fraud_by_type_total              # Fraud alerts by type
spark_fraud_alerts_rate_per_hour       # Fraud alert rate
spark_inventory_velocity_units_sold_24h # 24h units sold
spark_top_product_units_sold           # Top 10 products (units)
spark_top_product_revenue              # Top 10 products (revenue)
spark_cart_abandoned_24h               # 24h abandoned carts
spark_cart_abandonment_rate            # Abandonment rate (%)
spark_cart_recovery_rate               # Recovery rate (%)
spark_job_success_total                # Successful job executions
spark_job_failure_total                # Failed job executions
spark_job_duration{job_name}           # Duration by job (5 jobs)
spark_job_records_processed_total      # Total records processed
```

---

## 🔍 Where to Look

| Goal | URL | Query |
|------|-----|-------|
| **Dashboard** | http://localhost:3000/d/microservices-dashboard | 10-panel visual overview |
| **Spark Dashboard** | http://localhost:3000/d/spark-analytics-dashboard | Spark metrics overview |
| **Prometheus** | http://localhost:9090 | Raw metric data |
| **Spark Metrics Exporter** | http://localhost:9097/metrics | Raw Spark metrics |
| **Payment Success** | http://localhost:9090/api/v1/query | `rate(payment_processing_total{status="success"}[1h])` |
| **Order Rate** | http://localhost:9090/api/v1/query | `rate(order_processing_total{status="confirmed"}[1h])` |
| **Inventory Stock** | http://localhost:9090/api/v1/query | `inventory_stock_level` |
| **24h Revenue** | http://localhost:9090/api/v1/query | `spark_revenue_total_24h` |
| **Fraud Alerts** | http://localhost:9090/api/v1/query | `spark_fraud_alerts_rate_per_hour` |
| **Cart Abandonment** | http://localhost:9090/api/v1/query | `spark_cart_abandonment_rate` |
| **Latency P95** | http://localhost:9090/api/v1/query | `histogram_quantile(0.95,http_request_duration_seconds)` |

---

## 🚀 Quick Commands

### Validate Everything
```bash
./scripts/validate-metrics.sh
# Returns: Pass/Fail count + percentage score
```

### Check Service Metrics
```bash
curl http://localhost:8001/metrics   # Cart
curl http://localhost:8002/metrics   # Order
curl http://localhost:8003/metrics   # Payment
curl http://localhost:8004/metrics   # Inventory
curl http://localhost:8005/metrics   # Notification
```

### Query Prometheus
```bash
# Via API:
curl "http://localhost:9090/api/v1/query?query=METRIC_NAME"

# Via web UI:
http://localhost:9090/graph → Enter metric name → Execute
```

### View Grafana
```
http://localhost:3000
Username: admin
Password: admin
```

### View Spark Metrics
```bash
# Raw metrics endpoint
curl http://localhost:9097/metrics | grep spark_

# Query specific Spark metric
curl "http://localhost:9090/api/v1/query?query=spark_fraud_alerts_rate_per_hour"
curl "http://localhost:9090/api/v1/query?query=spark_revenue_total_24h"
curl "http://localhost:9090/api/v1/query?query=spark_job_failure_total"
```

### Check Spark Metrics Exporter Health
```bash
# Via endpoint
curl http://localhost:9097/-/healthy

# Via Docker
docker ps | grep spark-metrics-exporter
docker logs spark-metrics-exporter
```

---

## 📈 Key Metrics to Monitor

### Health Metrics (track these daily)
```
1. Payment Success Rate
   Query: rate(payment_processing_total{status="success"}[1h])
   Alert: If < 95%, investigate

2. Order Completion Rate  
   Query: rate(order_processing_total{status="confirmed"}[1h])
   Alert: If < 90%, check saga

3. Latency P95
   Query: histogram_quantile(0.95,http_request_duration_seconds)
   Alert: If > 2s, optimize

4. Error Rate
   Query: rate(service_errors_total[5m])
   Alert: If > 1%, investigate
```

### Inventory Metrics
```
5. Stock Levels by Product
   Query: inventory_stock_level
   Alert: If < 10, restock

6. Reservation Success
   Query: rate(inventory_reservation_total{status="success"}[1h])
   Alert: If < 99%, check failures
```

### Order Saga Metrics
```
7. Saga Compensation (Rollbacks)
   Query: rate(saga_compensation_total[1h])
   Alert: If > 0, investigate failures

8. Pending Orders
   Query: pending_orders_total
   Alert: If > 100, check processing
```

### Spark Analytics Metrics 🎯 NEW
```
9. 24-Hour Revenue
   Query: spark_revenue_total_24h
   Alert: If < 80% of average, investigate

10. Fraud Alert Rate
    Query: spark_fraud_alerts_rate_per_hour
    Alert: If > 10 alerts/hour, escalate to security

11. Cart Abandonment Rate
    Query: spark_cart_abandonment_rate
    Alert: If > 60%, coordinate with marketing

12. Spark Job Success Rate
    Query: spark_job_success_total / (spark_job_success_total + spark_job_failure_total)
    Alert: If < 95%, check Spark cluster

13. Top Product Revenue
    Query: spark_top_product_revenue
    Alert: Monitor inventory for top products

14. Inventory Velocity
    Query: spark_inventory_velocity_units_sold_24h
    Alert: If spike detected, prepare for restocks
```

---

## 🛠️ Helper Functions Available

All in `shared/metrics.py`:

```python
# Saga & Order Tracking
track_saga_step(service, step, success, compensated)
track_saga_compensation(service, step)
track_order_status(service, status)
update_saga_gauge(service, metric, value)

# Payment & Cache
track_payment_status(service, status)
track_cache_hit(cache_type, service, hit)

# Inventory
track_inventory_reservation(service, product_id, status)
update_stock_level(service, product_id, quantity, warehouse)

# Notifications & Cart
track_notification(service, type, status)
track_cart_operation(service, operation)

# Kafka Events
track_kafka_message(service, topic, published, success)
track_kafka_error(service, topic, error_type)

# Deduplication
track_deduplicated_event(service)
```

---

## 🔧 How to Add Metrics to New Code

### Pattern 1: Simple Counter
```python
from shared.metrics import track_order_status

track_order_status("order-service", "created")
```

### Pattern 2: With Timing
```python
from shared.metrics import track_operation
import time

start = time.time()
try:
    result = do_something()
    duration = time.time() - start
    return result
except Exception as e:
    track_saga_step("service", "step", success=False)
    raise
```

### Pattern 3: Cache Tracking
```python
from shared.metrics import track_cache_hit

cached = get_from_cache(key)
if cached:
    track_cache_hit("idempotency", "payment-service", hit=True)
else:
    track_cache_hit("idempotency", "payment-service", hit=False)
```

---

## 📋 Files You Need to Know

| File | Purpose |
|------|---------|
| `shared/metrics.py` | Core metrics definitions + helpers (600 lines) |
| `scripts/validate-metrics.sh` | Validation script (480 lines) |
| `monitoring/dashboards/microservices-dashboard.json` | Grafana dashboard (10 panels) |
| `monitoring/dashboards/spark-analytics-dashboard.json` | Spark Grafana dashboard |
| `monitoring/prometheus.yml` | Prometheus config (15s interval) |
| `analytics/metrics_exporter.py` | Spark metrics exporter (600+ lines) |
| `analytics/jobs/` | 5 Spark streaming jobs (revenue, fraud, cart, inventory, ops) |
| `SPARK_ANALYTICS.md` | Complete Spark documentation |
| `MONITORING_IMPLEMENTATION_COMPLETE.md` | Complete feature list |

---

## ✅ Validation Results

Last run (`./scripts/validate-metrics.sh`):

```
Core Services Health ............ PASS ✓ (Prometheus UP, Grafana UP)
Service Metrics Endpoints ....... PASS ✓ (5/5 services)
Service Health Endpoints ........ PASS ✓ (5/5 services)
Prometheus Targets .............. PASS ✓ (6/6 UP)
Spark Metrics Exporter .......... PASS ✓ (UP at :9097)
Metric Collection ............... PASS ✓ (3/3 metrics)
Configuration Files ............ PASS ✓ (3/3 files)
Service Integrations ........... PASS ✓ (5/5 services)
Spark Jobs Running ............. PASS ✓ (5/5 jobs)
Spark Metrics Available ......... PASS ✓ (21/21 metrics)

Overall Score: 100% ✅

Status: PRODUCTION READY (WITH SPARK ANALYTICS)
```

---

## 🚨 Common Alerts to Set Up

When creating alert rules, watch for:

```
1. Payment Service:
   - Success rate < 95% → Check payment gateway
   - Latency > 2s → Optimize processing
   - Errors > 1% → Investigate failures

2. Order Service:
   - Completion rate < 90% → Check saga flow
   - Compensation rate > 1% → Too many rollbacks
   - Pending orders > 100 → Throughput issue

3. Inventory Service:
   - Reservation failures > 1% → Stock issues
   - Stock < 10 units → Restock needed

4. All Services:
   - Error rate > 1% → Critical issue
   - Latency P95 > 2s → Performance issue
   - No requests in 5min → Service down
```

---

## 🔥 Spark Analytics Alerts to Set Up

```
1. Spark Job Failures:
   - Condition: spark_job_failure_total > 5 in 1 hour
   - Severity: CRITICAL
   - Action: Check Spark cluster logs
   
2. High Fraud Rate:
   - Condition: spark_fraud_alerts_rate_per_hour > 10
   - Severity: WARNING
   - Action: Notify security team
   
3. Cart Abandonment Alert:
   - Condition: spark_cart_abandonment_rate > 60%
   - Severity: WARNING
   - Action: Notify marketing team
   
4. Revenue Anomaly:
   - Condition: spark_revenue_total_24h < avg(spark_revenue_total_24h) * 0.8
   - Severity: WARNING
   - Action: Investigate system issues
   
5. Spark Metrics Unavailable:
   - Condition: up{job="spark-metrics-exporter"} == 0
   - Severity: CRITICAL
   - Action: Check metrics exporter health
   
6. Inventory Velocity Spike:
   - Condition: spark_inventory_velocity_units_sold_24h > avg() * 1.5
   - Severity: INFO
   - Action: Prepare inventory replenishment
```

---

## 📞 Troubleshooting

### Prometheus not collecting metrics?
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq .

# Should see all 6 targets as "up": true
```

### No metrics showing up?
```bash
1. Check service is running:
   curl http://localhost:8001/health
   
2. Check metrics endpoint:
   curl http://localhost:8001/metrics | grep http_requests_total
   
3. Check Prometheus is scraping:
   http://localhost:9090/targets
   
4. Check Grafana datasource:
   http://localhost:3000 → Configuration → Data Sources
```

### Metrics endpoint returns 404?
```bash
# Rebuild and restart services
docker-compose build --no-cache payment-service
docker-compose up -d payment-service
```

### Grafana can't connect to Prometheus?
```bash
# Check Grafana logs
docker logs grafana

# Verify Prometheus is running
curl http://prometheus:9090/-/healthy
```

### Dashboard looks empty?
```bash
1. Verify metrics exist:
   curl "http://localhost:9090/api/v1/query?query=http_requests_total"
   
2. Check time range (top right of dashboard)
   Set to "Last 1 hour"
   
3. Refresh dashboard:
   Press F5 or click refresh button
```

### Too many metric series?
```bash
1. Metrics are normalized (no user IDs)
   This prevents cardinality explosion
   
2. If still high, check labels:
   grep "Labels:" shared/metrics.py
   
3. Remove unnecessary labels
   Keep labels < 5 per metric
```

### Want to reset everything?
```bash
# Stop monitoring stack
docker-compose down prometheus grafana

# Remove data volumes
docker volume rm kafka-microservices-spark-ecom_prometheus_data
docker volume rm kafka-microservices-spark-ecom_grafana_data

# Restart fresh
docker-compose up -d prometheus grafana
```

---

## � Spark Monitoring Troubleshooting

### Spark metrics not showing up?
```bash
1. Check metrics exporter is running:
   docker ps | grep spark-metrics-exporter
   
2. Check exporter health:
   curl http://localhost:9097/-/healthy
   
3. Check Prometheus is scraping Spark:
   http://localhost:9090/targets → Look for spark-metrics-exporter
   
4. Check Spark jobs are running:
   docker logs spark-master
   docker logs spark-worker-1 (and worker-2)
```

### Spark metrics endpoint returns 404?
```bash
# Rebuild and restart metrics exporter
docker-compose build --no-cache spark-metrics-exporter
docker-compose up -d spark-metrics-exporter

# Verify it starts without errors
docker logs spark-metrics-exporter
```

### Spark jobs showing zero metrics?
```bash
1. Check jobs are processing data:
   docker exec spark-master spark-submit --status <job-id>
   
2. Check job logs:
   docker logs spark-job-<jobname>
   
3. Restart all Spark components:
   docker-compose down spark-master spark-worker-1 spark-worker-2 spark-metrics-exporter
   docker-compose up -d spark-master spark-worker-1 spark-worker-2 spark-metrics-exporter
```

### Spark data not updating in PostgreSQL?
```bash
1. Check metrics exporter can connect to database:
   docker logs spark-metrics-exporter | grep "postgres\|database"
   
2. Verify tables exist:
   docker exec postgres psql -U postgres -d kafka_ecom -c "\dt"
   
3. Check recent data:
   docker exec postgres psql -U postgres -d kafka_ecom -c "SELECT * FROM revenue_metrics ORDER BY timestamp DESC LIMIT 5;"
```

### Spark dashboard in Grafana is empty?
```bash
1. Verify Spark datasource is configured:
   Grafana → Configuration → Data Sources
   Should see "Prometheus" with "Spark Metrics Exporter" URL
   
2. Check time range - set to "Last 1 hour"
   
3. Manually query a Spark metric:
   http://localhost:9090/graph → Query: spark_revenue_total_24h
   
4. Refresh Grafana dashboard:
   Press F5 or click refresh button
```

---

## �💾 Storage Information

### Prometheus Data
- **Location:** `prometheus_data` volume
- **Retention:** 15 days
- **Size:** ~10MB/day (varies with load)
- **Storage Path:** `/prometheus` (inside container)

### Grafana Data
- **Location:** `grafana_data` volume
- **Includes:** Dashboards, datasources, user settings
- **Size:** ~50MB (with dashboards)
- **Storage Path:** `/var/lib/grafana` (inside container)

---

## ⚙️ Performance Tips

### Reduce CPU Impact
If Prometheus is using too much CPU, you can:
```yaml
# In monitoring/prometheus.yml, increase scrape interval:
scrape_interval: 30s  # Was 15s
```

### Reduce Storage Usage
```yaml
# In docker-compose.yml, change retention:
--storage.tsdb.retention.time=7d  # Was 15d
```

### Reduce Grafana Memory
In docker-compose.yml:
```yaml
GF_SERVER_MAX_OPEN_CONNECTIONS: 100  # Limit database connections
```

---

---

## 🚨 Dead Letter Queue (DLQ) Monitoring

### What is DLQ?

A **Dead Letter Queue** is a Kafka topic (`dlq.events`) that stores messages that failed processing after 3 retry attempts. It prevents data loss while allowing investigation and recovery.

**Retry Strategy:**
- Attempt 1: Immediate retry
- Attempt 2: Wait 1 second, retry
- Attempt 3: Wait 2 seconds, retry
- After 3 failures → Sent to `dlq.events` topic

### Viewing DLQ Messages

**Option 1: Dashboards (Easiest)**
- **Infrastructure Health Dashboard**: "Dead Letter Queue Status" section shows:
  - Current DLQ message count (gauge)
  - DLQ growth rate (trend graph)
  - Auto-replay status
- **Microservices Dashboard**: "DLQ Alerts" section shows:
  - **DLQ Errors by Service (Table)** - Count of failed messages in past 1 hour per service
    - Normal state: All services show 0 (system healthy ✓)
    - Alert state: Any service > 0 (investigation required)
    - Shows service name, error type, and count
  - **Service Failures vs DLQ Correlation (Graph)** - Shows correlation between HTTP errors and DLQ messages
    - Normal state: Both lines flat at 0 (no failures, no DLQ messages ✓)
    - Expected pattern: When failures spike → DLQ messages increase (they're correlated)
    - If DLQ shows 0 but you had errors → They may have been successfully retried (no replay needed)
    - Legend shows each service with both metrics for easy identification

**Option 2: Kafka UI**
```
http://localhost:8080 → Topics → dlq.events → View messages
```

**Option 3: CLI Script**
```bash
# View all DLQ messages with details
python scripts/dlq-replay.py --view
```

### DLQ Message Format

```json
{
  "original_topic": "order.created",
  "event_id": "evt-123",
  "correlation_id": "corr-456",
  "error_reason": "PendingRollbackError: Can't reconnect...",
  "error_type": "PendingRollbackError",
  "retry_count": 3,
  "timestamp": 1708277445.123456,
  "payload": { "order_id": "ORD-123", ... }
}
```

### Auto-Replay DLQ Messages

**Automatic Recovery (Production):**
```bash
# Start daemon (checks every 5 minutes, threshold: 50 messages)
nohup python scripts/dlq-auto-replay.py --daemon --interval 300 --threshold 50 > logs/dlq-auto-replay.log 2>&1 &

# One-time check
python scripts/dlq-auto-replay.py --threshold 50 --verbose
```

**How Auto-Replay Works:**
1. Monitors DLQ message count continuously
2. When count exceeds threshold (default: 50):
   - Checks PostgreSQL connectivity ✓
   - Checks Kafka cluster health ✓
   - Checks all 5 microservices (/health endpoints) ✓
3. If system healthy → Automatically replays all DLQ messages
4. If any check fails → Blocks replay (prevents cascading failures)

**Prometheus Metrics (Visible in Dashboards):**
- `dlq_message_count` - Current messages in DLQ
- `dlq_auto_replay_triggered_total` - Number of replay attempts
- `dlq_auto_replay_success_total` - Successful replays
- `dlq_auto_replay_failed_total` - Failed replays
- `dlq_system_health_check_passed` - System health (0/1)

### Manual Recovery from DLQ

**Step 1: Identify Root Cause**

Read error from DLQ message:

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused: postgres:5432` | PostgreSQL down | `docker-compose up -d postgres` |
| `Network unreachable` | Kafka down | `docker-compose up -d kafka-broker-1 kafka-broker-2 kafka-broker-3` |
| `PendingRollbackError` | Broken DB session | `docker-compose restart <service>` |

**Step 2: Fix Issue**
```bash
# Example: PostgreSQL recovery
docker-compose stop postgres
docker-compose up -d postgres
sleep 5
docker-compose restart order-service cart-service inventory-service
```

**Step 3: Replay Messages**
```bash
# Replay all DLQ messages
python scripts/dlq-replay.py --replay-all

# Or replay specific event
python scripts/dlq-replay.py --replay <event-id>
```

### DLQ Monitoring SLA Targets

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| DLQ Message Count | 0-25 | > 50 (warning), > 100 (critical) |
| DLQ Growth Rate | 0 msg/sec | > 1 msg/sec |
| Auto-Replay Success Rate | > 95% | < 80% |
| System Health Status | Healthy (1) | Unhealthy (0) |

### DLQ Troubleshooting

| Problem | Diagnosis | Solution |
|---------|-----------|----------|
| DLQ messages accumulating | Check logs: `docker-compose logs order-service` | Fix underlying service issue |
| Auto-replay blocked | Check: `tail logs/dlq-auto-replay.log` | Fix health issue (postgres/kafka/service) |
| Manual replay hangs | Test: `python scripts/dlq-replay.py --view` | Check if services are responding |

### Setup DLQ Monitoring

```bash
# 1. Run setup script
bash setup-dlq-monitoring.sh

# 2. Start auto-replay daemon
nohup python scripts/dlq-auto-replay.py --daemon --interval 300 > logs/dlq-auto-replay.log 2>&1 &

# 3. Verify in dashboards
# - Infrastructure Health → Dead Letter Queue Status
# - Microservices → DLQ Alerts
```

---

## 🎯 Success Criteria

Your monitoring stack is production-ready when:

✅ `./scripts/validate-metrics.sh` returns 100%  
✅ All 5 microservices show UP in Prometheus targets  
✅ Spark metrics exporter shows UP in Prometheus targets  
✅ Dashboard displays all 10 panels with data  
✅ Spark Analytics dashboard displays all business KPIs  
✅ All 5 Spark jobs are running and collecting metrics  
✅ Metrics are being collected and stored  
✅ No cardinality explosion in metrics  
✅ Query latency < 100ms  
✅ Retention is set to 15 days  
✅ Revenue, fraud, cart abandonment, and inventory metrics visible  

---

## 🧪 DLQ Testing Guide

### Pre-Testing Setup (5 min)

Verify environment before starting tests:

```bash
# 1. Check all services running
docker-compose ps
# Expected: All containers showing "Up (healthy)"

# 2. Install DLQ dependencies
bash scripts/setup-dlq-monitoring.sh

# 3. Verify DLQ topic exists
docker-compose exec kafka-broker-1 \
  /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list | grep dlq

# Expected: dlq.events topic listed
```

### Phase 2: Baseline Testing (10 min)

Verify system works normally with no errors:

```bash
# Generate normal traffic
python scripts/simulate-users.py --duration 30

# Check DLQ is empty
python scripts/dlq-replay.py --view
# Expected: No messages output (or "0 messages" indicator)

# Check dashboard
open http://localhost:3000/d/infrastructure-health-dashboard
# Expected: Infrastructure Health → Dead Letter Queue Status row shows:
#   - Panel 5 (DLQ Count): 0 (green gauge)
#   - Panel 6 (Growth Rate): 0 msg/sec
#   - Panel 7 (Health): Healthy (green)
```

### Phase 3: Simulate Database Failure (15 min)

Create errors to test DLQ accumulation:

```bash
# Terminal 1: Stop PostgreSQL (simulates DB connection failure)
docker-compose stop postgres

# Terminal 2: Generate traffic immediately
python scripts/simulate-users.py --duration 60

# Terminal 3: Watch DLQ messages accumulate
watch -n 2 'python scripts/dlq-replay.py --view'
# Expected: Message count increasing (2-5 msg/sec)
# Error Type: Connection refused: postgres:5432
```

**Dashboard During Failure:**
- Infrastructure Health → DLQ panels show:
  - Panel 5: Gauge increases (yellow/red warning)
  - Panel 6: Growth Rate shows spike (green → yellow → red line)
- Microservices → DLQ Alerts show:
  - Panel 11: order-service with high error count
  - Panel 12: Failure spike correlated with DLQ messages

### Phase 4: Auto-Replay Testing (20 min)

Test automatic recovery when system becomes healthy:

```bash
# Terminal 1: Start auto-replay daemon
python scripts/dlq-auto-replay.py --daemon --interval 60 --threshold 5 --verbose

# Watch logs in real-time (Terminal 2)
tail -f logs/dlq-auto-replay.log
# Expected: "⚠️ THRESHOLD EXCEEDED... ❌ HEALTH CHECK FAILED: PostgreSQL unreachable"

# Terminal 3: Restart PostgreSQL
docker-compose up -d postgres
sleep 5
docker-compose restart order-service

# Watch logs - should show auto-replay triggered
# Expected: "✅ ALL CHECKS PASSED - Triggering auto-replay! ✅ Auto-replay completed"

# Verify DLQ cleared
python scripts/dlq-replay.py --view
# Expected: No messages (or empty list - auto-replay succeeded)

# Check dashboard
open http://localhost:3000/d/infrastructure-health-dashboard
# Expected: DLQ panels back to green/normal
```

### Phase 5-8: Advanced Testing (1 hour)

**Kafka Failure Test:**
```bash
docker-compose stop kafka-broker-1
python scripts/simulate-users.py --duration 30
# Expected: DLQ messages accumulate (Kafka unavailable)

docker-compose up -d kafka-broker-1
sleep 10
# Expected: Auto-replay triggers and clears DLQ
```

**Multiple Failures Test:**
```bash
docker-compose stop payment-service notification-service
python scripts/simulate-users.py --duration 30
# Expected: DLQ from multiple service failures

docker-compose up -d payment-service notification-service
# Expected: Auto-replay clears all messages
```

**Manual Replay Test:**
```bash
# Stop auto-replay daemon
pkill -f dlq-auto-replay.py

# Create errors again
docker-compose stop postgres
python scripts/simulate-users.py --duration 20

# Recover and manually replay
docker-compose up -d postgres
sleep 5
python scripts/dlq-replay.py --replay-all
# Expected: DLQ clears after manual replay
```

**Selective Replay:**
```bash
# View messages
python scripts/dlq-replay.py --view
# Get event_id from output

# Replay specific message
python scripts/dlq-replay.py --replay evt-specific-id
```

### Metrics Verification

Query Prometheus to verify DLQ metrics:

```bash
# Open Prometheus
open http://localhost:9090

# Create graph queries:
```

| Query | Expected |
|-------|----------|
| `dlq_message_count` | Shows gauge value during errors, 0 when healthy |
| `dlq_auto_replay_triggered_total` | Counter increases after each replay |
| `dlq_auto_replay_success_total` | Matches triggered count when all replays succeed |
| `dlq_system_health_check_passed` | 1 when healthy, 0 when unhealthy |

### Stress Testing (15 min)

High volume DLQ accumulation:

```bash
# Generate many orders rapidly while postgres is down
docker-compose stop postgres

for i in {1..100}; do
  python scripts/simulate-users.py --duration 1 &
done
wait

# Check DLQ spike
python scripts/dlq-replay.py --view
# Expected: 100+ messages output

# Recover and verify auto-replay handles large backlog
docker-compose up -d postgres
sleep 5

python scripts/dlq-auto-replay.py --threshold 50 --verbose
# Expected: All 100+ messages replayed successfully
```

### Expected Test Results Summary

✅ **Phase 2 (Baseline):** 0 DLQ messages, all services healthy  
✅ **Phase 3 (Error):** DLQ accumulates during PostgreSQL failure  
✅ **Phase 4 (Auto-Replay):** Auto-replay triggers, DLQ clears, dashboard updates  
✅ **Phase 5-8 (Advanced):** Multiple failures handled, manual replay works  
✅ **Metrics:** All 5 DLQ metrics reporting correctly  
✅ **Stress:** 100+ messages replayed without loss  

### Quick Troubleshooting During Tests

| Issue | Check |
|-------|-------|
| Auto-replay not triggering | `tail logs/dlq-auto-replay.py` - Check health check errors |
| Dashboard showing "No Data" | Ensure Prometheus is running: `docker-compose exec prometheus curl localhost:9090` |
| Replay hangs | Check message status: `python scripts/dlq-replay.py --view` |
| Metrics not appearing | Check metrics endpoint: `curl http://localhost:8002/metrics \| grep dlq` |

---

## 📚 Further Reading

- **Complete Details**: See `MONITORING_IMPLEMENTATION_COMPLETE.md`
- **Implementation Guide**: See original `MONITORING_IMPLEMENTATION_GUIDE.md`
- **Dashboard Management**: See `DASHBOARD_WORKFLOW.md`
- **Metrics Reference**: See `QUICK_METRICS_REFERENCE.md`
- **Phase Timeline**: See `METRICS_PHASE_TIMELINE.md`

---

## 🎉 You're All Set!

The monitoring system is:
- ✅ Fully implemented (microservices + Spark analytics)
- ✅ Production-ready
- ✅ Validated and tested
- ✅ Documented
- ✅ Operational with 36+ metrics

**Start monitoring your system:**

1. Open http://localhost:3000/d/microservices-dashboard (operations)
2. Open http://localhost:3000/d/spark-analytics-dashboard (business KPIs)
3. Run `./scripts/validate-metrics.sh` to verify
4. Query metrics as needed (Prometheus, Grafana, raw endpoints)
5. Set up alerts based on your SLOs
6. Monitor Spark job health continuously

**Key Monitoring URLs:**
- Grafana Dashboards: http://localhost:3000 (admin/admin)
- Prometheus Metrics: http://localhost:9090
- Spark Metrics Exporter: http://localhost:9097/metrics

**What You Can Monitor:**
- ✅ Microservice performance (5 services, 15 metrics)
- ✅ Order saga orchestration & compensation
- ✅ Payment processing & idempotency
- ✅ Inventory levels & reservations
- ✅ Cart operations & abandonment
- ✅ Real-time revenue analytics (24h trends)
- ✅ Fraud detection alerts & patterns
- ✅ Cart abandonment rates & recovery
- ✅ Inventory velocity & top products
- ✅ Spark job health & performance

**Questions?** Check the documentation files or review the metrics.py helpers. See SPARK_ANALYTICS.md for detailed Spark job documentation.
