# Spark Analytics Dashboard

## Overview

The **Spark Analytics Dashboard** is a comprehensive Grafana dashboard that visualizes all 21 metrics exported by the Spark Metrics Exporter. It provides real-time monitoring of analytics jobs running on Apache Spark, covering revenue analytics, fraud detection, inventory tracking, cart abandonment monitoring, and operational metrics.

**Dashboard UID:** `spark-analytics-dashboard`  
**Location:** `monitoring/dashboards/spark-analytics-dashboard.json`  
**Refresh Interval:** 30 seconds (aligned with metrics exporter update frequency)

---

## Dashboard Structure

The dashboard is organized into 5 logical sections:

### 1. **Revenue Analytics** (Top Row - 4 KPI Gauges + 2 Time Series)

Tracks financial metrics from the revenue streaming analytics job.

#### Key Performance Indicators
- **24h Total Revenue** (Blue Gauge)
  - Metric: `spark_revenue_total_24h`
  - Unit: USD
  - Data Source: `revenue_metrics` table
  - Shows total revenue generated in the last 24 hours

- **24h Order Count** (Green Gauge)
  - Metric: `spark_order_count_24h`
  - Unit: Orders
  - Data Source: `revenue_metrics` table
  - Shows total orders processed in 24 hours

- **Average Order Value** (Orange Gauge)
  - Metric: `spark_avg_order_value`
  - Unit: USD
  - Calculated as total revenue / order count
  - Indicates average transaction size

- **Revenue Per Minute** (Purple Gauge)
  - Metric: `spark_revenue_per_minute`
  - Unit: USD/minute
  - Data Source: Latest `revenue_metrics` record
  - Shows current revenue generation rate

#### Trend Visualizations
- **Revenue Trend (24h)** - Time series showing revenue changes over the past 6 hours
- **Order Count Trend (24h)** - Time series showing order volume trends

---

### 2. **Fraud Detection** (Middle-Left - 1 KPI + 2 Analysis Charts)

Monitors fraud detection system performance and alert patterns.

#### Key Performance Indicators
- **Total Fraud Alerts** (Red Gauge)
  - Metric: `spark_fraud_alerts_total`
  - Unit: Alerts
  - Data Source: `fraud_alerts` table (24h window)
  - Shows cumulative fraud alerts detected

#### Analysis Charts
- **Fraud Alerts by Type** (Stacked Bar Chart)
  - Metric: `spark_fraud_by_type_total`
  - Grouped by: `alert_type` label
  - Shows distribution of different fraud alert categories
  - Common types: suspicious_behavior, high_amount, multiple_declines, velocity_check

- **Fraud Alert Rate (Alerts/Hour)** (Time Series)
  - Metric: `spark_fraud_alerts_rate_per_hour`
  - Unit: Alerts per hour
  - Calculated as: 24h alerts / 24 hours
  - Helps identify trends in fraud detection activity

---

### 3. **Inventory Analytics** (Middle-Right - 1 KPI + 2 Top N Rankings)

Tracks inventory velocity and product performance.

#### Key Performance Indicators
- **24h Units Sold** (Green Gauge)
  - Metric: `spark_inventory_velocity_units_sold_24h`
  - Unit: Units
  - Data Source: `inventory_velocity` table
  - Shows total inventory units sold in 24 hours

#### Product Rankings
- **Top 10 Products by Units Sold** (Bar Chart)
  - Metric: `spark_top_product_units_sold`
  - Visualization: Top 10 products by quantity
  - Helps identify best-selling items
  - Uses query: `topk(10, spark_top_product_units_sold)`

- **Top 10 Products by Revenue** (Bar Chart)
  - Metric: `spark_top_product_revenue`
  - Visualization: Top 10 products by revenue generated
  - May differ from units sold (due to pricing differences)
  - Uses query: `topk(10, spark_top_product_revenue)`

---

### 4. **Cart Abandonment** (Bottom-Left - 3 KPIs + 1 Trend)

Monitors abandoned cart detection and recovery efforts.

#### Key Performance Indicators
- **24h Abandoned Carts** (Orange Gauge)
  - Metric: `spark_cart_abandoned_24h`
  - Unit: Carts
  - Data Source: `cart_abandonment` table (24h window)
  - Shows number of carts detected as abandoned

- **Cart Abandonment Rate** (Threshold Gauge - Red/Yellow/Green)
  - Metric: `spark_cart_abandonment_rate`
  - Unit: Percent (%)
  - Thresholds:
    - Red: < 30% (low detection)
    - Yellow: 30-50%
    - Green: > 50% (expected, all rows are abandonments)
  - **Note:** Currently set to 100% - all rows in `cart_abandonment` table are detected abandonments

