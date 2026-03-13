# How Dashboard Endpoint Selection Works

## Quick Answer

The dashboard shows **ALL endpoints** that receive traffic, determined by:
1. **Prometheus metric:** `http_requests_total` (tracks every request)
2. **Grouping:** `sum(rate(http_requests_total[1m])) by (service, endpoint)`
3. **Legend:** `{{ service }} {{ endpoint }}` (shows both service and endpoint name)

No manual filtering - it's **automatic and data-driven**. Whatever endpoints your services receive requests on appear on the dashboard.

---

## The Full Decision Process

### Step 1: Request Happens → Metrics Recorded

When any request hits a service, the middleware automatically records it:

```python
# In shared/metrics.py - add_metrics_middleware()
http_requests_total.labels(
    service=service_name,           # e.g., "cart-service"
    method=request.method,          # e.g., "GET", "POST"
    endpoint=normalized_endpoint,   # e.g., "/cart/{user_id}/items"
    status=response.status_code,    # e.g., 200, 404, 500
).inc()
```

### Step 2: Path Normalization (Key Step)

Before recording, we **normalize the endpoint path** to prevent cardinality explosion:

```python
def normalize_endpoint(path: str) -> str:
    # /cart/user_001/items   →  /cart/{user_id}/items
    path = re.sub(r'/user_\d+', '/{user_id}', path)
    
    # /order/12345           →  /order/{id}
    path = re.sub(r'/(\d+)(?=/|$)', '/{id}', path)
    
    # /payment/txn_abc123    →  /payment/{reference_id}
    path = re.sub(r'/(txn_|ref_|order_|payment_|invoice_)[a-zA-Z0-9_]+', '/{reference_id}', path)
    
    return path
```

**Why this matters:** Without normalization, you'd get:
- ❌ `/cart/user_000/items` (1 series)
- ❌ `/cart/user_001/items` (1 series)
- ❌ `/cart/user_002/items` (1 series)
- ... × 50 users = 50 overlapping lines 📊

With normalization:
- ✅ `/cart/{user_id}/items` (1 series, aggregated)

### Step 3: Prometheus Stores the Metrics

Prometheus scrapes every 15 seconds and stores:
- Service name
- HTTP method
- **Normalized endpoint**
- Status code
- Request count

### Step 4: Dashboard Queries and Groups

The dashboard query groups by service AND endpoint:

```promql
sum(rate(http_requests_total[1m])) by (service, endpoint)
```

Breaking this down:
- `http_requests_total` - Total requests (counter metric)
- `rate(...[1m])` - Calculate requests per second over 1 minute
- `sum(...)` - Add up all requests matching the grouping
- `by (service, endpoint)` - Group results by these dimensions
- Result: One line per (service, endpoint) combination

---

## Example: What Gets Shown

When you run 10 concurrent users doing a realistic journey:

### Cart Service Endpoints

```
cart-service /cart/{user_id}/items           → 156 req/min
cart-service /cart/{user_id}/checkout        →  23 req/min
```

### Order Service Endpoints

```
order-service /order                         →  25 req/min
order-service /order/{id}                    →  15 req/min
order-service /order/{id}/status             →  10 req/min
```

### Payment Service Endpoints

```
payment-service /payment/process             →  23 req/min
payment-service /payment/{id}/status         →   8 req/min
```

**Total visible:** ~7-10 lines (not 50-100!)

---

## Decision Tree: Should an Endpoint Show?

```
┌─ Does it receive traffic? ─→ NO  → Not shown (no metrics recorded)
│                         └─→ YES
│
├─ Is it normalized?  ──────→ YES  → Each unique normalized path gets 1 line
│                         └─→ NO   → Normalization applied automatically
│
└─ Result: Line appears in "Request Rate by Endpoint" panel
```

---

## How to Control What Shows

You have **3 levels of control**:

