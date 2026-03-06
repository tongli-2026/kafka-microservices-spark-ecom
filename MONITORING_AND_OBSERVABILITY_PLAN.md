# Monitoring and Observability Plan

## Executive Summary

This document outlines the complete plan to add monitoring and observability to the Kafka microservices e-commerce platform using Prometheus, Grafana, and custom metrics instrumentation. This includes dashboards for all 5 microservices and 5 Spark analytics jobs.

**Total Implementation Time: 5-7 days**

---

## Part 1: Architecture Overview

### Current Infrastructure (Existing)
```
docker-compose.yml services:
├── Kafka Cluster (3 brokers)
├── PostgreSQL (data storage)
├── Redis (cart caching)
├── MailHog (email testing)
└── 5 Microservices
    ├── cart-service (8001)
    ├── order-service (8002)
    ├── payment-service (8003)
    ├── inventory-service (8004)
    └── notification-service (8005)
└── Spark Cluster
    ├── spark-master (7077, UI: 9080)
    ├── spark-worker-1 (4040)
    └── spark-worker-2
```

### New Monitoring Stack (To Add)
```
Prometheus (metrics scraper)
    ↓
Grafana (visualization)
    ↑
Services expose /metrics endpoint:
├── Payment Service → prometheus_client metrics
├── Order Service → prometheus_client metrics
├── Inventory Service → prometheus_client metrics
├── Notification Service → prometheus_client metrics
├── Cart Service → prometheus_client metrics
└── Custom metrics exporter → Spark job outputs
```

---

## Part 2: Deliverables & Dashboard Contents

### Phase 1: Service Metrics & Dashboard (2-3 days)

#### 2.1 Metrics Endpoints
Each microservice will expose `/metrics` endpoint with:

**Payment Service** (`/metrics` on port 8003)
```
payment_requests_total{service="payment-service"}
payment_request_duration_seconds{service="payment-service"}
payment_processing_errors_total{service="payment-service"}
idempotency_cache_hits_total{service="payment-service"}
idempotency_cache_misses_total{service="payment-service"}
postgres_connection_pool_active{service="payment-service"}
```

**Order Service** (`/metrics` on port 8002)
```
order_requests_total{status="created|confirmed|failed"}
order_processing_duration_seconds{quantile="0.5|0.9|0.99"}
saga_orchestration_steps_total{step="payment|inventory|notification"}
saga_failures_total{step="payment|inventory|notification"}
processed_events_deduplicated{service="order-service"}
outbox_events_pending{service="order-service"}
kafka_consumer_lag_seconds{service="order-service"}
```

**Inventory Service** (`/metrics` on port 8004)
```
inventory_reservations_total{product_id="*"}
inventory_reservation_duration_seconds
inventory_failure_backpressure_total
stock_level{product_id="*"}
reservation_concurrency_gauge{product_id="*"}
```

**Notification Service** (`/metrics` on port 8005)
```
notification_requests_total{type="email|sms"}
notification_delivery_duration_seconds{type="email|sms"}
notification_failures_total{type="email|sms"}
notification_deduplication_cache_hits_total
outgoing_emails_total{status="sent|failed"}
```

**Cart Service** (`/metrics` on port 8001)
```
cart_requests_total{operation="add|remove|view|checkout"}
cart_cache_hits_total{service="cart-service"}
cart_cache_misses_total{service="cart-service"}
redis_connection_errors_total{service="cart-service"}
cart_abandonment_events_total
```

#### 2.2 Services Dashboard
**Name:** `Services Overview Dashboard`
**Location:** Grafana home page (first dashboard)
**Panels:**

1. **Health Status (Top Section)**
   - 5 status cards showing:
     - Payment Service: Last request time, avg response time
     - Order Service: Saga success rate, pending sagas count
     - Inventory Service: Current reservation queue length
     - Notification Service: Last email sent, delivery success rate
     - Cart Service: Active carts, cache hit rate

2. **Request Metrics Row**
   ```
   Panel 1: Payment Service Requests
   - Graph: requests/sec over 24 hours
   - Query: rate(payment_requests_total[1m])
   
   Panel 2: Order Service Saga Success Rate
   - Graph: % of successful sagas
   - Query: rate(saga_orchestration_steps_total{status="success"}[1m]) / rate(saga_orchestration_steps_total[1m])
   
   Panel 3: Inventory Reservations/sec
   - Graph: reservations per second
   - Query: rate(inventory_reservations_total[1m])
   
   Panel 4: Notifications Sent/sec
   - Graph: notifications/sec by type (email/sms)
   - Query: rate(notification_requests_total[1m]) by (type)
   ```

