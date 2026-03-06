# AI Agent Prompt: Implement Monitoring and Observability Stack

## Executive Brief

Implement a complete monitoring and observability stack for a Kafka-based microservices e-commerce platform using Prometheus, Grafana, and custom metrics instrumentation.

**Scope:** Add monitoring to 5 FastAPI microservices + 5 Spark analytics jobs
**Technology Stack:** Prometheus (metrics), Grafana (visualization), prometheus-client (instrumentation)
**Deployment:** Docker Compose (existing infrastructure)
**Timeline:** 5-7 days
**Deliverables:** 2 Grafana dashboards + instrumented services + metrics exporter

---

## Current Architecture

### Existing Infrastructure (Docker Compose)
- **Kafka Cluster:** 3 brokers with KafkaUI
- **PostgreSQL:** Central database for orders, payments, inventory
- **Redis:** Cart data caching
- **Microservices (FastAPI):**
  - Payment Service (port 8003)
  - Order Service (port 8002) 
  - Inventory Service (port 8004)
  - Notification Service (port 8005)
  - Cart Service (port 8001)
- **Spark Cluster:** Master + 2 workers for analytics
  - Spark Master UI: port 9080
  - Worker 1 Driver: port 4040
- **Supporting:**
  - pgAdmin (port 5050)
  - Kafka UI (port 8080)
  - MailHog (ports 1025, 8025)

### Existing Code Patterns
- Services follow saga orchestration pattern
- Order Service uses processed_events table for idempotency
- Spark jobs write aggregated metrics to PostgreSQL:
  - `revenue_metrics` (1-minute windows)
  - `fraud_alerts` (real-time)
  - `inventory_velocity` (1-hour windows)
  - `cart_abandonment` (15-minute windows)
  - `operational_metrics` (job execution logs)

---

## Part 1: Add Prometheus & Grafana to Docker Compose

### 1.1 Prometheus Service Configuration

**Create file:** `monitoring/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    monitor: 'kafka-ecom-monitor'

scrape_configs:
  # Microservices
  - job_name: 'payment-service'
    static_configs:
      - targets: ['payment-service:8003']
    metrics_path: '/metrics'

  - job_name: 'order-service'
    static_configs:
      - targets: ['order-service:8002']
    metrics_path: '/metrics'

  - job_name: 'inventory-service'
    static_configs:
      - targets: ['inventory-service:8004']
    metrics_path: '/metrics'

  - job_name: 'notification-service'
    static_configs:
      - targets: ['notification-service:8005']
    metrics_path: '/metrics'

  - job_name: 'cart-service'
    static_configs:
      - targets: ['cart-service:8001']
    metrics_path: '/metrics'

  # Spark Metrics Exporter
  - job_name: 'spark-analytics'
    static_configs:
      - targets: ['spark-metrics-exporter:9090']
    metrics_path: '/metrics'

  # Prometheus itself
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

**Create file:** `monitoring/Dockerfile.prometheus`

```dockerfile
FROM prom/prometheus:latest

COPY monitoring/prometheus.yml /etc/prometheus/prometheus.yml

EXPOSE 9090

CMD ["--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus"]
```

### 1.2 Grafana Service Configuration

**Create file:** `monitoring/Dockerfile.grafana`

```dockerfile
FROM grafana/grafana:latest

ENV GF_SECURITY_ADMIN_PASSWORD=admin
ENV GF_SECURITY_ADMIN_USER=admin
ENV GF_INSTALL_PLUGINS=grafana-piechart-panel
ENV GF_USERS_ALLOW_SIGN_UP=false

EXPOSE 3000

