# Monitoring & Observability Implementation Guide (Revised)

## Overview

This guide revises and completes the monitoring implementation plan, addressing gaps in the `AI_AGENT_PROMPT.md`.

**Timeline: 7-10 days**  
**Phases: Infrastructure → Core Instrumentation → Dashboards → Validation**

---

## Phase 0: Preparation (Before Starting Implementation)

### Required Decisions

**1. Alert Notifications** (Choose ONE for MVP)
- [ ] **None** (Recommended for MVP) - Alerts only visible in Grafana
- [ ] Slack webhook (requires Slack integration setup)
- [ ] Email via SMTP (requires mail server configuration)

**2. Metrics Retention Policy**
- [ ] 7 days (minimal storage)
- [ ] **15 days** (Recommended - good balance)
- [ ] 30 days (requires more disk space)

**3. Prometheus Storage Limits**
- Max time series: 100,000 (prevents cardinality explosion)
- Storage path: `/prometheus` (2GB initial, will grow)

**4. Grafana Access**
- [ ] Admin authentication: admin/admin (via environment variable)
- [ ] Anonymous access: Disabled (GF_USERS_ALLOW_SIGN_UP=false)

### Pre-Implementation Checklist

- [ ] Verify all 5 services are running: `docker ps`
- [ ] Verify Kafka is operational: `docker exec kafka1 kafka-broker-api-versions.sh`
- [ ] Verify PostgreSQL is operational: `psql` connection works
- [ ] Check available disk space: `df -h` (need ~5GB for monitoring data)
- [ ] Read Prometheus best practices: https://prometheus.io/docs/practices/

---

## Phase 1: Infrastructure Setup (1-2 days)

### 1.1 Create Monitoring Directory Structure

```bash
mkdir -p monitoring/dashboards
mkdir -p monitoring/provisioning/datasources
mkdir -p monitoring/provisioning/dashboards
```

### 1.2 Prometheus Configuration

**File:** `monitoring/prometheus.yml`

```yaml
global:
  scrape_interval: 15s          # Scrape metrics every 15 seconds
  evaluation_interval: 15s      # Evaluate alerts every 15 seconds
  external_labels:
    monitor: 'kafka-ecom-prod'

# Alerting configuration (optional, for Phase 2)
alerting:
  alertmanagers:
    - static_configs:
        - targets: []
          # Uncomment to enable: alertmanager:9093

# Alert rules (optional, for Phase 2)
rule_files:
  # - "alert-rules.yml"

scrape_configs:
  # ==================== PAYMENT SERVICE ====================
  - job_name: 'payment-service'
    static_configs:
      - targets: ['payment-service:8003']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s

  # ==================== ORDER SERVICE ====================
  - job_name: 'order-service'
    static_configs:
      - targets: ['order-service:8002']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s

  # ==================== INVENTORY SERVICE ====================
  - job_name: 'inventory-service'
    static_configs:
      - targets: ['inventory-service:8004']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s

  # ==================== NOTIFICATION SERVICE ====================
  - job_name: 'notification-service'
    static_configs:
      - targets: ['notification-service:8005']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s

  # ==================== CART SERVICE ====================
  - job_name: 'cart-service'
    static_configs:
      - targets: ['cart-service:8001']
    metrics_path: '/metrics'
    scrape_interval: 15s
    scrape_timeout: 10s

  # ==================== PROMETHEUS ITSELF ====================
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
```

### 1.3 Prometheus Dockerfile

**File:** `monitoring/Dockerfile.prometheus`

```dockerfile
FROM prom/prometheus:v2.45.0

# Create non-root user for security
RUN useradd --no-create-home --shell /bin/false prometheus

# Copy configuration
COPY monitoring/prometheus.yml /etc/prometheus/prometheus.yml

# Set permissions
RUN chown -R prometheus:prometheus /etc/prometheus

# Expose metrics port
EXPOSE 9090

# Run as non-root user
USER prometheus

# Start Prometheus with command-line arguments
CMD ["--config.file=/etc/prometheus/prometheus.yml", \
     "--storage.tsdb.path=/prometheus", \
     "--storage.tsdb.retention.time=15d", \
     "--storage.tsdb.max-block-duration=2h"]
```