- **Cart Recovery Rate** (Threshold Gauge - Green/Yellow)
  - Metric: `spark_cart_recovery_rate`
  - Unit: Percent (%)
  - Thresholds:
    - Green: > 30%
    - Yellow: < 30%
  - **Note:** Currently set to 0.0 - cart recovery tracking not available in current schema
  - **TODO:** Requires schema enhancement with status tracking or separate recovered_carts table

#### Trend Visualization
- **Cart Abandonment Trend** (Time Series)
  - Shows 24h abandoned cart count over time
  - Helps identify peaks and patterns in abandonment

---

### 5. **Spark Job Operations** (Bottom-Right - 2 KPIs + 2 Analysis Charts)

Monitors health and performance of all Spark analytics jobs.

#### Key Performance Indicators
- **Total Successful Jobs** (Green Gauge)
  - Metric: `spark_job_success_total`
  - Unit: Count
  - Data Source: `operational_metrics` table (status='SUCCESS')
  - Cumulative count of successful job executions

- **Total Failed Jobs** (Red Gauge)
  - Metric: `spark_job_failure_total`
  - Unit: Count
  - Data Source: `operational_metrics` table (status!='SUCCESS')
  - Cumulative count of failed job executions

#### Performance Analysis
- **Job Success vs Failure Rate** (Stacked Area Chart)
  - Compares success and failure counts over time
  - Visual indication of overall system health
  - Shows both metrics stacked for easy comparison

- **Spark Job Execution Duration by Job** (Time Series - Multi-line)
  - Metric: `spark_job_duration` (grouped by job_name)
  - Unit: Milliseconds (ms)
  - Tracks duration trends for all 5 analytics jobs:
    - Revenue Streaming
    - Fraud Detection
    - Inventory Velocity
    - Cart Abandonment
    - Operational Metrics
  - Helps identify performance degradation or outliers

---

## Metrics Reference

### All 21 Spark Metrics Visualized

| # | Metric Name | Type | Unit | Description |
|---|---|---|---|---|
| 1 | `spark_revenue_total_24h` | Gauge | USD | 24-hour total revenue |
| 2 | `spark_order_count_24h` | Gauge | Orders | 24-hour order count |
| 3 | `spark_avg_order_value` | Gauge | USD | Average order value |
| 4 | `spark_revenue_per_minute` | Gauge | USD/min | Current revenue rate |
| 5 | `spark_fraud_alerts_total` | Counter | Count | Total fraud alerts (24h) |
| 6 | `spark_fraud_by_type_total` | Counter | Count | Fraud alerts grouped by type |
| 7 | `spark_fraud_alerts_rate_per_hour` | Gauge | Alerts/hr | Fraud alert rate |
| 8 | `spark_inventory_velocity_units_sold_24h` | Gauge | Units | 24-hour units sold |
| 9 | `spark_top_product_units_sold` | Gauge | Units | Top 10 products by units |
| 10 | `spark_top_product_revenue` | Gauge | USD | Top 10 products by revenue |
| 11 | `spark_cart_abandoned_24h` | Gauge | Carts | 24-hour abandoned carts |
| 12 | `spark_cart_abandonment_rate` | Gauge | % | Abandonment rate |
| 13 | `spark_cart_recovery_rate` | Gauge | % | Recovery rate |
| 14 | `spark_job_success_total` | Counter | Count | Successful job executions |
| 15 | `spark_job_failure_total` | Counter | Count | Failed job executions |
| 16 | `spark_job_duration{job_name='revenue_streaming'}` | Histogram | ms | Revenue job duration |
| 17 | `spark_job_duration{job_name='fraud_detection'}` | Histogram | ms | Fraud detection duration |
| 18 | `spark_job_duration{job_name='inventory_velocity'}` | Histogram | ms | Inventory velocity duration |
| 19 | `spark_job_duration{job_name='cart_abandonment'}` | Histogram | ms | Cart abandonment duration |
| 20 | `spark_job_duration{job_name='operational_metrics'}` | Histogram | ms | Operational metrics duration |
| 21 | `spark_job_records_processed_total` | Counter | Records | Total records processed (in exporter) |

---

## Accessing the Dashboard

### In Grafana UI
1. Navigate to `http://localhost:3000`
2. Go to **Dashboards** → **Browse**
3. Search for **"Spark Analytics Dashboard"** or find it by tag "spark"
4. Click to open

### Direct URL
```
http://localhost:3000/d/spark-analytics-dashboard/spark-analytics-dashboard
```

---

## Customization Guide

### Changing Time Range
- Default: Last 6 hours
- Click the time picker in the top-right corner
- Options: 5m, 15m, 1h, 6h, 24h, 7d, 30d, custom