CMD ["bin/grafana-server"]
```

### 1.3 Update docker-compose.yml

Add these services to the existing `docker-compose.yml`:

```yaml
  prometheus:
    build:
      context: .
      dockerfile: monitoring/Dockerfile.prometheus
    container_name: prometheus
    ports:
      - "9090:9090"
    volumes:
      - prometheus_data:/prometheus
    networks:
      - kafka-network
    environment:
      - TZ=America/Los_Angeles
    depends_on:
      - payment-service
      - order-service
      - inventory-service
      - notification-service
      - cart-service
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'

  grafana:
    build:
      context: .
      dockerfile: monitoring/Dockerfile.grafana
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/provisioning:/etc/grafana/provisioning
    networks:
      - kafka-network
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_SECURITY_ADMIN_USER=admin
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
      - TZ=America/Los_Angeles
    depends_on:
      - prometheus
```

Add to the `volumes:` section at the bottom:
```yaml
  prometheus_data:
    driver: local
  grafana_data:
    driver: local
```

---

## Part 2: Instrument All 5 Microservices

### 2.1 Generic Metrics Pattern

For each service, follow this pattern:

**Update `requirements.txt`:**
```
prometheus-client>=0.17.0
```

**Update `Dockerfile`:**
```dockerfile
RUN pip install -r requirements.txt
```

**Modify service's `main.py`:**

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Request
from fastapi.responses import Response
import time
from datetime import datetime

app = FastAPI()

# ============ PROMETHEUS METRICS ============

# Generic metrics (all services have these)
request_count = Counter(
    'service_requests_total',
    'Total requests',
    ['service', 'method', 'endpoint', 'status']
)

request_duration = Histogram(
    'service_request_duration_seconds',
    'Request duration in seconds',
    ['service', 'endpoint'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

service_errors = Counter(
    'service_errors_total',
    'Total errors',
    ['service', 'error_type']
)

# Service-specific metrics (defined below per service)

# ============ MIDDLEWARE ============

@app.middleware("http")
async def add_metrics_middleware(request: Request, call_next):
    """Record metrics for all requests."""
    service_name = "payment"  # CHANGE THIS PER SERVICE
    start_time = time.time()
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        request_count.labels(
            service=service_name,
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        
        request_duration.labels(
            service=service_name,
            endpoint=request.url.path
        ).observe(duration)
        
        return response
    except Exception as e:
        duration = time.time() - start_time
        service_errors.labels(
            service=service_name,
            error_type=type(e).__name__
        ).inc()
        raise

# ============ METRICS ENDPOINT ============

@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics."""
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

# ============ REST OF YOUR ROUTES ============
# ... existing routes below ...
```

### 2.2 Payment Service Specific Metrics

**In `services/payment-service/main.py`:**

```python
# Add these imports at top
from prometheus_client import Counter, Histogram, Gauge

# Add after generic metrics section
payment_processing_errors = Counter(
    'payment_processing_errors_total',
    'Total payment processing errors',
    ['service', 'error_type']
)

payment_request_duration = Histogram(
    'payment_request_duration_seconds',
    'Payment request processing duration',
    ['service'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
)

idempotency_cache_hits = Counter(
    'idempotency_cache_hits_total',
    'Idempotency cache hits',
    ['service']
)

idempotency_cache_misses = Counter(
    'idempotency_cache_misses_total',
    'Idempotency cache misses',
    ['service']
)

# In your payment processing handler
def process_payment(order_id, amount):
    """Process payment with metrics."""
    # Check cache
    cache_key = f"payment_{order_id}"
    if cache_key in cache:
        idempotency_cache_hits.labels(service="payment-service").inc()
        return cache[cache_key]
    
    idempotency_cache_misses.labels(service="payment-service").inc()
    
    try:
        # Your payment processing logic
        result = do_payment_processing(order_id, amount)
        cache[cache_key] = result
        return result
    except Exception as e:
        payment_processing_errors.labels(
            service="payment-service",
            error_type=type(e).__name__
        ).inc()
        raise
```

### 2.3 Order Service Specific Metrics

**In `services/order-service/main.py`:**