3. **Latency/Performance Row**
   ```
   Panel 1: Payment Request Latency (p50, p99)
   - Graph: histogram with percentiles
   - Query: histogram_quantile(0.99, payment_request_duration_seconds)
   
   Panel 2: Order Processing Duration
   - Graph: saga orchestration end-to-end time
   - Query: histogram_quantile(0.99, order_processing_duration_seconds)
   
   Panel 3: Inventory Reservation Latency
   - Graph: response time distribution
   - Query: histogram_quantile(0.99, inventory_reservation_duration_seconds)
   
   Panel 4: Notification Delivery Time
   - Graph: time to deliver by type
   - Query: histogram_quantile(0.99, notification_delivery_duration_seconds) by (type)
   ```

4. **Error & Reliability Row**
   ```
   Panel 1: Payment Processing Errors
   - Graph: error count over time
   - Query: rate(payment_processing_errors_total[1m])
   
   Panel 2: Saga Failures by Step
   - Graph: stacked bars for payment/inventory/notification failures
   - Query: rate(saga_failures_total[1m]) by (step)
   
   Panel 3: Notification Failures
   - Graph: failed notifications by type
   - Query: rate(notification_failures_total[1m]) by (type)
   ```

5. **Idempotency & Deduplication Row**
   ```
   Panel 1: Idempotency Cache Hit Rate
   - Gauge: % of requests hitting cache (target: > 95%)
   - Query: rate(idempotency_cache_hits_total[5m]) / (rate(idempotency_cache_hits_total[5m]) + rate(idempotency_cache_misses_total[5m]))
   
   Panel 2: Processed Events Deduplicated
   - Counter: total events deduplicated
   - Query: processed_events_deduplicated
   
   Panel 3: Notification Dedup Cache Hit Rate
   - Gauge: % of notifications deduplicated
   - Query: rate(notification_deduplication_cache_hits_total[5m])
   ```

6. **Infrastructure Row**
   ```
   Panel 1: Database Connection Pool Status
   - Gauge: active connections
   - Query: postgres_connection_pool_active
   
   Panel 2: Redis Cache Performance
   - Graph: hits vs misses
   - Query: rate(cart_cache_hits_total[1m]) vs rate(cart_cache_misses_total[1m])
   
   Panel 3: Redis Connection Errors
   - Graph: connection error rate
   - Query: rate(redis_connection_errors_total[1m])
   ```

7. **Kafka Consumer Lag**
   ```
   Panel 1: Consumer Lag by Service
   - Graph: lag in seconds for each service
   - Query: kafka_consumer_lag_seconds by (service)
   ```

---

### Phase 2: Spark Analytics Dashboard (2-3 days)

#### 2.3 Spark Metrics Exporter
Create `analytics/metrics_exporter.py`:
- Polls PostgreSQL tables created by Spark jobs every 30 seconds
- Exposes Prometheus metrics on `/metrics` endpoint (port 9090)
- Tracks:
  - Revenue metrics (total, order count, avg value)
  - Fraud alerts (by type: high_value, rapid_velocity, failed_payments, ip_based)
  - Inventory velocity (top 10 products, units sold, revenue)
  - Cart abandonment (count, avg cart value)
  - Operational metrics (job run duration, status)

#### 2.4 Spark Analytics Dashboard
**Name:** `Analytics Jobs Dashboard`
**Location:** Grafana (second dashboard)
**Panels:**

1. **Job Health Status (Top Section)**
   - 5 cards showing:
     - Revenue Streaming: Last run, total revenue/day, order count
     - Fraud Detection: Last alert count, highest severity
     - Inventory Velocity: Top product today, units sold
     - Cart Abandonment: Total abandoned, recovery rate
     - Operational Metrics: Last job run, success count

