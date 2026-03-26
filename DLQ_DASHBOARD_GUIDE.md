# DLQ Dashboard Panels - Complete Guide

## Overview
The Microservices Dashboard includes two DLQ monitoring panels in "Row 5 - DLQ Alerts" that help operators quickly identify and resolve failed events.

---

## Panel 1: DLQ Errors by Service (Table)

**Location:** Microservices Dashboard → Row 5 → Left Panel

### What It Shows
A table of all failed messages (Dead Letter Queue entries) from the past 1 hour, organized by service and error type.

### Columns
| Column | Meaning |
|--------|---------|
| **Service** | Which microservice generated the DLQ message (cart-service, order-service, payment-service, inventory-service, notification-service) |
| **Error Type** | Type of error that caused the failure (PendingRollbackError, OperationalError, TimeoutError, etc.) |
| **DLQ Messages (1h)** | Number of messages in DLQ in the past 1 hour |

### Normal State
```
Service               | Error Type | DLQ Messages (1h)
---------------------|------------|------------------
(empty - no rows)     |    -       |        0
```
✅ When system is healthy, this table shows **NO ROWS** (no failed messages)

### Alert State Example
```
Service               | Error Type             | DLQ Messages (1h)
---------------------|------------------------|------------------
order-service        | PendingRollbackError   |        5
cart-service         | OperationalError       |        2
payment-service      | TimeoutError           |        1
```
❌ When services fail, table shows services with counts > 0

### How to Interpret
- **0 messages:** Service is working fine, all events processed successfully
- **1-5 messages:** Minor issue (likely transient), may self-recover
- **5-50 messages:** Moderate issue, investigate root cause
- **50+ messages:** Critical issue, immediate action required

### Action Items
1. **Identify:** Which service has errors? Look at "Service" column
2. **Diagnose:** What type of error? Look at "Error Type" column
3. **Fix:** Apply fix based on error type (see reference table in README)
4. **Recover:** Run `python scripts/dlq-replay.py --replay-all`

---

## Panel 2: Service Failures vs DLQ Correlation (Graph)

**Location:** Microservices Dashboard → Row 5 → Right Panel

### What It Shows
A time-series graph showing the relationship between HTTP request failures and messages sent to the Dead Letter Queue across all microservices.

### Two Y-Axes
- **Left Axis (Failures/sec):** HTTP errors (4xx and 5xx responses) per second
- **Right Axis (DLQ Messages/sec):** Rate of messages being sent to Dead Letter Queue per second

### Legend Interpretation
Each line represents one metric from one service:
```
order-service - Failures/sec          (blue line)    ← HTTP errors
order-service - DLQ Messages/sec      (red line)     ← DLQ rate
cart-service - Failures/sec           (green line)   ← HTTP errors
cart-service - DLQ Messages/sec       (orange line)  ← DLQ rate
... (one pair per microservice)
```

### Normal State
```
Both axes show flat lines at 0
No legend entries (or all show 0)
```
✅ Zero failures = zero DLQ messages (expected, system healthy)

### Expected Pattern During Failures
```
Time →
Failures/sec: ▂▄██▆▂  (spike when error occurs)
DLQ/sec:      ▁▂▄██▅  (after 3 retries, messages appear in DLQ)
```
✅ When HTTP failures spike → DLQ messages increase after ~10 seconds (expected, shows retry mechanism working)

### Possible Scenarios

#### Scenario 1: Both at 0
```
Interpretation: ✅ System is healthy
Action: No action needed
```

#### Scenario 2: Failures > 0, DLQ = 0
```
Interpretation: ⚠️ Events are failing but recovering via retries
Action: Monitor for 5 minutes. If failures persist, check service logs
  docker-compose logs <service> | grep ERROR
```

#### Scenario 3: DLQ > 0, Failures = 0
```
Interpretation: ⚠️ Async errors (background jobs, event consumers)
Action: Check background job logs or event consumer logs
  docker-compose logs <service> | grep -i dlq
```