```python
from prometheus_client import Counter, Gauge

# Saga orchestration metrics
saga_steps_total = Counter(
    'saga_orchestration_steps_total',
    'Total saga orchestration steps executed',
    ['service', 'step', 'status']  # step: payment, inventory, notification; status: success, failed
)

saga_failures = Counter(
    'saga_failures_total',
    'Total saga failures',
    ['service', 'step', 'reason']
)

pending_sagas = Gauge(
    'saga_pending_count',
    'Number of pending saga orchestrations',
    ['service']
)

processed_events_deduplicated = Counter(
    'processed_events_deduplicated',
    'Total events deduplicated via processed_events table',
    ['service']
)

# In your saga handler
async def handle_order_created(event):
    """Handle order.created event with metrics."""
    # Check if already processed (idempotency)
    if db.is_event_processed(event.event_id):
        processed_events_deduplicated.labels(service="order-service").inc()
        return
    
    try:
        # Step 1: Call payment service
        payment_response = await call_payment_service(order_id, amount)
        saga_steps_total.labels(
            service="order-service",
            step="payment",
            status="success"
        ).inc()
        
        # Step 2: Call inventory service
        inventory_response = await call_inventory_service(items)
        saga_steps_total.labels(
            service="order-service",
            step="inventory",
            status="success"
        ).inc()
        
        # Record as processed
        db.mark_event_processed(event.event_id)
        
    except PaymentServiceError as e:
        saga_failures.labels(
            service="order-service",
            step="payment",
            reason=str(e)
        ).inc()
        raise
    except Exception as e:
        saga_failures.labels(
            service="order-service",
            step="inventory",
            reason=str(e)
        ).inc()
        raise
```

### 2.4 Inventory Service Specific Metrics

**In `services/inventory-service/main.py`:**

```python
from prometheus_client import Counter, Gauge, Histogram

inventory_reservations = Counter(
    'inventory_reservations_total',
    'Total inventory reservations',
    ['service', 'status']  # status: success, failed
)

reservation_duration = Histogram(
    'inventory_reservation_duration_seconds',
    'Inventory reservation processing time',
    ['service']
)

reservation_queue_length = Gauge(
    'inventory_reservation_queue_length',
    'Current queue length for inventory reservations',
    ['service']
)

stock_level = Gauge(
    'inventory_stock_level',
    'Current stock level per product',
    ['product_id']
)

# In your reservation handler
async def reserve_inventory(order_id, items):
    """Reserve inventory with metrics."""
    start_time = time.time()
    
    try:
        # Your reservation logic
        result = process_reservation(order_id, items)
        
        duration = time.time() - start_time
        inventory_reservations.labels(
            service="inventory-service",
            status="success"
        ).inc()
        reservation_duration.labels(service="inventory-service").observe(duration)
        
        # Update stock level gauge
        for product_id, quantity in items:
            current_stock = get_stock_level(product_id)
            stock_level.labels(product_id=product_id).set(current_stock)
        
        return result
    except Exception as e:
        inventory_reservations.labels(
            service="inventory-service",
            status="failed"
        ).inc()
        raise
```

### 2.5 Notification Service Specific Metrics

**In `services/notification-service/main.py`:**

```python
from prometheus_client import Counter, Histogram

notification_requests = Counter(
    'notification_requests_total',
    'Total notification requests',
    ['service', 'type', 'status']  # type: email, sms
)

notification_delivery_duration = Histogram(
    'notification_delivery_duration_seconds',
    'Time to deliver notification',
    ['service', 'type']
)

notification_dedup_hits = Counter(
    'notification_deduplication_cache_hits_total',
    'Notification deduplication cache hits',
    ['service']
)

# In your notification handler
async def send_notification(user_id, notification_type, content):
    """Send notification with metrics."""
    cache_key = f"notification_{user_id}_{notification_type}"
    
    # Check dedup cache
    if cache_key in cache:
        notification_dedup_hits.labels(service="notification-service").inc()
        return
    
    start_time = time.time()
    try:
        # Your notification sending logic
        send_email(user_id, content)
        
        duration = time.time() - start_time
        notification_requests.labels(
            service="notification-service",
            type=notification_type,
            status="success"
        ).inc()
        notification_delivery_duration.labels(
            service="notification-service",
            type=notification_type
        ).observe(duration)
        
        cache[cache_key] = True
        
    except Exception as e:
        notification_requests.labels(
            service="notification-service",
            type=notification_type,
            status="failed"
        ).inc()
        raise
```