### 1.4 Grafana Configuration

**File:** `monitoring/Dockerfile.grafana`

```dockerfile
FROM grafana/grafana:10.0.0

# Install plugins (optional)
RUN grafana-cli plugins install grafana-piechart-panel --quiet && \
    grafana-cli plugins install grafana-worldmap-panel --quiet

# Copy provisioning configurations
COPY monitoring/provisioning /etc/grafana/provisioning

# Expose dashboard port
EXPOSE 3000

# Start Grafana
CMD ["bin/grafana-server", "cfg:default.paths.provisioning=/etc/grafana/provisioning"]
```

**File:** `monitoring/provisioning/datasources/prometheus.yml`

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
    jsonData:
      timeInterval: 15s
```

**File:** `monitoring/provisioning/dashboards/dashboards.yml`

```yaml
apiVersion: 1

providers:
  - name: 'default'
    orgId: 1
    folder: 'monitoring'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
```

### 1.5 Update docker-compose.yml

Add these services to your existing `docker-compose.yml`:

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
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:9090/-/healthy"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

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
      - ./monitoring/dashboards:/var/lib/grafana/dashboards
    networks:
      - kafka-network
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_USERS_ALLOW_SIGN_UP: "false"
      GF_INSTALL_PLUGINS: "grafana-piechart-panel,grafana-worldmap-panel"
      TZ: America/Los_Angeles
    depends_on:
      - prometheus
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
```

Add to `volumes:` section:

```yaml
volumes:
  prometheus_data:
    driver: local
  grafana_data:
    driver: local
```

---

## Phase 2: Shared Metrics Module (1 day)

### 2.1 Create Metrics Module

**File:** `shared/metrics.py`