2. **Revenue Metrics Row**
   ```
   Panel 1: Total Revenue (24 hours)
   - Large number display with sparkline
   - Query: SELECT SUM(total_revenue) FROM revenue_metrics WHERE window_start > now() - interval '24 hours'
   
   Panel 2: Revenue Trend (7 days)
   - Line graph: daily revenue
   - Query: SELECT DATE(window_start), SUM(total_revenue) FROM revenue_metrics WHERE window_start > now() - interval '7 days' GROUP BY DATE(window_start)
   
   Panel 3: Order Count (24 hours)
   - Graph: orders per minute (1-min windows from Spark)
   - Query: SELECT window_start, order_count FROM revenue_metrics WHERE window_start > now() - interval '24 hours'
   
   Panel 4: Average Order Value (7 days)
   - Graph: AOV trend
   - Query: SELECT window_start, avg_order_value FROM revenue_metrics WHERE window_start > now() - interval '7 days'
   ```

3. **Fraud Detection Row**
   ```
   Panel 1: Total Fraud Alerts (24 hours)
   - Large gauge: total count
   - Query: SELECT COUNT(*) FROM fraud_alerts WHERE timestamp > now() - interval '24 hours'
   
   Panel 2: Fraud Alerts by Severity
   - Stacked bar: LOW/MEDIUM/HIGH/CRITICAL breakdown
   - Query: SELECT severity, COUNT(*) FROM fraud_alerts WHERE timestamp > now() - interval '24 hours' GROUP BY severity
   
   Panel 3: Fraud Alerts by Type
   - Pie chart: high_value, rapid_velocity, failed_payments, ip_based
   - Query: SELECT alert_type, COUNT(*) FROM fraud_alerts WHERE timestamp > now() - interval '24 hours' GROUP BY alert_type
   
   Panel 4: Fraud Alert Timeline
   - Graph: alerts per hour
   - Query: SELECT DATE_TRUNC('hour', timestamp), COUNT(*) FROM fraud_alerts WHERE timestamp > now() - interval '24 hours' GROUP BY DATE_TRUNC('hour', timestamp)
   ```

4. **Inventory Velocity Row**
   ```
   Panel 1: Top 10 Products by Units Sold (24 hours)
   - Bar chart: product_id vs units_sold
   - Query: SELECT product_id, SUM(units_sold) FROM inventory_velocity WHERE window_start > now() - interval '24 hours' GROUP BY product_id ORDER BY SUM(units_sold) DESC LIMIT 10
   
   Panel 2: Top 10 Products by Revenue (24 hours)
   - Bar chart: product_id vs revenue
   - Query: SELECT product_id, SUM(revenue) FROM inventory_velocity WHERE window_start > now() - interval '24 hours' GROUP BY product_id ORDER BY SUM(revenue) DESC LIMIT 10
   
   Panel 3: Velocity Score Distribution
   - Heat map: product_id vs velocity_score
   - Query: SELECT product_id, velocity_score FROM inventory_velocity WHERE window_start > now() - interval '24 hours'
   
   Panel 4: Inventory Velocity Trend (7 days)
   - Line graph: daily inventory value
   - Query: SELECT DATE(window_start), SUM(revenue) FROM inventory_velocity WHERE window_start > now() - interval '7 days' GROUP BY DATE(window_start)
   ```

5. **Cart Abandonment Row**
   ```
   Panel 1: Total Abandoned Carts (24 hours)
   - Large gauge
   - Query: SELECT COUNT(*) FROM cart_abandonment WHERE window_start > now() - interval '24 hours'
   
   Panel 2: Abandonment Rate
   - Percentage: abandoned / (completed + abandoned)
   - Query: SELECT COUNT(*) FILTER (WHERE status='abandoned') * 100.0 / COUNT(*) FROM cart_abandonment WHERE window_start > now() - interval '24 hours'
   
   Panel 3: Average Cart Value (Abandoned vs Completed)
   - Comparison bars
   - Query: SELECT status, AVG(cart_value) FROM cart_abandonment WHERE window_start > now() - interval '24 hours' GROUP BY status
   
   Panel 4: Cart Abandonment Trend (7 days)
   - Stacked area: abandoned vs recovered vs completed
   - Query: SELECT DATE(window_start), status, COUNT(*) FROM cart_abandonment WHERE window_start > now() - interval '7 days' GROUP BY DATE(window_start), status
   ```