### 2.6 Cart Service Specific Metrics

**In `services/cart-service/main.py`:**

```python
from prometheus_client import Counter, Gauge

cart_requests = Counter(
    'cart_requests_total',
    'Total cart requests',
    ['service', 'operation']  # operation: add, remove, view, checkout
)

cart_cache_hits = Counter(
    'cart_cache_hits_total',
    'Redis cache hits for cart',
    ['service']
)

cart_cache_misses = Counter(
    'cart_cache_misses_total',
    'Redis cache misses for cart',
    ['service']
)

redis_connection_errors = Counter(
    'redis_connection_errors_total',
    'Redis connection errors',
    ['service']
)

active_carts = Gauge(
    'cart_active_count',
    'Number of active shopping carts',
    ['service']
)

# In your cart operations
async def add_to_cart(user_id, product_id, quantity):
    """Add item to cart with metrics."""
    cache_key = f"cart:{user_id}"
    
    try:
        # Try to get from cache
        cached_cart = redis.get(cache_key)
        if cached_cart:
            cart_cache_hits.labels(service="cart-service").inc()
            cart = json.loads(cached_cart)
        else:
            cart_cache_misses.labels(service="cart-service").inc()
            cart = fetch_from_db(user_id)
        
        # Add item
        cart[product_id] = quantity
        
        # Update cache
        redis.set(cache_key, json.dumps(cart))
        
        cart_requests.labels(
            service="cart-service",
            operation="add"
        ).inc()
        
        return cart
        
    except redis.ConnectionError:
        redis_connection_errors.labels(service="cart-service").inc()
        raise
```

---

## Part 3: Create Spark Metrics Exporter

**Create file:** `analytics/metrics_exporter.py`

