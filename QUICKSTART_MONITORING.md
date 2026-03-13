# Quick Start: Using Prometheus & Grafana

## Access Points

### Grafana Dashboard
- **URL:** http://localhost:3000
- **Username:** admin
- **Password:** admin

### Prometheus Metrics UI
- **URL:** http://localhost:9090

## What's Available Right Now

### 1. View Raw Prometheus Metrics
Access any service's metrics endpoint directly:

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

### 2. Query Prometheus
Visit http://localhost:9090 and try these queries:

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

### 3. Check Grafana
Visit http://localhost:3000:
- Click on "Connections" → "Data sources"
- You should see "Prometheus" is configured
- Ready for dashboards in Phase 2

## Understanding the Metrics (What's Being Collected)

### Default Python Metrics (Already Available)
Every service exports basic Python metrics automatically:
- `python_gc_*` - Garbage collection stats
- `process_*` - CPU, memory, file descriptor usage
- `python_info` - Python version info

### Custom Metrics (Phase 2)
In the next phase, we'll add business metrics like:
- `payment_processing_total` - Payments processed
- `saga_orchestration_steps_total` - Order saga steps
- `inventory_reservation_total` - Inventory reservations
- `notification_sent_total` - Notifications sent
- `cart_operations_total` - Cart operations

## Next Steps

### Phase 2: Add Business Logic Metrics
We'll integrate the `shared/metrics.py` module into each service to track:
1. HTTP request metrics (requests/sec, latency)
2. Business metrics (orders, payments, inventory)
3. Error tracking (failures by type)
4. Cache metrics (hits/misses)

### Phase 3: Create Dashboards
Build Grafana dashboards showing:
1. Service overview (health, request rate, latency)
2. Order pipeline (saga steps, success rate)
3. Business KPIs (revenue, orders, inventory)
4. Alerts and errors

## Troubleshooting

### Prometheus not collecting metrics?
```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq .

# Should see all 6 targets as "up": true
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

## Storage Information

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

## Performance Tips

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

## What You Can Do Now

1. ✅ View real-time metrics from any service
2. ✅ Query metrics using Prometheus Query Language (PromQL)
3. ✅ Setup Grafana (datasource is ready)
4. ✅ Export metrics data
5. ✅ Monitor Python runtime metrics

## What's Ready for Phase 2

- ✅ Prometheus infrastructure
- ✅ Grafana UI
- ✅ All services exposing metrics
- ✅ Shared metrics module (`shared/metrics.py`)
- ✅ Configuration for custom metrics

## Getting Help

### Check Service Logs
```bash
docker logs prometheus          # Prometheus logs
docker logs grafana             # Grafana logs
docker logs payment-service     # Any service logs
```

### Check Container Status
```bash
docker ps | grep -E "prometheus|grafana"
```

### Validate Metrics Endpoint
```bash
# Should return metrics in Prometheus text format
curl http://localhost:8003/metrics

# Check response code is 200
curl -w "\n%{http_code}\n" http://localhost:8003/metrics
```

## Next Commands (When Ready for Phase 2)

```bash
# 1. Add metrics middleware to services
# See MONITORING_IMPLEMENTATION_GUIDE.md Phase 3

# 2. Create first dashboard
# Copy microservices-dashboard.json to monitoring/dashboards/

# 3. Load test and verify metrics
python scripts/simulate-users.py --duration 300

# 4. View metrics in Grafana
# Visit http://localhost:3000/d/microservices-dashboard
```

---

**Status:** Phase 1 Complete - Infrastructure Ready ✅