### Adjusting Refresh Rate
- Current: 30 seconds (matches exporter frequency)
- To change: Click dashboard settings → Refresh interval
- Recommended: Keep at 30s for real-time visibility

### Modifying Thresholds
To change gauge thresholds (e.g., abandonment rate colors):
1. Click the panel to edit
2. Go to **Field Config** tab
3. Adjust **Thresholds** section
4. Save changes

### Adding Alerts
To create alerts for specific metrics:
1. Go to **Alerting** → **Alert rules**
2. Create new rule targeting Spark metrics
3. Example: Alert if fraud_alerts_rate_per_hour > 10
4. Configure notification channels (email, Slack, etc.)

---

## Alerts & Thresholds

### Recommended Alert Rules

**1. High Fraud Alert Rate**
- Condition: `spark_fraud_alerts_rate_per_hour > 10`
- Severity: Warning
- Action: Notify security team

**2. High Cart Abandonment Rate**
- Condition: `spark_cart_abandonment_rate > 60%`
- Severity: Warning
- Action: Trigger recovery campaigns

**3. Job Failure Rate**
- Condition: `spark_job_failure_total > spark_job_success_total * 0.1`
- Severity: Critical
- Action: Page on-call engineer

**4. Revenue Anomaly**
- Condition: `spark_revenue_total_24h < avg(spark_revenue_total_24h) * 0.8`
- Severity: Warning
- Action: Investigate platform issues

---

## Known Limitations & TODOs

### 1. Cart Recovery Tracking ⚠️
**Current State:**
- Recovery rate hardcoded to 0.0% because `cart_abandonment` table only tracks detections, not recoveries
- Abandonment rate fixed at 100%

**Enhancement Needed:**
```sql
ALTER TABLE cart_abandonment ADD COLUMN status VARCHAR(20);
-- OR create separate recovered_carts table
```

**Impact:** Once implemented, both metrics will show meaningful data

### 2. Job Name Extraction ⚠️
**Current State:**
- Job names extracted from `metric_name` via string split
- Works with current naming convention (e.g., "revenue_streaming_duration" → "revenue")
- May be fragile if naming changes

**Enhancement Needed:**
```sql
ALTER TABLE operational_metrics ADD COLUMN job_name VARCHAR(100);
```

**Impact:** More robust job tracking without string parsing

### 3. Records Processed Metric ℹ️
**Current State:**
- `spark_job_records_processed_total` is not currently visualized in dashboard
- Available in metrics exporter but no dedicated panel

**Enhancement:** Add panel to show records processed by job type

---

## Data Freshness & Latency

- **Exporter Update Frequency:** Every 30 seconds
- **Prometheus Scrape Interval:** 30 seconds
- **Grafana Query Latency:** < 1 second
- **Total End-to-End Latency:** ~1-2 seconds

This ensures near-real-time visibility into Spark analytics operations.

---

## Integration with Other Dashboards

This dashboard complements the following Grafana dashboards:
- **Microservices Dashboard** - Application-level metrics from FastAPI services
- **Order Fulfillment Dashboard** - E-commerce order processing
- **Financial Operations Dashboard** - Payment and revenue tracking
- **Customer Experience Dashboard** - User-facing metrics
- **Infrastructure Health Dashboard** - System resources and Kafka health

---

## Troubleshooting

### No Data Showing
1. Verify metrics exporter is running: `docker ps | grep spark-metrics-exporter`
2. Check PostgreSQL connectivity from exporter container
3. Verify Prometheus can scrape: `http://localhost:9090/targets`

### Metrics Missing
1. Check if specific Spark jobs are running (they don't emit metrics when idle)
2. Verify PostgreSQL `operational_metrics` table has recent data
3. Review exporter logs: `docker logs spark-metrics-exporter`

### High Latency
1. Reduce dashboard refresh rate if CPU-bound
2. Check Prometheus database performance
3. Monitor Grafana server resources

---

## Export & Sharing

### Export Dashboard
1. Click dashboard settings (gear icon)
2. Select **Save as** to clone
3. Export JSON via **Share** → **Export**

### Share with Team
1. Click **Share** button
2. Get shareable link with current view
3. Generate embed code for reports

---

## Updates & Maintenance

- **Last Updated:** March 17, 2026
- **Grafana Version:** 10.0+
- **Prometheus Version:** 2.45+
- **Metrics Exporter Version:** Part 3 Complete

Monitor this dashboard regularly to:
- Identify revenue trends and anomalies
- Track fraud detection effectiveness
- Optimize inventory velocity
- Reduce cart abandonment
- Ensure Spark job health