```python
"""
Prometheus Metrics Exporter for Spark Analytics Jobs

This service polls PostgreSQL tables created by Spark jobs and exposes
metrics as Prometheus format on http://localhost:9090/metrics

Tables monitored:
- revenue_metrics: 1-minute windowed revenue aggregations
- fraud_alerts: Real-time fraud detection alerts
- inventory_velocity: Hourly product sales velocity
- cart_abandonment: 15-minute windowed cart abandonment
- operational_metrics: Spark job execution logs
"""

import os
import logging
import time
from datetime import datetime, timedelta
import psycopg2
from prometheus_client import Counter, Gauge, Histogram, start_http_server, REGISTRY
from prometheus_client.core import CollectorRegistry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database connection parameters
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "kafka_ecom")

# ============ PROMETHEUS METRICS ============

# Revenue metrics
revenue_total_24h = Gauge(
    'spark_revenue_total_24h',
    'Total revenue in last 24 hours',
    ['service']
)

order_count_24h = Gauge(
    'spark_order_count_24h',
    'Total orders processed in last 24 hours',
    ['service']
)

avg_order_value = Gauge(
    'spark_avg_order_value',
    'Average order value',
    ['service']
)

revenue_per_minute = Gauge(
    'spark_revenue_per_minute',
    'Revenue in the latest 1-minute window',
    ['service']
)

# Fraud detection metrics
fraud_alerts_total = Gauge(
    'spark_fraud_alerts_total',
    'Total fraud alerts in last 24 hours',
    ['service', 'severity']
)

fraud_by_type = Gauge(
    'spark_fraud_by_type_total',
    'Fraud alerts by type in last 24 hours',
    ['service', 'alert_type']
)

fraud_alerts_rate = Gauge(
    'spark_fraud_alerts_rate_per_hour',
    'Fraud alert rate per hour',
    ['service']
)

# Inventory velocity metrics
inventory_velocity_total = Gauge(
    'spark_inventory_velocity_units_sold_24h',
    'Total units sold in last 24 hours',
    ['service']
)

top_product_units = Gauge(
    'spark_top_product_units_sold',
    'Units sold for top 10 products (24h)',
    ['service', 'product_id', 'rank']
)

top_product_revenue = Gauge(
    'spark_top_product_revenue',
    'Revenue for top 10 products (24h)',
    ['service', 'product_id', 'rank']
)

# Cart abandonment metrics
cart_abandoned_24h = Gauge(
    'spark_cart_abandoned_24h',
    'Total abandoned carts in last 24 hours',
    ['service']
)

cart_abandonment_rate = Gauge(
    'spark_cart_abandonment_rate',
    'Cart abandonment rate (percent)',
    ['service']
)

cart_recovery_rate = Gauge(
    'spark_cart_recovery_rate',
    'Cart recovery rate (recovered/abandoned)',
    ['service']
)

# Operational metrics
spark_job_duration = Histogram(
    'spark_job_duration_seconds',
    'Spark job execution duration',
    ['service', 'job_name'],
    buckets=(10, 30, 60, 300, 600, 1800, 3600)
)

spark_job_success = Counter(
    'spark_job_success_total',
    'Successful Spark job executions',
    ['service', 'job_name']
)

spark_job_failure = Counter(
    'spark_job_failure_total',
    'Failed Spark job executions',
    ['service', 'job_name']
)

spark_job_records_processed = Counter(
    'spark_job_records_processed_total',
    'Total records processed by Spark jobs',
    ['service', 'job_name']
)

# ============ DATABASE FUNCTIONS ============

def get_db_connection():
    """Create PostgreSQL connection."""
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return None

def update_revenue_metrics(conn):
    """Query revenue_metrics table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get 24-hour revenue stats
        cursor.execute("""
            SELECT 
                SUM(total_revenue) as total_rev,
                SUM(order_count) as total_orders,
                AVG(avg_order_value) as avg_value
            FROM revenue_metrics
            WHERE window_start > NOW() - INTERVAL '24 hours'
        """)
        
        total_rev, total_orders, avg_val = cursor.fetchone()
        revenue_total_24h.labels(service="spark-analytics").set(total_rev or 0)
        order_count_24h.labels(service="spark-analytics").set(total_orders or 0)
        avg_order_value.labels(service="spark-analytics").set(avg_val or 0)
        
        # Get latest minute revenue
        cursor.execute("""
            SELECT total_revenue FROM revenue_metrics
            ORDER BY window_start DESC
            LIMIT 1
        """)
        latest = cursor.fetchone()
        if latest:
            revenue_per_minute.labels(service="spark-analytics").set(latest[0])
        
        cursor.close()
        logger.debug("Updated revenue metrics")
        
    except Exception as e:
        logger.error(f"Error updating revenue metrics: {e}")

def update_fraud_metrics(conn):
    """Query fraud_alerts table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get fraud alerts by severity
        cursor.execute("""
            SELECT severity, COUNT(*) as count
            FROM fraud_alerts
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY severity
        """)
        
        for severity, count in cursor.fetchall():
            fraud_alerts_total.labels(
                service="spark-analytics",
                severity=severity.upper() if severity else "UNKNOWN"
            ).set(count)
        
        # Get fraud alerts by type
        cursor.execute("""
            SELECT alert_type, COUNT(*) as count
            FROM fraud_alerts
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            GROUP BY alert_type
        """)
        
        for alert_type, count in cursor.fetchall():
            fraud_by_type.labels(
                service="spark-analytics",
                alert_type=alert_type or "unknown"
            ).set(count)
        
        # Get fraud alert rate per hour
        cursor.execute("""
            SELECT COUNT(*) * 1.0 / 24 as alerts_per_hour
            FROM fraud_alerts
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)
        
        rate = cursor.fetchone()[0]
        fraud_alerts_rate.labels(service="spark-analytics").set(rate or 0)
        
        cursor.close()
        logger.debug("Updated fraud metrics")
        
    except Exception as e:
        logger.error(f"Error updating fraud metrics: {e}")

def update_inventory_metrics(conn):
    """Query inventory_velocity table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get total units sold
        cursor.execute("""
            SELECT SUM(units_sold)
            FROM inventory_velocity
            WHERE window_start > NOW() - INTERVAL '24 hours'
        """)
        
        total_units = cursor.fetchone()[0]
        inventory_velocity_total.labels(service="spark-analytics").set(total_units or 0)
        
        # Get top 10 products by units sold
        cursor.execute("""
            SELECT product_id, SUM(units_sold) as units, SUM(revenue) as revenue,
                   ROW_NUMBER() OVER (ORDER BY SUM(units_sold) DESC) as rank
            FROM inventory_velocity
            WHERE window_start > NOW() - INTERVAL '24 hours'
            GROUP BY product_id
            ORDER BY units DESC
            LIMIT 10
        """)
        
        for product_id, units, revenue, rank in cursor.fetchall():
            top_product_units.labels(
                service="spark-analytics",
                product_id=str(product_id),
                rank=int(rank)
            ).set(units or 0)
            
            top_product_revenue.labels(
                service="spark-analytics",
                product_id=str(product_id),
                rank=int(rank)
            ).set(revenue or 0)
        
        cursor.close()
        logger.debug("Updated inventory metrics")
        
    except Exception as e:
        logger.error(f"Error updating inventory metrics: {e}")

def update_cart_abandonment_metrics(conn):
    """Query cart_abandonment table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get abandoned carts in 24h
        cursor.execute("""
            SELECT COUNT(*) as abandoned_count
            FROM cart_abandonment
            WHERE window_start > NOW() - INTERVAL '24 hours'
            AND status = 'abandoned'
        """)
        
        abandoned = cursor.fetchone()[0]
        cart_abandoned_24h.labels(service="spark-analytics").set(abandoned or 0)
        
        # Get abandonment rate
        cursor.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'abandoned') * 100.0 / COUNT(*) as abandon_rate
            FROM cart_abandonment
            WHERE window_start > NOW() - INTERVAL '24 hours'
        """)
        
        rate = cursor.fetchone()[0]
        cart_abandonment_rate.labels(service="spark-analytics").set(rate or 0)
        
        # Get recovery rate (recovered vs abandoned)
        cursor.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'recovered') * 1.0 /
                NULLIF(COUNT(*) FILTER (WHERE status = 'abandoned'), 0) as recovery_rate
            FROM cart_abandonment
            WHERE window_start > NOW() - INTERVAL '24 hours'
        """)
        
        recovery = cursor.fetchone()[0]
        cart_recovery_rate.labels(service="spark-analytics").set(recovery or 0)
        
        cursor.close()
        logger.debug("Updated cart abandonment metrics")
        
    except Exception as e:
        logger.error(f"Error updating cart abandonment metrics: {e}")

def update_operational_metrics(conn):
    """Query operational_metrics table and update Prometheus metrics."""
    try:
        cursor = conn.cursor()
        
        # Get job execution stats
        cursor.execute("""
            SELECT job_name, duration, status
            FROM operational_metrics
            ORDER BY execution_time DESC
            LIMIT 50
        """)
        
        for job_name, duration, status in cursor.fetchall():
            if status.upper() == 'SUCCESS':
                spark_job_success.labels(
                    service="spark-analytics",
                    job_name=job_name
                ).inc()
                
                spark_job_duration.labels(
                    service="spark-analytics",
                    job_name=job_name
                ).observe(duration)
            else:
                spark_job_failure.labels(
                    service="spark-analytics",
                    job_name=job_name
                ).inc()
        
        cursor.close()
        logger.debug("Updated operational metrics")
        
    except Exception as e:
        logger.error(f"Error updating operational metrics: {e}")

def update_all_metrics():
    """Update all Prometheus metrics from PostgreSQL."""
    conn = get_db_connection()
    if not conn:
        logger.warning("Could not connect to PostgreSQL, skipping metrics update")
        return
    
    try:
        update_revenue_metrics(conn)
        update_fraud_metrics(conn)
        update_inventory_metrics(conn)
        update_cart_abandonment_metrics(conn)
        update_operational_metrics(conn)
        logger.info("Successfully updated all metrics")
    finally:
        conn.close()

def metrics_update_loop():
    """Continuously update metrics every 30 seconds."""
    logger.info("Starting metrics update loop...")
    while True:
        try:
            update_all_metrics()
            time.sleep(30)  # Update every 30 seconds
        except Exception as e:
            logger.error(f"Error in metrics loop: {e}")
            time.sleep(30)

# ============ MAIN ============

if __name__ == "__main__":
    logger.info("Starting Spark Metrics Exporter...")
    
    # Start Prometheus HTTP server on port 9090
    start_http_server(9090)
    logger.info("Prometheus metrics server started on port 9090")
    logger.info("Metrics available at http://localhost:9090/metrics")
    
    # Start metrics update loop
    metrics_update_loop()
```