```python
"""
Shared metrics module for all microservices.

Provides:
- Generic request/response metrics via middleware
- Service-specific metric decorators
- Prometheus client setup
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
import logging
import time
from functools import wraps
from typing import Callable, Optional
import asyncio

logger = logging.getLogger(__name__)

# ============================================================================
# SHARED METRICS (ALL SERVICES)
# ============================================================================

# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status'],
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['service', 'endpoint', 'method'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Error metrics
service_errors_total = Counter(
    'service_errors_total',
    'Total service errors',
    ['service', 'error_type', 'endpoint'],
)

# Database metrics
db_connection_pool_active = Gauge(
    'db_connection_pool_active',
    'Active database connections',
    ['service'],
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query duration in seconds',
    ['service', 'query_type'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

# ============================================================================
# PAYMENT SERVICE SPECIFIC METRICS
# ============================================================================

payment_processing_total = Counter(
    'payment_processing_total',
    'Total payment processing attempts',
    ['service', 'status'],  # status: success, failed, pending
)

payment_processing_duration_seconds = Histogram(
    'payment_processing_duration_seconds',
    'Payment processing duration in seconds',
    ['service'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
)

payment_validation_errors_total = Counter(
    'payment_validation_errors_total',
    'Total payment validation errors',
    ['service', 'error_reason'],  # e.g., invalid_card, insufficient_funds
)

idempotency_cache_hits_total = Counter(
    'idempotency_cache_hits_total',
    'Idempotency cache hits',
    ['service'],
)

idempotency_cache_misses_total = Counter(
    'idempotency_cache_misses_total',
    'Idempotency cache misses',
    ['service'],
)

# ============================================================================
# ORDER SERVICE SPECIFIC METRICS
# ============================================================================

order_processing_total = Counter(
    'order_processing_total',
    'Total orders created',
    ['service', 'status'],  # status: created, confirmed, cancelled
)

saga_steps_total = Counter(
    'saga_orchestration_steps_total',
    'Total saga orchestration steps executed',
    ['service', 'step', 'status'],
    # step: payment, inventory, notification
    # status: success, failed, compensated
)

saga_compensation_total = Counter(
    'saga_compensation_total',
    'Total saga compensation (rollback) events',
    ['service', 'step'],
)

pending_orders_gauge = Gauge(
    'pending_orders_total',
    'Number of pending orders',
    ['service'],
)

processed_events_deduplicated_total = Counter(
    'processed_events_deduplicated_total',
    'Events deduplicated via processed_events table',
    ['service'],
)

outbox_events_pending_gauge = Gauge(
    'outbox_events_pending_total',
    'Number of pending outbox events',
    ['service'],
)

# ============================================================================
# INVENTORY SERVICE SPECIFIC METRICS
# ============================================================================

inventory_reservation_total = Counter(
    'inventory_reservation_total',
    'Total inventory reservations',
    ['service', 'product_id', 'status'],  # status: success, failed
)

inventory_reservation_duration_seconds = Histogram(
    'inventory_reservation_duration_seconds',
    'Inventory reservation duration',
    ['service', 'product_id'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

stock_level_gauge = Gauge(
    'inventory_stock_level',
    'Current stock level',
    ['service', 'product_id', 'warehouse'],
)

inventory_allocation_errors_total = Counter(
    'inventory_allocation_errors_total',
    'Inventory allocation errors',
    ['service', 'product_id', 'error_reason'],
)

# ============================================================================
# NOTIFICATION SERVICE SPECIFIC METRICS
# ============================================================================

notification_sent_total = Counter(
    'notification_sent_total',
    'Total notifications sent',
    ['service', 'type', 'status'],  # type: email, sms; status: sent, failed
)

notification_processing_duration_seconds = Histogram(
    'notification_processing_duration_seconds',
    'Notification processing duration',
    ['service', 'type'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0),
)

notification_deduplication_hits_total = Counter(
    'notification_deduplication_hits_total',
    'Notification deduplication cache hits',
    ['service'],
)

# ============================================================================
# CART SERVICE SPECIFIC METRICS
# ============================================================================

cart_operations_total = Counter(
    'cart_operations_total',
    'Total cart operations',
    ['service', 'operation'],  # operation: add_item, remove_item, checkout, view
)

redis_cache_hits_total = Counter(
    'redis_cache_hits_total',
    'Redis cache hits',
    ['service'],
)

redis_cache_misses_total = Counter(
    'redis_cache_misses_total',
    'Redis cache misses',
    ['service'],
)

redis_connection_errors_total = Counter(
    'redis_connection_errors_total',
    'Redis connection errors',
    ['service'],
)

# ============================================================================
# KAFKA METRICS
# ============================================================================

kafka_message_published_total = Counter(
    'kafka_message_published_total',
    'Total Kafka messages published',
    ['service', 'topic', 'status'],  # status: success, failed
)

kafka_message_consumed_total = Counter(
    'kafka_message_consumed_total',
    'Total Kafka messages consumed',
    ['service', 'topic'],
)

kafka_produce_errors_total = Counter(
    'kafka_produce_errors_total',
    'Total Kafka produce errors',
    ['service', 'topic', 'error_type'],
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def track_request_metrics(service_name: str):
    """Middleware for tracking HTTP requests."""
    async def middleware(request, call_next):
        start_time = time.time()
        endpoint = request.url.path
        method = request.method

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            http_requests_total.labels(
                service=service_name,
                method=method,
                endpoint=endpoint,
                status=response.status_code,
            ).inc()

            http_request_duration_seconds.labels(
                service=service_name,
                endpoint=endpoint,
                method=method,
            ).observe(duration)

            return response

        except Exception as e:
            duration = time.time() - start_time
            service_errors_total.labels(
                service=service_name,
                error_type=type(e).__name__,
                endpoint=endpoint,
            ).inc()
            raise

    return middleware


def track_operation(
    operation_name: str,
    service_name: str,
    duration_metric: Optional[Histogram] = None,
    status_counter: Optional[Counter] = None,
):
    """
    Decorator to track operation timing and status.

    Usage:
        @track_operation(
            operation_name="payment_processing",
            service_name="payment-service",
            duration_metric=payment_processing_duration_seconds,
            status_counter=payment_processing_total,
        )
        async def process_payment(order_id: str, amount: float):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                if status_counter:
                    status_counter.labels(service=service_name, status="success").inc()
                return result
            except Exception as e:
                if status_counter:
                    status_counter.labels(service=service_name, status="failed").inc()
                logger.error(f"Error in {operation_name}: {e}")
                raise
            finally:
                duration = time.time() - start_time
                if duration_metric:
                    duration_metric.labels(service=service_name).observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                if status_counter:
                    status_counter.labels(service=service_name, status="success").inc()
                return result
            except Exception as e:
                if status_counter:
                    status_counter.labels(service=service_name, status="failed").inc()
                logger.error(f"Error in {operation_name}: {e}")
                raise
            finally:
                duration = time.time() - start_time
                if duration_metric:
                    duration_metric.labels(service=service_name).observe(duration)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# METRICS ENDPOINT
# ============================================================================


def get_metrics_response():
    """
    Return Prometheus metrics in text format.

    Usage in FastAPI:
        from shared.metrics import get_metrics_response
        
        @app.get("/metrics")
        async def metrics():
            return get_metrics_response()
    """
    return (generate_latest(), CONTENT_TYPE_LATEST)
```

