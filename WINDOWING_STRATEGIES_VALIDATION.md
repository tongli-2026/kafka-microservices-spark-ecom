# Windowing Strategies - Code Validation Report

**Date:** March 17, 2026  
**Status:** ⚠️ **FOUND INACCURACIES** (3 out of 5 jobs documented incorrectly)

---

## Summary

Checked SPARK_ANALYTICS.md "Windowing Strategies" table against actual code in `analytics/jobs/*.py`. Found **3 discrepancies**:

| Job | Documented | Actual Code | Status |
|-----|------------|------------|--------|
| revenue_streaming | 1 minute | `window(col("event_timestamp"), "1 minute")` | ✅ CORRECT |
| fraud_detection | 5-minute tumbling + 1-minute sliding | `window(col("event_timestamp"), "5 minutes", "1 minute")` | ✅ CORRECT |
| inventory_velocity | 1 hour | `DATE_TRUNC('hour', created_at)` | ✅ CORRECT |
| cart_abandonment | **15 minutes** | No tumbling window - **stream-stream LEFT JOIN** only | ❌ WRONG |
| operational_metrics | 1 minute | `window(col("event_timestamp"), "1 minute")` | ✅ CORRECT |

---

## Detailed Findings

### ✅ Revenue Streaming - CORRECT

**Documented:**
```
Window Type: Tumbling
Duration: 1 minute
```

**Actual Code (line 175 of revenue_streaming.py):**
```python
.groupBy(window(col("event_timestamp"), "1 minute")) \
```

**Status:** ✅ **VERIFIED CORRECT**

---

### ✅ Fraud Detection - CORRECT

**Documented:**
```
Window Type: Tumbling
Duration: 5 minutes
Reason: Pattern detection requires time window
Note: Uses 1-minute sliding step for velocity analysis
```

**Actual Code (lines 226-228 of fraud_detection.py):**
```python
.groupBy(
    col("user_id"),
    window(col("event_timestamp"), "5 minutes", "1 minute")
) \
```

**Status:** ✅ **VERIFIED CORRECT** (5-minute window with 1-minute slide)

---

### ✅ Inventory Velocity - CORRECT

**Documented:**
```
Window Type: Tumbling
Duration: 1 hour
Reason: Inventory trends over longer period
```

**Actual Code (lines 125-130 of inventory_velocity.py):**
```sql
DATE_TRUNC('hour', created_at) as window_start,
DATE_TRUNC('hour', created_at) + INTERVAL '1 hour' as window_end,
```

**Status:** ✅ **VERIFIED CORRECT** (1-hour window via PostgreSQL DATE_TRUNC)

---

### ❌ Cart Abandonment - INCORRECT

**Documented:**
```
Window Type: Sliding
Duration: 15 minutes
Reason: Capture abandonment patterns
```

**Actual Code (lines 195-210 of cart_abandonment.py):**
```python
# Apply watermarks to handle late-arriving data
items_with_wm = parsed_items.withWatermark("item_added_time", "30 seconds")
checkout_with_wm = parsed_checkout.withWatermark("checkout_time", "30 seconds")

# Stream-stream left join to identify abandoned carts
# LEFT JOIN: Keep all item additions, even if no matching checkout
# JOIN CONDITIONS:
#   1. Same user_id (same person who added item)
```

**What Documentation Says:**
- Sliding 15-minute window
- Table in SPARK_ANALYTICS.md shows: "Sliding | 15 minutes"

**What Code Actually Does:**
- **NO TUMBLING/SLIDING WINDOW AT ALL**
- Uses **stream-stream LEFT JOIN** instead
- Watermarks: 30 seconds (for late data tolerance)
- Join window: 1 minute after item add (per docstring: "Checkout must occur within 1 minute")

**Status:** ❌ **WRONG** - Not a windowing strategy, it's a JOIN strategy

**Correct Description Should Be:**
```
Window Type: Stream-Stream Join (not a tumbling/sliding window)
Join Condition: user_id match + checkout within 1 minute of item add
Watermark: 30 seconds (tolerance for late-arriving events)
Output: Left join → keeps all items, nulls for abandoned
```

---

### ✅ Operational Metrics - CORRECT

**Documented:**
```
Window Type: Tumbling
Duration: 1 minute
Reason: Event-based (job completion)
```

**Actual Code (lines 206-207 of operational_metrics.py):**
```python
.groupBy(
    col("topic"),
    window(col("event_timestamp"), "1 minute")
) \
```

**Status:** ✅ **VERIFIED CORRECT** (1-minute tumbling window)

---

## Corrections Required

### SPARK_ANALYTICS.md - Line 558 (Windowing Strategies Table)

**Current (WRONG):**
```markdown
| cart_abandonment | Sliding | 15 minutes | Capture abandonment patterns |
```

**Should Be:**
```markdown
| cart_abandonment | Stream-Stream Join | 1 minute (join window) | Left join: capture items without matching checkout |
```

---

## Detailed Cart Abandonment Logic

Since this is the only incorrect one, here's what the actual code does:

### Current Implementation

**Inputs:**
- Stream 1: `cart.item_added` events
- Stream 2: `cart.checkout_initiated` events

**Processing:**
```python
# Left join: keep all item_added events
items_with_wm.join(
    checkout_with_wm,
    [
        items_with_wm.user_id == checkout_with_wm.checkout_user_id,
        checkout_with_wm.checkout_time >= items_with_wm.item_added_time,
        checkout_with_wm.checkout_time <= items_with_wm.item_added_time + 1 minute
    ],
    "leftOuter"
)
```

**Result:**
- Items WITH matching checkout within 1 minute → included with checkout_time filled
- Items WITHOUT matching checkout → included with checkout_time = NULL
- Filtering for `checkout_time IS NULL` → abandoned carts

**Why Not Tumbling Window:**
- Abandonment detection is **event-driven**, not time-windowed
- Each item addition is independently checked against upcoming checkouts
- No aggregation per time window
- Real-time detection (as soon as watermark expires on item, it's marked abandoned)

---

## Recommendation

Update the **Windowing Strategies** table in SPARK_ANALYTICS.md (lines 555-565) to correct cart_abandonment from "Sliding | 15 minutes" to the accurate "Stream-Stream Join | 1 minute (join window)".

This will ensure documentation matches actual implementation.

---

## Validation Status

- **revenue_streaming:** ✅ CORRECT
- **fraud_detection:** ✅ CORRECT  
- **inventory_velocity:** ✅ CORRECT
- **cart_abandonment:** ❌ NEEDS CORRECTION
- **operational_metrics:** ✅ CORRECT

**Overall:** 4/5 correct (80% accuracy)