**Create file:** `analytics/Dockerfile.exporter`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy metrics exporter
COPY analytics/metrics_exporter.py .

# Install dependencies
RUN pip install prometheus-client psycopg2-binary

EXPOSE 9090

CMD ["python", "metrics_exporter.py"]
```

**Add to docker-compose.yml:**

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
      - spark-master
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=kafka_ecom
      - TZ=America/Los_Angeles
    networks:
      - kafka-network
    restart: unless-stopped
```

---

## Part 4: Create Grafana Dashboards

### 4.1 Services Overview Dashboard

**Create file:** `monitoring/dashboards/services-overview.json`

This dashboard should include:

**Panels to create (in this order):**

1. **Health Status Cards** (Top row)
   - Payment Service Status (last request, response time)
   - Order Service Status (saga success rate, pending count)
   - Inventory Service Status (queue length)
   - Notification Service Status (emails sent, success rate)
   - Cart Service Status (active carts, cache hit %)

2. **Request Rate Row**
   - Payment requests/sec
   - Order requests/sec
   - Inventory requests/sec
   - Notification requests/sec
   - Cart requests/sec
   
   Query format: `rate(service_requests_total[1m])` grouped by service

3. **Latency Row** (p50, p90, p99)
   - Payment latency
   - Order latency
   - Inventory latency
   - Notification latency
   - Cart latency
   
   Query format: `histogram_quantile(0.99, service_request_duration_seconds)`