6. **Operational Metrics Row**
   ```
   Panel 1: Spark Job Execution Status
   - Table: job_name, last_run_time, duration, status (success/failure)
   - Query: SELECT job_name, MAX(execution_time), status FROM operational_metrics GROUP BY job_name, status ORDER BY MAX(execution_time)
   
   Panel 2: Job Duration Trend (7 days)
   - Line graph: execution time over time per job
   - Query: SELECT execution_time, duration FROM operational_metrics WHERE execution_time > now() - interval '7 days'
   
   Panel 3: Job Success Rate
   - Gauge for each job (target: 100%)
   - Query: SELECT job_name, (COUNT(*) FILTER (WHERE status='success')) * 100.0 / COUNT(*) FROM operational_metrics GROUP BY job_name
   
   Panel 4: Records Processed (24 hours)
   - Stacked bar: by job type
   - Query: SELECT job_name, SUM(records_processed) FROM operational_metrics WHERE execution_time > now() - interval '24 hours' GROUP BY job_name
   ```

---

## Part 3: Implementation Breakdown

### Phase 1: Add Prometheus & Grafana to docker-compose.yml (0.5 days)

**Changes to make:**
1. Add Prometheus service that scrapes `/metrics` from all services
2. Add Grafana service connected to Prometheus
3. Update all microservice Dockerfiles to install `prometheus-client` package

**Files to create:**
- `monitoring/prometheus.yml` - Prometheus configuration
- `monitoring/prometheus.Dockerfile` - Custom Prometheus image with config
- `monitoring/grafana.Dockerfile` - Custom Grafana image with data sources
- `monitoring/entrypoint.sh` - Script to initialize Grafana datasources

**Time estimate: 1 day**

---

### Phase 2: Instrument Microservices (1-2 days)

**For each microservice (payment, order, inventory, notification, cart):**

1. **Modify main.py/fastapi app:**
   ```python
   from prometheus_client import Counter, Histogram, Gauge, generate_latest
   from fastapi import FastAPI
   from fastapi.responses import Response
   
   # Initialize metrics
   request_count = Counter('service_requests_total', 'Total requests', ['service', 'method', 'endpoint'])
   request_duration = Histogram('service_request_duration_seconds', 'Request duration', ['service', 'endpoint'])
   
   app = FastAPI()
   
   @app.middleware("http")
   async def add_metrics(request, call_next):
       # Record metrics before and after request
       ...
   
   @app.get("/metrics")
   async def metrics():
       return Response(generate_latest(), media_type="text/plain")
   ```

2. **Add service-specific metrics:**
   - Payment: idempotency cache hits/misses, processing errors
   - Order: saga step counters, processed events dedup
   - Inventory: reservation queue length, backpressure
   - Notification: dedup cache, delivery success rate
   - Cart: cache performance, redis connection errors

3. **Update requirements.txt:**
   ```
   prometheus-client>=0.17.0
   ```

4. **Modify Dockerfile:**
   ```dockerfile
   RUN pip install prometheus-client
   ```

**Time estimate: 1-2 days**

---

### Phase 3: Create Spark Metrics Exporter (1 day)

**Create new file:** `analytics/metrics_exporter.py`