#### Scenario 4: Both > 0 and Correlated
```
Interpretation: ✅ Expected pattern (failures → retries → DLQ)
Action: Fix root cause, then replay DLQ messages
  1. Fix issue (restart service, restart postgres, etc.)
  2. python scripts/dlq-replay.py --replay-all
```

---

## Quick Diagnosis Guide

### Question: Why does my panel show "0 for all microservices"?

**Answer:** That's the normal, healthy state! Here's what it means:

| Panel | Shows 0 | Means |
|-------|---------|-------|
| **DLQ Errors by Service** | No rows, all services 0 | All events processed successfully ✅ |
| **Service Failures vs DLQ** | Both lines flat at 0 | No errors, no retries needed ✅ |

### Question: What if the legend is unclear?

**Answer:** Each line should now show:
- Service name (e.g., "order-service")
- Metric type (e.g., "Failures/sec" or "DLQ Messages/sec")

Format: `{service-name} - {metric-type}`

Example clear legends:
```
✅ order-service - Failures/sec
✅ order-service - DLQ Messages/sec
✅ cart-service - Failures/sec
✅ cart-service - DLQ Messages/sec
```

If you see unclear legends, verify the dashboard is updated:
1. Go to Dashboards → Microservices Dashboard
2. Press `F5` to refresh (clear browser cache)
3. If still unclear, re-import dashboard: `bash scripts/dashboard-sync.sh`

---

## Common Issues & Solutions

### Issue: "Table shows 5 but there are no DLQ messages"
**Old Query:** Counted metric definitions, not actual messages  
**Solution:** Dashboard updated with new query using `increase()` function  
**Action:** Re-import dashboard: `bash scripts/dashboard-sync.sh`

### Issue: "Legend doesn't show which service failed"
**Old Legend:** Just showed "DLQ Messages/sec"  
**Solution:** Updated to show `{service} - DLQ Messages/sec`  
**Action:** Refresh dashboard (F5)

### Issue: "Can't see correlation between failures and DLQ"
**Old Graph:** Mixed HTTP errors from all services  
**Solution:** Now aggregates by service with clear service-based legend  
**Action:** Refresh dashboard

---

## Recovery Workflow

When DLQ panel shows errors:

```
1. Check DLQ Errors table
   ↓
2. Identify error type (PendingRollbackError, OperationalError, etc.)
   ↓
3. Fix root cause
   - PendingRollbackError → docker-compose restart <service>
   - Connection refused  → docker-compose up -d <service>
   - Timeout             → Check service logs
   ↓
4. Verify fix in Correlation graph (should go flat)
   ↓
5. Replay DLQ messages
   python scripts/dlq-replay.py --replay-all
   ↓
6. Verify in table (should go to 0)
   ↓
7. ✅ System recovered
```

---

## Prometheus Queries (For Advanced Users)

### Check current DLQ count
```promql
# Total messages in DLQ (current snapshot)
sum(dlq_message_count)

# By service
sum by (service) (dlq_message_count)
```

### Check DLQ rate (new messages per second)
```promql
# Messages added to DLQ in past 5 minutes
rate(dlq_message_count[5m])

# By service
rate(dlq_message_count[5m]) by (service)
```

### Check HTTP failures by service
```promql
# Failures per second
rate(http_requests_total{status=~"4..|5.."}[5m]) by (job)

# Total failures in past hour
sum(increase(http_requests_total{status=~"4..|5.."}[1h])) by (job)
```

---

## Dashboard Update Summary

**Changes Made:**
- ✅ Updated "DLQ Errors by Service" query to use `increase()` instead of `count()`
- ✅ Changed column header "Count" → "DLQ Messages (1h)" for clarity
- ✅ Updated "Service Failures vs DLQ Correlation" legend to include service names
- ✅ Added descriptions to both panels explaining what they show
- ✅ Changed legend display from "list" to "table" for better readability
- ✅ Added service-level aggregation for better diagnostics

**No Action Required:** Dashboards should auto-update. If not, refresh with `F5` or re-sync with:
```bash
bash scripts/dashboard-sync.sh
```