4. **Error Rate Row**
   - Payment errors/sec
   - Order saga failures/sec
   - Inventory failures/sec
   - Notification failures/sec
   - Cart errors/sec
   
   Query format: `rate(service_errors_total[1m])`

5. **Idempotency & Deduplication Row**
   - Payment idempotency cache hit %
   - Order processed events deduplicated
   - Notification dedup cache hit %

6. **Infrastructure Row**
   - Database connection pool (active)
   - Redis cache hit rate
   - Kafka consumer lag per service

### 4.2 Spark Analytics Dashboard

**Create file:** `monitoring/dashboards/spark-analytics.json`

This dashboard should include:

**Panels to create:**

1. **Job Health Cards** (Top row)
   - Revenue Streaming: Last run time, total 24h revenue
   - Fraud Detection: Last alert count, highest severity
   - Inventory Velocity: Top product, units sold
   - Cart Abandonment: Total abandoned, recovery rate
   - Operational: Success rate, avg duration

2. **Revenue Row**
   - 24-hour total revenue (large gauge)
   - Revenue trend (7 days)
   - Order count (24h)
   - Average order value trend
   
   Queries: SELECT statements from revenue_metrics table with 24h and 7d windows

3. **Fraud Detection Row**
   - Total fraud alerts (24h)
   - Alerts by severity (stacked bar)
   - Alerts by type (pie chart)
   - Alert timeline (hourly)
   
   Queries: SELECT statements from fraud_alerts table

4. **Inventory Velocity Row**
   - Top 10 products by units sold
   - Top 10 products by revenue
   - Velocity score distribution
   - 7-day inventory value trend
   
   Queries: SELECT statements from inventory_velocity table with ranking