### 2.2 Update requirements.txt (ALL SERVICES)

Add to each service's `requirements.txt`:

```
prometheus-client>=0.17.0,<1.0.0
```

---

## Phase 3: Service Instrumentation (2-3 days)

### 3.1 Payment Service Integration

**File:** `services/payment-service/main.py` (ADD AT TOP after imports)

```python
from fastapi import FastAPI, Request
from fastapi.responses import Response
from shared.metrics import (
    track_request_metrics,
    track_operation,
    payment_processing_total,
    payment_processing_duration_seconds,
    idempotency_cache_hits_total,
    idempotency_cache_misses_total,
    get_metrics_response,
)

SERVICE_NAME = "payment-service"

# ... existing FastAPI app creation ...

app.add_middleware(Middleware(Track Request Metrics))  # See implementation below

# ADD THIS ENDPOINT
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    content, content_type = get_metrics_response()
    return Response(content=content, media_type=content_type)
```

**In payment processing function:**

```python
@track_operation(
    operation_name="process_payment",
    service_name=SERVICE_NAME,
    duration_metric=payment_processing_duration_seconds,
    status_counter=payment_processing_total,
)
async def process_payment(order_id: str, amount: float, idempotency_key: str):
    """Process payment with idempotency and metrics."""
    
    # Check cache for idempotency
    cached_result = payment_cache.get(idempotency_key)
    if cached_result:
        idempotency_cache_hits_total.labels(service=SERVICE_NAME).inc()
        return cached_result
    
    idempotency_cache_misses_total.labels(service=SERVICE_NAME).inc()
    
    # Process payment...
    result = await call_payment_provider(order_id, amount)
    
    # Cache result
    payment_cache.set(idempotency_key, result)
    
    return result
```

### 3.2 Order Service Integration

**File:** `services/order-service/main.py` (ADD AT TOP)

```python
from shared.metrics import (
    order_processing_total,
    saga_steps_total,
    saga_compensation_total,
    processed_events_deduplicated_total,
    outbox_events_pending_gauge,
    get_metrics_response,
)

SERVICE_NAME = "order-service"

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    content, content_type = get_metrics_response()
    return Response(content=content, media_type=content_type)
```

**In saga orchestration:**

```python
async def handle_cart_checkout_initiated(event):
    """Handle cart checkout with metrics."""
    
    # Check if already processed (idempotency)
    if is_event_processed(event['event_id']):
        processed_events_deduplicated_total.labels(service=SERVICE_NAME).inc()
        return
    
    try:
        # Create order
        order = create_order(event)
        order_processing_total.labels(service=SERVICE_NAME, status="created").inc()
        
        # Update outbox gauge
        update_outbox_gauge()
        
        # Step 1: Inventory reservation
        await call_inventory_service(order_id, items)
        saga_steps_total.labels(
            service=SERVICE_NAME,
            step="inventory",
            status="success",
        ).inc()
        
        # Step 2: Payment processing
        await call_payment_service(order_id, amount)
        saga_steps_total.labels(
            service=SERVICE_NAME,
            step="payment",
            status="success",
        ).inc()
        
        order_processing_total.labels(service=SERVICE_NAME, status="confirmed").inc()
        
    except Exception as e:
        # Compensating transaction
        saga_compensation_total.labels(service=SERVICE_NAME, step="payment").inc()
        order_processing_total.labels(service=SERVICE_NAME, status="cancelled").inc()
        raise


def update_outbox_gauge():
    """Update pending outbox events gauge."""
    count = db.query(
        "SELECT COUNT(*) FROM outbox_events WHERE published = false"
    )
    outbox_events_pending_gauge.labels(service=SERVICE_NAME).set(count)
```