```python
"""
Prometheus metrics exporter for Spark job outputs.
Polls PostgreSQL tables and exposes as /metrics endpoint.
"""

from prometheus_client import Counter, Gauge, Histogram, start_http_server
from datetime import datetime, timedelta
import psycopg2
import logging
import time

# Revenue metrics
revenue_total = Gauge('spark_revenue_total', 'Total revenue in 24h', ['period'])
order_count_total = Gauge('spark_order_count_total', 'Total orders in 24h', ['period'])
avg_order_value = Gauge('spark_avg_order_value', 'Average order value', ['period'])

# Fraud metrics
fraud_alerts_total = Gauge('spark_fraud_alerts_total', 'Total fraud alerts', ['severity'])
fraud_by_type = Gauge('spark_fraud_by_type_total', 'Fraud alerts by type', ['alert_type'])

# Inventory metrics
top_product_units = Gauge('spark_top_product_units_sold', 'Units sold for top products', ['product_id'])
top_product_revenue = Gauge('spark_top_product_revenue', 'Revenue for top products', ['product_id'])

# Cart metrics
abandoned_carts_total = Gauge('spark_abandoned_carts_total', 'Total abandoned carts', ['period'])
cart_abandonment_rate = Gauge('spark_cart_abandonment_rate', 'Cart abandonment rate', ['period'])

# Operational metrics
spark_job_duration = Histogram('spark_job_duration_seconds', 'Job execution duration', ['job_name'])
spark_job_success = Gauge('spark_job_success_total', 'Successful job runs', ['job_name'])
spark_job_failure = Gauge('spark_job_failure_total', 'Failed job runs', ['job_name'])

def fetch_and_update_metrics():
    """Query PostgreSQL and update metrics every 30 seconds."""
    conn = psycopg2.connect("dbname=kafka_ecom user=postgres password=postgres host=postgres")
    
    while True:
        try:
            cursor = conn.cursor()
            
            # Update revenue metrics
            cursor.execute("""
                SELECT SUM(total_revenue), SUM(order_count), AVG(avg_order_value)
                FROM revenue_metrics 
                WHERE window_start > now() - interval '24 hours'
            """)
            total_rev, order_cnt, avg_val = cursor.fetchone()
            revenue_total.labels(period='24h').set(total_rev or 0)
            order_count_total.labels(period='24h').set(order_cnt or 0)
            avg_order_value.labels(period='24h').set(avg_val or 0)
            
            # Update fraud metrics
            cursor.execute("""
                SELECT severity, COUNT(*) FROM fraud_alerts 
                WHERE timestamp > now() - interval '24 hours'
                GROUP BY severity
            """)
            for severity, count in cursor.fetchall():
                fraud_alerts_total.labels(severity=severity).set(count)
            
            # Update inventory metrics (top 10)
            cursor.execute("""
                SELECT product_id, SUM(units_sold), SUM(revenue)
                FROM inventory_velocity
                WHERE window_start > now() - interval '24 hours'
                GROUP BY product_id
                ORDER BY SUM(units_sold) DESC
                LIMIT 10
            """)
            for product_id, units, revenue in cursor.fetchall():
                top_product_units.labels(product_id=product_id).set(units)
                top_product_revenue.labels(product_id=product_id).set(revenue)
            
            # Update cart metrics
            cursor.execute("""
                SELECT COUNT(*), AVG(cart_value)
                FROM cart_abandonment
                WHERE window_start > now() - interval '24 hours'
                AND status = 'abandoned'
            """)
            abandoned_cnt, avg_cart_val = cursor.fetchone()
            abandoned_carts_total.labels(period='24h').set(abandoned_cnt or 0)
            
            cursor.close()
        except Exception as e:
            logging.error(f"Error updating metrics: {e}")
        
        time.sleep(30)  # Update every 30 seconds

if __name__ == "__main__":
    start_http_server(9090)  # Expose on port 9090
    fetch_and_update_metrics()
```

**Update docker-compose.yml:**
```yaml
spark-metrics-exporter:
  build:
    context: .
    dockerfile: analytics/Dockerfile.exporter
  container_name: spark-metrics-exporter
  ports:
    - "9090:9090"
  depends_on:
    - postgres
  environment:
    - POSTGRES_HOST=postgres
    - POSTGRES_DB=kafka_ecom
    - POSTGRES_USER=postgres
    - POSTGRES_PASSWORD=postgres
  networks:
    - kafka-network
```

**Time estimate: 1 day**

---

### Phase 4: Create Grafana Dashboards (1-2 days)

**Deliverables:**
1. `monitoring/dashboards/services-overview.json` - Services dashboard (40 panels)
2. `monitoring/dashboards/spark-analytics.json` - Analytics dashboard (25 panels)
3. `monitoring/dashboards/kafka-topics.json` - Kafka monitoring (15 panels, optional)

**Tools:**
- Manually create in Grafana UI, then export as JSON
- OR generate JSON programmatically using Python

**Time estimate: 1-2 days**

---

## Part 4: Detailed Timeline & Effort