### Level 1: Code Changes (Source)
If an endpoint shouldn't exist, remove it from services:
```python
# Don't create endpoints like this:
@app.get("/debug/{request_id}")  # Would show as /debug/{id}

# Use normalized names:
@app.get("/api/orders")          # Shows as /api/orders
@app.get("/api/orders/{order_id}") # Shows as /api/orders/{id} after normalization
```

### Level 2: Normalization Rules (Metrics)
Adjust `normalize_endpoint()` in `shared/metrics.py` if you want different grouping:

**Currently normalizes:**
- User IDs: `/user_NNN` → `/{user_id}`
- Numeric IDs: `/123` → `/{id}`
- Transaction IDs: `/txn_ABC` → `/{reference_id}`

**To add custom normalization**, edit the function:
```python
def normalize_endpoint(path: str) -> str:
    import re
    
    # ... existing rules ...
    
    # Add custom rule (e.g., for session IDs):
    path = re.sub(r'/session_[a-z0-9]+', '/{session_id}', path)
    
    return path
```

### Level 3: Dashboard Filtering (Visualization)
Filter in the dashboard itself (Grafana):

**Option A:** Add a variable filter in dashboard
```
Request Rate by Endpoint
  Filter: service = "cart-service" only
```

**Option B:** Modify the query to exclude certain endpoints
```promql
# Show all except health checks:
sum(rate(http_requests_total{endpoint!="/health"}[1m])) by (service, endpoint)

# Show only GET requests:
sum(rate(http_requests_total{method="GET"}[1m])) by (service, endpoint)
```

---

## Practical Example: Add a New Endpoint

When you add a new endpoint to a service:

```python
# In services/order-service/main.py
@app.post("/order/bulk-create")
async def bulk_create_orders(orders: List[OrderRequest]):
    return {"created": len(orders)}
```

**What happens automatically:**

1. ✅ First request comes in
2. ✅ Middleware records metric with `endpoint="/order/bulk-create"`
3. ✅ Prometheus scrapes and stores it
4. ✅ **Dashboard automatically shows** `/order/bulk-create` on next refresh

No manual dashboard editing needed!

---

## Real Data from Current System

Run this to see what's actually being tracked:

```bash
# See all endpoints currently tracked:
curl -s http://localhost:8001/metrics | grep 'http_requests_total' | grep -v '#'

# Example output:
# http_requests_total{endpoint="/cart/{user_id}/items",method="GET",service="cart-service",status="200"} 156
# http_requests_total{endpoint="/cart/{user_id}/checkout",method="POST",service="cart-service",status="200"} 23
# http_requests_total{endpoint="/order",method="POST",service="order-service",status="200"} 25
```

See what's in Prometheus:

```bash
# Query Prometheus for all endpoints
curl -s 'http://localhost:9090/api/v1/query?query=http_requests_total' | jq '.data.result[] | {endpoint: .metric.endpoint, service: .metric.service}'
```

---

## Summary

| Aspect | Decision Method |
|--------|-----------------|
| **Which endpoints show?** | All that receive traffic (automatic) |
| **How are they grouped?** | By service + normalized endpoint path |
| **How are IDs handled?** | Stripped during normalization (user_001 → {user_id}) |
| **How is cardinality controlled?** | Regex patterns in `normalize_endpoint()` |
| **Can you customize?** | Yes - modify normalization rules or dashboard query |
| **Does it require dashboard edits?** | No - automatic based on metric data |
| **Is it production-ready?** | Yes - no manual maintenance needed |

---

## When to Adjust the Selection

**Keep current setup if:**
- ✅ Dashboard shows expected endpoints
- ✅ No 50-100+ overlapping lines
- ✅ Lines are labeled meaningfully (e.g., `/cart/{user_id}/items`)

**Adjust if:**
- ❌ Want to group different IDs differently
- ❌ Want to exclude certain endpoints
- ❌ Want service-level only (no per-endpoint breakdown)

See "How to Control What Shows" section above for adjustment options.