### 3.3 Inventory Service Integration

**File:** `services/inventory-service/main.py`

```python
from shared.metrics import (
    inventory_reservation_total,
    inventory_reservation_duration_seconds,
    stock_level_gauge,
    get_metrics_response,
)

SERVICE_NAME = "inventory-service"

@app.get("/metrics")
async def metrics():
    content, content_type = get_metrics_response()
    return Response(content=content, media_type=content_type)

@track_operation(
    operation_name="reserve_inventory",
    service_name=SERVICE_NAME,
    duration_metric=inventory_reservation_duration_seconds,
    status_counter=inventory_reservation_total,
)
async def reserve_inventory(order_id: str, items: List[InventoryItem]):
    """Reserve inventory with metrics."""
    
    for item in items:
        product_id = item.product_id
        
        try:
            reserved = await db.reserve(product_id, item.quantity)
            
            inventory_reservation_total.labels(
                service=SERVICE_NAME,
                product_id=product_id,
                status="success",
            ).inc()
            
            # Update stock gauge
            current_stock = db.get_stock_level(product_id)
            stock_level_gauge.labels(
                service=SERVICE_NAME,
                product_id=product_id,
                warehouse="us-west-2",
            ).set(current_stock)
            
        except InsufficientStockError:
            inventory_reservation_total.labels(
                service=SERVICE_NAME,
                product_id=product_id,
                status="failed",
            ).inc()
            raise
```

### 3.4 Notification Service Integration

**File:** `services/notification-service/main.py`

```python
from shared.metrics import (
    notification_sent_total,
    notification_processing_duration_seconds,
    notification_deduplication_hits_total,
    get_metrics_response,
)

SERVICE_NAME = "notification-service"

@app.get("/metrics")
async def metrics():
    content, content_type = get_metrics_response()
    return Response(content=content, media_type=content_type)

@track_operation(
    operation_name="send_notification",
    service_name=SERVICE_NAME,
    duration_metric=notification_processing_duration_seconds,
    status_counter=notification_sent_total,
)
async def send_email(user_id: str, template: str, context: dict):
    """Send email with metrics."""
    
    # Check deduplication cache
    cache_key = f"email_{user_id}_{template}"
    if dedup_cache.get(cache_key):
        notification_deduplication_hits_total.labels(service=SERVICE_NAME).inc()
        return
    
    try:
        result = await email_service.send(user_id, template, context)
        
        notification_sent_total.labels(
            service=SERVICE_NAME,
            type="email",
            status="sent",
        ).inc()
        
        dedup_cache.set(cache_key, True)
        return result
        
    except Exception as e:
        notification_sent_total.labels(
            service=SERVICE_NAME,
            type="email",
            status="failed",
        ).inc()
        raise
```

### 3.5 Cart Service Integration

**File:** `services/cart-service/main.py`

```python
from shared.metrics import (
    cart_operations_total,
    redis_cache_hits_total,
    redis_cache_misses_total,
    redis_connection_errors_total,
    get_metrics_response,
)

SERVICE_NAME = "cart-service"

@app.get("/metrics")
async def metrics():
    content, content_type = get_metrics_response()
    return Response(content=content, media_type=content_type)

async def get_cart(user_id: str):
    """Get cart with cache metrics."""
    
    try:
        # Try Redis cache
        cached_cart = redis_client.get(f"cart_{user_id}")
        if cached_cart:
            redis_cache_hits_total.labels(service=SERVICE_NAME).inc()
            return json.loads(cached_cart)
        
        redis_cache_misses_total.labels(service=SERVICE_NAME).inc()
        
        # Get from DB and cache
        cart = db.get_cart(user_id)
        redis_client.set(f"cart_{user_id}", json.dumps(cart), ex=3600)
        
        return cart
        
    except RedisConnectionError:
        redis_connection_errors_total.labels(service=SERVICE_NAME).inc()
        # Fallback to DB
        return db.get_cart(user_id)

async def add_item_to_cart(user_id: str, product_id: str, quantity: int):
    """Add item to cart with metrics."""
    
    cart_operations_total.labels(
        service=SERVICE_NAME,
        operation="add_item",
    ).inc()
    
    # Implementation...
```