| Phase | Task | Files | Time | Status |
|-------|------|-------|------|--------|
| **1** | Prometheus + Grafana setup | docker-compose.yml, prometheus.yml | 0.5 days | Ready |
| **1** | Add to docker-compose | monitoring/Dockerfile | 0.5 days | Ready |
| **2.1** | Payment service metrics | services/payment-service/main.py | 3 hours | To Do |
| **2.2** | Order service metrics | services/order-service/main.py | 3 hours | To Do |
| **2.3** | Inventory service metrics | services/inventory-service/main.py | 3 hours | To Do |
| **2.4** | Notification service metrics | services/notification-service/main.py | 3 hours | To Do |
| **2.5** | Cart service metrics | services/cart-service/main.py | 3 hours | To Do |
| **3** | Spark metrics exporter | analytics/metrics_exporter.py | 1 day | To Do |
| **4.1** | Services dashboard | monitoring/dashboards/services-overview.json | 1 day | To Do |
| **4.2** | Spark dashboard | monitoring/dashboards/spark-analytics.json | 1 day | To Do |
| **5** | Testing & validation | test-monitoring.sh | 0.5 days | To Do |
| | **TOTAL** | | **5-7 days** | |

---

## Part 5: Success Criteria

After implementation, you will be able to:

✅ **Service Monitoring:**
- View real-time request rates for each service
- Track saga orchestration success rates
- Monitor idempotency cache hit rates (should be > 95%)
- See request latency (p50, p90, p99)
- Alert when error rate exceeds threshold (e.g., > 1%)

✅ **Analytics Monitoring:**
- Dashboard showing 24-hour revenue total
- Fraud alert count and severity breakdown
- Top 10 products by units sold
- Cart abandonment rate and recovery
- Spark job execution status and duration

✅ **Business Metrics:**
- Revenue trend over 7 days
- Order count per minute
- Fraud detection effectiveness (alerts per day)
- Inventory velocity insights
- Cart recovery opportunities

✅ **Infrastructure Health:**
- Database connection pool status
- Redis cache hit rate
- Kafka consumer lag per service
- Spark job resource utilization

---

## Part 6: Access Information

### Grafana
- **URL:** http://localhost:3000
- **Default User:** admin
- **Default Password:** admin
- **Dashboards:**
  - Services Overview: http://localhost:3000/d/services-overview
  - Spark Analytics: http://localhost:3000/d/spark-analytics

### Prometheus
- **URL:** http://localhost:9090
- **Metrics Explorer:** http://localhost:9090/graph

### Data Sources
- **Prometheus:** http://prometheus:9090
- **PostgreSQL:** postgres:5432

---

## Part 7: Maintenance & Future Enhancements

### Alerts to Add (Phase 2)
```yaml
alerts:
  - name: HighPaymentErrorRate
    condition: rate(payment_processing_errors_total[5m]) > 0.01
    action: send_to_slack
  
  - name: SagaFailed
    condition: rate(saga_failures_total[5m]) > 0
    action: send_to_email
  
  - name: FraudSpikeDetected
    condition: rate(spark_fraud_alerts_total[5m]) > 10
    action: page_oncall
```

### Dashboard Improvements (Phase 3)
- Add drill-down to individual product details
- Create heatmaps for time-of-day analysis
- Add correlations (fraud vs cart abandonment)
- Custom alerting rules UI

---

## How to Use This Plan

1. **Week 1, Days 1-2:** Set up Prometheus + Grafana in docker-compose
2. **Week 1, Days 2-4:** Instrument all 5 microservices
3. **Week 1, Days 4-5:** Create Spark metrics exporter
4. **Week 1, Days 5-6:** Build Grafana dashboards
5. **Week 1, Day 7:** Test, validate, and document

---

## Questions to Consider

1. **Do you want email alerts** when errors spike?
2. **Should Grafana auto-refresh dashboards** (every 5s, 30s, or 1m)?
3. **Do you need historical data retention?** (default 15 days in Prometheus)
4. **Do you want to track custom business metrics** (e.g., customer lifetime value)?

---

## Next Steps

Pick your preferred approach:

**Option A: I create the complete implementation**
- Create docker-compose with Prometheus + Grafana
- Create metrics exporter for Spark jobs
- Provide code templates for each service's metrics
- Deliver all 2 dashboards as JSON files
- Expected time: You provide code, I implement metrics = 3-4 days

**Option B: I guide you step-by-step**
- I create Prometheus + Grafana setup
- I show you how to add metrics to one service as example
- You replicate to other 4 services
- I review and help with dashboard creation
- Expected time: 1 week with your active participation

**Option C: Minimal MVP approach**
- Add just Prometheus + Grafana (no custom metrics yet)
- Create basic dashboard with system metrics only
- You can add service metrics later as needed
- Expected time: 2-3 days

Which approach works best for your timeline?