5. **Cart Abandonment Row**
   - Total abandoned carts (24h)
   - Abandonment rate %
   - Avg cart value (abandoned vs completed)
   - Trend over 7 days
   
   Queries: SELECT statements from cart_abandonment table

6. **Operational Metrics Row**
   - Job execution status table
   - Duration trend per job
   - Success rate gauge for each job
   - Records processed per job
   
   Queries: SELECT statements from operational_metrics table

---

## Part 5: Grafana Provisioning Setup

**Create file:** `monitoring/provisioning/datasources/prometheus.yml`

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

**Create file:** `monitoring/provisioning/dashboards/dashboards.yml`

```yaml
apiVersion: 1

providers:
  - name: 'Dashboards'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

Update `monitoring/Dockerfile.grafana`:

```dockerfile
FROM grafana/grafana:latest

ENV GF_SECURITY_ADMIN_PASSWORD=admin
ENV GF_SECURITY_ADMIN_USER=admin
ENV GF_INSTALL_PLUGINS=grafana-piechart-panel
ENV GF_USERS_ALLOW_SIGN_UP=false

COPY monitoring/provisioning /etc/grafana/provisioning

EXPOSE 3000

CMD ["bin/grafana-server"]
```

---

## Part 6: Dashboard JSON Template

**For services-overview.json and spark-analytics.json:**

Use this structure:

```json
{
  "dashboard": {
    "title": "Services Overview",
    "uid": "services-overview",
    "tags": ["services", "microservices"],
    "timezone": "browser",
    "schemaVersion": 16,
    "version": 0,
    "refresh": "30s",
    "time": {
      "from": "now-6h",
      "to": "now"
    },
    "panels": [
      {
        "id": 1,
        "title": "Payment Service - Requests/sec",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(service_requests_total{service=\"payment-service\"}[1m])",
            "refId": "A"
          }
        ],
        "gridPos": {
          "h": 8,
          "w": 12,
          "x": 0,
          "y": 0
        }
      }
      // ... more panels ...
    ]
  },
  "overwrite": true
}
```

---

## Testing & Validation

**Create file:** `test-monitoring.sh`

```bash
#!/bin/bash

echo "Testing Monitoring Stack..."

# 1. Check if Prometheus is running
echo "1. Testing Prometheus..."
curl -s http://localhost:9090/api/v1/query?query=up | jq .

# 2. Check if Grafana is running
echo "2. Testing Grafana..."
curl -s http://localhost:3000/api/datasources | jq .

# 3. Check metrics endpoints on all services
echo "3. Testing service metrics endpoints..."
for port in 8001 8002 8003 8004 8005; do
    echo "Service on port $port:"
    curl -s http://localhost:$port/metrics | head -20
done

# 4. Check Spark metrics exporter
echo "4. Testing Spark metrics exporter..."
curl -s http://localhost:9090/metrics | head -20

echo "Done!"
```

---

## Final Checklist

Before considering this complete:

- [ ] Prometheus service added to docker-compose.yml
- [ ] Grafana service added to docker-compose.yml
- [ ] All 5 microservices have `/metrics` endpoint
- [ ] All 5 microservices export appropriate metrics
- [ ] Spark metrics exporter created and running
- [ ] Prometheus.yml properly configured to scrape all services
- [ ] Services Overview dashboard created and populated
- [ ] Spark Analytics dashboard created and populated
- [ ] All dashboards use correct queries and display data
- [ ] Test script passes without errors
- [ ] Can access Grafana at http://localhost:3000
- [ ] Can access Prometheus at http://localhost:9090
- [ ] All panels show real data from live services

---

## Notes for AI Agent

- Use prometheus-client library (Python) for metrics instrumentation
- Follow the pattern: define metrics → middleware/decorator → expose on /metrics
- For Grafana dashboards, test each query in Prometheus first
- Ensure all timezone handling is correct (use UTC where possible)
- Consider adding health checks to services in docker-compose
- Test metrics flow: Service → Prometheus (scrape every 15s) → Grafana (visualize)
- All modifications should be non-breaking to existing functionality
- Create clear commit messages for git history