---

## Phase 4: Dashboards (1-2 days)

### 4.1 Microservices Overview Dashboard

**File:** `monitoring/dashboards/microservices-dashboard.json`

```json
{
  "dashboard": {
    "title": "Microservices Overview",
    "tags": ["microservices", "fastapi"],
    "timezone": "browser",
    "refresh": "30s",
    "panels": [
      {
        "title": "Request Rate (per minute)",
        "targets": [
          {
            "expr": "rate(http_requests_total[1m])",
            "legendFormat": "{{ service }}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Request Latency (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, http_request_duration_seconds)",
            "legendFormat": "{{ service }}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(service_errors_total[5m])",
            "legendFormat": "{{ service }} - {{ error_type }}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Orders Created (today)",
        "targets": [
          {
            "expr": "increase(order_processing_total{status=\"created\"}[24h])"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Payment Success Rate",
        "targets": [
          {
            "expr": "rate(payment_processing_total{status=\"success\"}[1h]) / rate(payment_processing_total[1h])",
            "legendFormat": "Success Rate"
          }
        ],
        "type": "gauge"
      },
      {
        "title": "Inventory Reservations (per hour)",
        "targets": [
          {
            "expr": "rate(inventory_reservation_total{status=\"success\"}[1h])",
            "legendFormat": "{{ product_id }}"
          }
        ],
        "type": "graph"
      }
    ]
  }
}
```

### 4.2 Saga Orchestration Dashboard

**File:** `monitoring/dashboards/saga-dashboard.json`

```json
{
  "dashboard": {
    "title": "Saga Orchestration",
    "tags": ["saga", "order-service"],
    "timezone": "browser",
    "refresh": "30s",
    "panels": [
      {
        "title": "Saga Steps Completed",
        "targets": [
          {
            "expr": "rate(saga_orchestration_steps_total[5m])",
            "legendFormat": "{{ step }} - {{ status }}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Saga Failures (by step)",
        "targets": [
          {
            "expr": "rate(saga_compensation_total[1h])",
            "legendFormat": "{{ step }}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Pending Outbox Events",
        "targets": [
          {
            "expr": "outbox_events_pending_total"
          }
        ],
        "type": "stat"
      },
      {
        "title": "Order Processing Timeline",
        "targets": [
          {
            "expr": "order_processing_total",
            "legendFormat": "{{ status }}"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Idempotency Effectiveness",
        "targets": [
          {
            "expr": "rate(processed_events_deduplicated_total[1h])",
            "legendFormat": "Deduplicated"
          }
        ],
        "type": "stat"
      }
    ]
  }
}
```

---

## Phase 5: Testing & Validation (1-2 days)

### 5.1 Pre-Launch Checklist

```bash
# 1. Start services
docker-compose up -d

# 2. Verify all containers are running
docker ps | grep -E "prometheus|grafana|payment|order|inventory|notification|cart"

# 3. Check Prometheus connectivity
curl http://localhost:9090/-/healthy

# 4. Check Grafana connectivity
curl http://localhost:3000/api/health

# 5. Verify services expose metrics
curl http://localhost:8003/metrics  # payment-service
curl http://localhost:8002/metrics  # order-service
curl http://localhost:8004/metrics  # inventory-service
curl http://localhost:8005/metrics  # notification-service
curl http://localhost:8001/metrics  # cart-service
```

### 5.2 Load Testing with Monitoring

```bash
# Start generating load while monitoring
cd scripts

# In Terminal 1: Generate user load
python simulate-users.py --duration 300 --concurrent-users 50

# In Terminal 2: Monitor Prometheus targets
watch -n 5 'curl -s http://localhost:9090/api/v1/query?query=up | jq .'

# In Terminal 3: Watch Grafana
# Open http://localhost:3000/d/microservices-dashboard
```

### 5.3 Validation Script

**File:** `scripts/validate-metrics.sh`

```bash
#!/bin/bash

set -e

echo "=== Validating Monitoring Stack ==="

# Function to check endpoint
check_endpoint() {
    local name=$1
    local url=$2
    
    if curl -sf "$url" > /dev/null 2>&1; then
        echo "✓ $name is accessible"
    else
        echo "✗ $name is NOT accessible"
        return 1
    fi
}

# Check services
check_endpoint "Prometheus" "http://localhost:9090/-/healthy"
check_endpoint "Grafana" "http://localhost:3000/api/health"
check_endpoint "Payment Metrics" "http://localhost:8003/metrics"
check_endpoint "Order Metrics" "http://localhost:8002/metrics"
check_endpoint "Inventory Metrics" "http://localhost:8004/metrics"
check_endpoint "Notification Metrics" "http://localhost:8005/metrics"
check_endpoint "Cart Metrics" "http://localhost:8001/metrics"

# Check Prometheus scrape targets
echo ""
echo "=== Checking Prometheus Targets ==="
TARGETS=$(curl -s http://localhost:9090/api/v1/query?query=up | jq '.data.result | length')
echo "Active targets: $TARGETS"

if [ "$TARGETS" -ge 5 ]; then
    echo "✓ All services registered with Prometheus"
else
    echo "✗ Only $TARGETS services registered (expected >= 5)"
fi

echo ""
echo "=== Validation Complete ==="
echo "Access Grafana: http://localhost:3000 (admin/admin)"
echo "Access Prometheus: http://localhost:9090"
```

---

## Known Issues & Workarounds

### Issue 1: Services not appearing in Prometheus

**Symptom:** Prometheus targets show "DOWN"

**Cause:** Services haven't exported metrics endpoint yet

**Fix:**
1. Ensure all services have `/metrics` endpoint
2. Verify service is running: `docker logs order-service`
3. Check service can reach Prometheus: `docker exec order-service curl http://prometheus:9090`

### Issue 2: Grafana dashboards not loading

**Symptom:** "Dashboard not found" or blank panels

**Cause:** Dashboards not in correct directory or missing datasource

**Fix:**
1. Verify files exist: `ls -la monitoring/dashboards/`
2. Check Prometheus datasource: http://localhost:3000/ds/prometheus
3. Restart Grafana: `docker restart grafana`

### Issue 3: High Prometheus memory usage

**Symptom:** Prometheus using >2GB RAM

**Cause:** High cardinality metrics (too many label combinations)

**Fix:**
1. Avoid labels with user_id, order_id, etc.
2. Set `--storage.tsdb.max-block-duration=2h`
3. Reduce scrape interval from 15s to 30s

---

## Success Criteria

After completing all phases:

- ✅ Prometheus scraping metrics from all 5 services
- ✅ Grafana dashboards displaying real-time metrics
- ✅ <2% performance overhead from instrumentation
- ✅ Alerts visible in Grafana (optional: Slack/Email alerts)
- ✅ All services return 200 on `/metrics` endpoint
- ✅ Metrics retention for 15 days
- ✅ Load test shows proper metric recording

---

## Next Steps (Phase 2 - Optional)

1. **Add Spark Analytics Metrics** - Export Spark job metrics from PostgreSQL
2. **Add Kafka Consumer Lag** - Monitor topic lag
3. **Add Alert Rules** - Define thresholds and alerting
4. **Add Custom Dashboards** - Team-specific views
5. **Add Distributed Tracing** - Jaeger integration (future)

---

## References

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Grafana Dashboard Guide](https://grafana.com/docs/grafana/latest/dashboards/)
- [Prometheus Python Client](https://github.com/prometheus/client_python)
- [Metric Naming](https://prometheus.io/docs/practices/naming/)

