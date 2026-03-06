# Deep Dive: Spark Analytics Architecture

## Overview

This document provides a comprehensive understanding of the Spark analytics layer in the Kafka microservices e-commerce platform. It covers the architecture, job designs, data flows, windowing strategies, and integration with the broader system.

---

## Part 1: System Architecture

### High-Level Flow

```
┌─────────────────────────────────────────┐
│ Event Sources (Microservices)           │
├─────────────────────────────────────────┤
│ ├─ order.created (Order Service)        │
│ ├─ order.confirmed (Order Service)      │
│ ├─ payment.processed (Payment Service)  │
│ ├─ inventory.reserved (Inventory Svc)   │
│ ├─ notification.email_sent (Notif Svc) │
│ └─ notification.sms_sent (Notif Svc)   │
└─────────────────────────────────────────┘
                    ↓
         ┌──────────────────────┐
         │ Kafka Broker Cluster │
         │ (3 brokers, 3 topics)│
         └──────────────────────┘
                    ↓
    ┌───────────────────────────────────┐
    │   Spark Structured Streaming      │
    │ ┌─────────────────────────────┐   │
    │ │ 5 Analytics Jobs (Parallel) │   │
    │ │                             │   │
    │ │ 1. Revenue Streaming        │   │ (1-min windows)
    │ │ 2. Fraud Detection          │   │ (5-min windows)
    │ │ 3. Inventory Velocity       │   │ (1-hour windows)
    │ │ 4. Cart Abandonment         │   │ (15-min windows)
    │ │ 5. Operational Metrics      │   │ (job execution logs)
    │ │                             │   │
    │ └─────────────────────────────┘   │
    │       (Spark Master: 7077)         │
    │       (Spark Workers: 4040+)       │
    └───────────────────────────────────┘
                    ↓
         ┌──────────────────────┐
         │ PostgreSQL Database  │
         │ (Aggregated Results) │
         │                      │
         │ ├─ revenue_metrics   │
         │ ├─ fraud_alerts      │
         │ ├─ inventory_velocity│
         │ ├─ cart_abandonment  │
         │ └─ operational_..    │
         └──────────────────────┘
                    ↓
         ┌──────────────────────┐
         │ Prometheus Exporter  │
         │ (Polls every 30s)    │
         └──────────────────────┘
                    ↓
    ┌───────────────────────────────┐
    │ Prometheus + Grafana Dashboards │
    └───────────────────────────────┘
```

### Key Components

| Component | Role | Technology | Port |
|-----------|------|-----------|------|
| **Spark Master** | Cluster manager, resource allocation | Spark Standalone | 7077 |
| **Spark Worker 1** | Task execution, driver execution | Spark Standalone | 4040 (driver) |
| **Spark Worker 2** | Task execution | Spark Standalone | 8081 (UI) |
| **Analytics Jobs** | Stream processing, aggregations | Spark Structured Streaming | - |
| **Checkpoint Storage** | Job state recovery | Local `/tmp/checkpoints/` | - |
| **PostgreSQL** | Persistent aggregation storage | PostgreSQL 15 | 5432 |

---

## Part 2: Spark Structured Streaming Concepts

### What is Structured Streaming?

Spark Structured Streaming treats streaming data as an **infinite table** where new rows are appended continuously:

```
Time → 
Row 1: {order_id: "O001", amount: 100, timestamp: "2026-03-05 10:00:00"}
Row 2: {order_id: "O002", amount: 250, timestamp: "2026-03-05 10:00:05"}
Row 3: {order_id: "O003", amount: 150, timestamp: "2026-03-05 10:00:10"}
...
(new rows continuously added)
```

### Key Concepts

#### 1. **Sources** (Where data comes from)

```python
# Reading from Kafka
df = spark.readStream \
    .format("kafka") \
    .option("subscribe", "payment.processed") \
    .options(**kafka_options) \
    .load()

# Returns: Streaming DataFrame with columns:
# - key: Message key (bytes)
# - value: Message payload (bytes)
# - topic: Topic name
# - partition: Partition number
# - offset: Message offset
# - timestamp: Message timestamp
# - timestampType: Timestamp type
```

#### 2. **Transformations** (How data is processed)

```python
# Parse JSON
schema = StructType([
    StructField("amount", DoubleType()),
    StructField("user_id", StringType()),
    StructField("timestamp", StringType()),
])

parsed_df = df.select(
    from_json(col("value").cast("string"), schema).alias("data")
).select("data.*")

# Aggregate with window
windowed_df = parsed_df \
    .withWatermark("timestamp", "10 seconds") \
    .groupBy(window(col("timestamp"), "1 minute")) \
    .agg(sum("amount").alias("total"))

# Output: DataFrame with results ready to write
```

#### 3. **Sinks** (Where results go)

```python
# Write to PostgreSQL (batch approach)
query = windowed_df \
    .writeStream \
    .foreachBatch(write_to_postgres) \
    .outputMode("append") \
    .option("checkpointLocation", "/tmp/checkpoints/job") \
    .start()

# Keeps running indefinitely
query.awaitTermination()
```

---

## Part 3: Windowing Strategies

### What is a Window?

A **window** groups streaming events into time buckets for aggregation:

```
Example: Payment events with 1-minute window

10:00:00 - 10:01:00: [Payment1($100), Payment2($200), Payment3($150)]
                     → Aggregated: Total=$450, Count=3, Avg=$150

10:01:00 - 10:02:00: [Payment4($300), Payment5($75)]
                     → Aggregated: Total=$375, Count=2, Avg=$187.50

10:02:00 - 10:03:00: [Payment6($250)]
                     → Aggregated: Total=$250, Count=1, Avg=$250
```

### Types of Windows

#### 1. **Tumbling Window** (Non-overlapping)
```
Fixed time buckets that don't overlap

|--- 1 min ---|--- 1 min ---|--- 1 min ---|
[Events]      [Events]      [Events]

Example: revenue_streaming (1-minute window)
Each minute produces exactly one result with that minute's revenue.
```

#### 2. **Sliding Window** (Overlapping)
```
Same-sized buckets that shift by interval

|--- 5 min ---|
      |--- 5 min ---|
            |--- 5 min ---|

Example: fraud_detection (5-min window, 1-min slide)
Produces output every 1 minute with last 5 minutes of data.
Detects sustained suspicious patterns better than tumbling.
```

#### 3. **Session Window** (Event-driven)
```
Buckets based on activity gaps (not implemented yet)

[Events]     Gap > 30min     [Events]
|   session   |              |   session   |

Could be useful for detecting user session patterns.
```

### Code Example

```python
from pyspark.sql.functions import window, col

# Tumbling window (1 minute)
tumbling = parsed_df \
    .groupBy(window(col("timestamp"), "1 minute")) \
    .agg(sum("amount").alias("total"))

# Sliding window (5 minutes, slides every 1 minute)
sliding = parsed_df \
    .groupBy(window(col("timestamp"), "5 minutes", "1 minute")) \
    .agg(sum("amount").alias("total"))

# Session window (30-minute gaps)
session = parsed_df \
    .groupBy(sessionWindow(col("timestamp"), "30 minutes")) \
    .agg(sum("amount").alias("total"))
```

---

## Part 4: The 5 Spark Analytics Jobs

### Job 1: Revenue Streaming (1-minute windows)

**Purpose:** Track revenue metrics in real-time

**Input:** `payment.processed` Kafka topic
```json
{
  "amount": 999.99,
  "user_id": "user_001",
  "order_id": "order_abc123",
  "timestamp": "2026-03-05T10:00:00Z"
}
```

**Processing Logic:**
```
1. Read Kafka topic: payment.processed
2. Parse JSON → Extract amount, user_id, order_id, timestamp
3. Group by 1-minute tumbling window
4. Aggregate:
   - SUM(amount) → total_revenue
   - COUNT(*) → order_count
   - AVG(amount) → avg_order_value
5. Write to PostgreSQL: revenue_metrics table
```

**Output:** `revenue_metrics` table
```sql
window_start      | window_end        | total_revenue | order_count | avg_order_value
2026-03-05 10:00:00 | 2026-03-05 10:01:00 | 5234.50       | 5           | 1046.90
2026-03-05 10:01:00 | 2026-03-05 10:02:00 | 3421.00       | 3           | 1140.33
```

**Use Cases:**
- Real-time revenue dashboard
- Detect revenue anomalies
- Monitor payment success rate
- Business metrics for management

**Window Strategy:** **Tumbling (1 minute)**
- Why? Each minute is independent business metric
- No overlapping data
- Clean one-result-per-minute pattern

---

### Job 2: Fraud Detection (5-minute sliding windows)

**Purpose:** Detect suspicious payment patterns in real-time

**Input:** Both `payment.processed` and `order.created` topics
```json
Payment: {
  "amount": 5500,
  "user_id": "user_fraud",
  "order_id": "order_xyz",
  "timestamp": "2026-03-05T10:00:00Z"
}

Order: {
  "total_amount": 5500,
  "user_id": "user_fraud",
  "order_id": "order_xyz",
  "timestamp": "2026-03-05T10:00:00Z"
}
```

**Processing Logic:**
```
1. Read both Kafka topics in parallel
2. Parse both JSON streams
3. Union both streams (combine as one source)
4. Group by (user_id, 5-minute sliding window)
5. Aggregate over last 5 minutes:
   - COUNT(*) → event_count
   - SUM(orders) → order_count
   - MAX(amount) → max_order_amount
   - SUM(payments) → payment_count
6. Detect fraud if:
   - order_count > 3 (unusual order frequency)
   - max_order_amount > $1000 (high-value order)
   - payment_count > 2 (multiple failed payments)
7. Write alerts to PostgreSQL: fraud_alerts table
```

**Output:** `fraud_alerts` table
```sql
user_id    | window_start        | alert_type              | severity | details
user_fraud | 2026-03-05 10:00:00 | high_order_value       | CRITICAL | max=$5500
user_fraud | 2026-03-05 10:01:00 | unusual_order_frequency| MEDIUM   | 4 orders in 5min
```

**Use Cases:**
- Real-time fraud prevention
- Risk-based payment approval
- Chargebacks and dispute prediction
- Customer behavior analysis

**Window Strategy:** **Sliding (5 minutes, 1-minute slide)**
- Why? Fraud patterns develop over time
- Need to see last 5 minutes to detect sustained abuse
- Sliding every 1 minute catches new patterns ASAP

---

### Job 3: Inventory Velocity (1-hour windows)

**Purpose:** Track which products are selling fastest

**Input:** `inventory.reserved` Kafka topic
```json
{
  "product_id": "PROD001",
  "quantity": 2,
  "timestamp": "2026-03-05T10:00:00Z"
}
```

**Processing Logic:**
```
1. Read Kafka topic: inventory.reserved
2. Parse JSON → Extract product_id, quantity, timestamp
3. Group by (product_id, 1-hour tumbling window)
4. Aggregate:
   - SUM(quantity) → units_sold
5. Rank products by units_sold (top sellers)
6. Write to PostgreSQL: inventory_velocity table
```

**Output:** `inventory_velocity` table
```sql
product_id | window_start        | units_sold | rank
PROD001    | 2026-03-05 10:00:00 | 45         | 1
PROD002    | 2026-03-05 10:00:00 | 32         | 2
PROD003    | 2026-03-05 10:00:00 | 28         | 3
```

**Use Cases:**
- Inventory demand forecasting
- Stock-out prevention
- Trending products identification
- Supplier ordering optimization

**Window Strategy:** **Tumbling (1 hour)**
- Why? Hourly windows match business planning cycles
- Demand patterns clear over hour intervals
- Non-overlapping avoids double-counting stock

---

### Job 4: Cart Abandonment (15-minute windows)

**Purpose:** Identify customers who started orders but didn't complete

**Input:** Both `order.created` and `payment.processed` topics
```json
Order: {
  "order_id": "order_abc",
  "user_id": "user_123",
  "timestamp": "2026-03-05T10:00:00Z"
}

Payment: {
  "order_id": "order_abc",
  "timestamp": "2026-03-05T10:00:15Z"
}
```

**Processing Logic:**
```
1. Read both Kafka topics
2. Parse both streams
3. For each order_id:
   - If payment exists within 15 minutes → status = "completed"
   - If no payment within 15 minutes → status = "abandoned"
4. Group by 15-minute tumbling window
5. Aggregate:
   - COUNT(abandoned) → abandoned_count
   - COUNT(completed) → completed_count
   - AVG(order_value) → avg_value_abandoned vs completed
6. Write to PostgreSQL: cart_abandonment table
```

**Output:** `cart_abandonment` table
```sql
window_start        | status    | count | avg_cart_value
2026-03-05 10:00:00 | abandoned | 12    | 234.50
2026-03-05 10:00:00 | completed | 28    | 567.80
```

**Use Cases:**
- Identify high-value abandoned carts
- Recovery email campaigns
- Payment friction points
- UX improvement targets

**Window Strategy:** **Tumbling (15 minutes)**
- Why? 15 minutes = typical user session length
- Matches payment processing time expectations
- Clear separation of periods

---

### Job 5: Operational Metrics (Job execution logs)

**Purpose:** Track Spark job health and performance

**Input:** Job's own execution logs (not Kafka-based)
```
This job runs separately and logs:
- Job start/end time
- Records processed
- Processing duration
- Success/failure status
```

**Processing Logic:**
```
1. Run periodically (cron-scheduled or manual trigger)
2. Execute query on each Kafka topic:
   - COUNT messages in last hour
   - Calculate processing rate (msgs/sec)
3. Record metrics to PostgreSQL: operational_metrics table
4. Log job execution details
```

**Output:** `operational_metrics` table
```sql
job_name           | execution_time      | status  | duration_ms | records_processed
revenue_streaming  | 2026-03-05 10:00:00 | SUCCESS | 120         | 150
fraud_detection    | 2026-03-05 10:00:00 | SUCCESS | 250         | 450
```

**Use Cases:**
- Spark cluster health monitoring
- Job latency tracking
- Resource utilization analysis
- SLA compliance verification

**Job Type:** **Batch (not streaming)**
- Why? Not continuous like others
- Runs on schedule, captures point-in-time metrics

---

## Part 5: Key Spark Features Used

### 1. Watermarks (Handling Late Data)

```python
.withWatermark("event_timestamp", "10 seconds")
```

**What is it?**
Watermarks allow late-arriving data (up to the watermark delay) to be included in window results.

**Example:**
```
Events arrive:
10:00:05 - Payment $100
10:00:15 - Payment $200
10:00:08 - Payment $150 (LATE - arrived 7 seconds after 10:00:15)

Without watermark: $150 payment ignored
With watermark (10 seconds): $150 included in 10:00-10:01 window

Watermark drops off data after 10 seconds old:
10:00:25 - Any data from before 10:00:15 is now discarded
```

### 2. Micro-batches (Processing Model)

```python
.writeStream \
.foreachBatch(write_to_postgres) \
.outputMode("append")
```

**What is it?**
Structured Streaming processes data in small batches (not truly real-time):

```
Kafka topic has:
Message 1 (offset 0)
Message 2 (offset 1)
Message 3 (offset 2)
Message 4 (offset 3)

Spark processes in batches:
Batch 1 (after 0.5s): Process messages 0-1
Batch 2 (after 0.5s): Process messages 2-3
Batch 3 (after 0.5s): No new messages

Each batch → forEach_batch_function() → Write to PostgreSQL
```

**Advantages:**
- Fault tolerance (can replay batches)
- Exactly-once semantics (with idempotent writes)
- Easier to debug (batch-level logs)

### 3. Output Modes

```python
.outputMode("append")  # Only write new complete results
```

**Options:**
1. **Append** (recommended for aggregations)
   - Writes only new complete window results
   - Example: Each new minute's revenue window = 1 new row
   - Storage: Append to table (no duplicates if idempotent)

2. **Complete** (bad for large datasets)
   - Writes entire results (all windows, all time)
   - Example: All 1000 revenue windows every batch
   - Storage: Overwrites table completely each time
   - ❌ Very inefficient

3. **Update** (for dynamic results)
   - Writes only changed results
   - Example: If late data updates previous window, rewrite it

---

## Part 6: Data Flow Deep Dive

### Example: Complete Revenue Streaming Flow

**Time: 10:00:30 (Batch execution)**

```
1. KAFKA INPUT (payment.processed topic)
   ├─ Message 1: {amount: 100, timestamp: "10:00:05", offset: 0}
   ├─ Message 2: {amount: 250, timestamp: "10:00:15", offset: 1}
   ├─ Message 3: {amount: 150, timestamp: "10:00:25", offset: 2}
   └─ Message 4: {amount: 300, timestamp: "10:01:05", offset: 3}

2. READ FROM KAFKA
   Spark reads raw Kafka messages with metadata
   ├─ key: null
   ├─ value: "{amount: 100, ...}"
   ├─ topic: "payment.processed"
   ├─ partition: 0
   ├─ offset: 0
   ├─ timestamp: 10:00:05
   └─ ...

3. PARSE JSON
   from_json(col("value"), schema)
   ├─ Message 1 → {amount: 100, timestamp: "10:00:05"}
   ├─ Message 2 → {amount: 250, timestamp: "10:00:15"}
   ├─ Message 3 → {amount: 150, timestamp: "10:00:25"}
   └─ Message 4 → {amount: 300, timestamp: "10:01:05"}

4. EXTRACT TIMESTAMP
   to_timestamp(col("data.timestamp"))
   ├─ Message 1 → {amount: 100, event_timestamp: <timestamp 10:00:05>}
   ├─ Message 2 → {amount: 250, event_timestamp: <timestamp 10:00:15>}
   ├─ Message 3 → {amount: 150, event_timestamp: <timestamp 10:00:25>}
   └─ Message 4 → {amount: 300, event_timestamp: <timestamp 10:01:05>}

5. APPLY WATERMARK & WINDOW
   withWatermark("event_timestamp", "10 seconds")
   .groupBy(window("event_timestamp", "1 minute"))
   
   Watermark at 10:00:30: Drop data older than 10:00:20
   Window 10:00:00-10:01:00: Messages 1,2,3 (all within window)
   Window 10:01:00-10:02:00: Message 4 (starts after 10:01)

6. AGGREGATE (for each window)
   Window 10:00:00-10:01:00:
   ├─ SUM(amount) = 100 + 250 + 150 = 500
   ├─ COUNT(*) = 3
   └─ AVG(amount) = 500 / 3 = 166.67

   Window 10:01:00-10:02:00:
   ├─ SUM(amount) = 300
   ├─ COUNT(*) = 1
   └─ AVG(amount) = 300

7. MICRO-BATCH OUTPUT (3 rows)
   ┌──────────────┬──────────────┬──────────────┬────────────┬──────────────┐
   │ window_start │ window_end   │ total_revenue│ order_count│ avg_order_val│
   ├──────────────┼──────────────┼──────────────┼────────────┼──────────────┤
   │ 10:00:00     │ 10:01:00     │ 500.00       │ 3          │ 166.67       │
   │ 10:01:00     │ 10:02:00     │ 300.00       │ 1          │ 300.00       │
   └──────────────┴──────────────┴──────────────┴────────────┴──────────────┘

8. JDBC WRITE (foreach_batch_function)
   INSERT INTO revenue_metrics (window_start, window_end, ...)
   VALUES ('10:00:00', '10:01:00', 500.00, 3, 166.67)
   VALUES ('10:01:00', '10:02:00', 300.00, 1, 300.00)

9. CHECKPOINT UPDATE
   /tmp/checkpoints/revenue-streaming/
   ├─ offsets/0 → 4 (latest processed offset)
   └─ ...

10. NEXT BATCH (10:00:35)
    New messages arrive, repeat from step 1
    Only unprocessed messages (offset > 4) are processed
```

---

## Part 7: Checkpoint & Fault Tolerance

### What is a Checkpoint?

A checkpoint stores the **streaming query state** so it can recover from failures:

```
/tmp/checkpoints/revenue-streaming/
├─ offsets/
│  └─ 0: "4"  # Last processed message offset = 4
├─ state/
│  └─ ...window aggregation state...
└─ metadata
   └─ ...query metadata...
```

### How Recovery Works

```
Scenario: Spark job crashes after processing offset 4

Step 1: Job dies
Step 2: User restarts job: docker-compose up or spark-submit ...
Step 3: Spark checks checkpoint
Step 4: Finds: "We processed up to offset 4"
Step 5: Starts from offset 5 (not from beginning)
Step 6: No data loss, no re-processing, seamless recovery

Result: Idempotent operation - can restart without worrying
```

### Checkpoint Storage Location

Current setup uses **local file system**:
```python
.option("checkpointLocation", "/tmp/checkpoints/{job_name}")
```

This works fine for single-machine Docker Compose setup, but for distributed Spark cluster:
```python
# Better for production (HDFS, S3, etc.)
.option("checkpointLocation", "hdfs://namenode:9000/checkpoints/revenue")
.option("checkpointLocation", "s3://bucket/checkpoints/revenue")
```

---

## Part 8: Performance Characteristics

### Throughput (Messages/second)

| Job | Typical Rate | Peak Rate | Notes |
|-----|-------------|-----------|-------|
| Revenue Streaming | 100-500 msgs/s | 5000 msgs/s | Simple aggregation, fast |
| Fraud Detection | 50-200 msgs/s | 2000 msgs/s | Dual-stream join, slower |
| Inventory Velocity | 200-1000 msgs/s | 10000 msgs/s | Single stream, very fast |
| Cart Abandonment | 50-150 msgs/s | 1500 msgs/s | Dual-stream, 15-min window |
| Operational Metrics | N/A | N/A | Batch job, not continuous |

### Latency (Time from event to database)

| Job | End-to-End Latency | Components |
|-----|-------------------|------------|
| Revenue Streaming | 1-3 seconds | Kafka(0.2s) + Spark(0.5s) + JDBC(2s) |
| Fraud Detection | 2-5 seconds | Kafka(0.2s) + Join(1s) + Spark(1.5s) + JDBC(2s) |
| Inventory Velocity | 1-2 seconds | Kafka(0.2s) + Spark(0.3s) + JDBC(1.5s) |
| Cart Abandonment | 3-6 seconds | Dual Kafka(0.4s) + Join(2s) + JDBC(3.6s) |

**Latency Breakdown:**
```
1. Kafka latency (0.2s typical)
   - Message published
   - Broker receives & replicates
   - Broker acknowledges to producer

2. Spark micro-batch delay (0.5-2s typical)
   - Configurable with:
     .trigger(processingTime='500ms')
   - Longer batch = more throughput, higher latency
   - Shorter batch = less throughput, lower latency

3. JDBC write latency (1.5-3s typical)
   - INSERT/UPDATE network round-trip
   - PostgreSQL disk sync (fsync)
   - Connection pooling overhead

Total: 1-6 seconds from event to queryable database
```

### Resource Usage

```
Typical Docker Compose setup (3 jobs running):

Spark Master:      300 MB RAM, 5% CPU
Spark Worker 1:    2 GB RAM, 20% CPU (driver + tasks)
Spark Worker 2:    1.5 GB RAM, 15% CPU (tasks)

PostgreSQL:        1 GB RAM, 10% CPU (during writes)
Redis:             200 MB RAM, 5% CPU
Kafka Brokers (3): 600 MB each, 5% CPU each

Total: ~8 GB RAM, 70% CPU during normal load
```

### Network Bandwidth

```
With 1000 orders/minute (16.7 orders/sec):

Kafka → Spark: ~5 MB/min (small JSON messages)
Spark → PostgreSQL: ~2 MB/min (aggregated results)
Total: ~7 MB/min network usage

With 10x load (10,000 orders/min):
Total: ~70 MB/min network usage (still reasonable)
```

---

## Part 9: Configuration & Tuning

### Key Configuration Parameters

**In `spark_session.py`:**

```python
spark = SparkSession.builder \
    .appName(app_name) \
    .master(spark_master) \
    .config("spark.sql.streaming.checkpointLocation", checkpoint_dir) \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
    .config("spark.streaming.kafka.maxRatePerPartition", "10000") \
    .config("spark.sql.session.timeZone", "UTC") \
    .getOrCreate()
```

| Parameter | Current Value | Effect | Tuning |
|-----------|---------------|--------|--------|
| `maxRatePerPartition` | 10000 | Max messages per partition per batch | Increase for high throughput, decrease for low resource |
| `trigger(processingTime)` | Default (500ms) | Batch interval | Increase for lower latency, decrease for better throughput |
| `spark.executor.memory` | Default (2GB) | Memory per executor | Increase if OOM errors |
| `spark.executor.cores` | Default (auto) | Cores per executor | Match to machine cores |

### Performance Tuning Examples

**For LOW LATENCY (real-time alerting):**
```python
spark.sql.streaming.forceDeleteTempCheckpointLocation = True
query = windowed_df \
    .writeStream \
    .trigger(processingTime='200ms') \  # Process every 200ms
    .foreachBatch(write_to_postgres) \
    .start()
```

**For HIGH THROUGHPUT (batch processing):**
```python
query = windowed_df \
    .writeStream \
    .trigger(processingTime='5000ms') \  # Process every 5 seconds
    .foreachBatch(write_to_postgres) \
    .start()
```

**For LIMITED RESOURCES:**
```python
spark = SparkSession.builder \
    .config("spark.streaming.kafka.maxRatePerPartition", "1000") \  # Lower from 10000
    .config("spark.executor.memory", "1g") \  # Lower from 2g
    .getOrCreate()
```

---

## Part 10: Monitoring & Debugging

### Monitoring Points

**1. Kafka Consumer Lag**
```sql
-- Check if Spark is keeping up with Kafka
SELECT COUNT(*) as messages_in_topic FROM kafka_queue
-- If lag increases over time: Spark is too slow
```

**2. PostgreSQL Insert Rate**
```sql
-- Monitor writes per minute
SELECT COUNT(*) FROM revenue_metrics 
WHERE window_start > NOW() - INTERVAL '1 minute'
```

**3. Spark Job Metrics**
```
Spark Master UI (http://localhost:9080):
├─ Running Applications → See active jobs
├─ Completed Applications → See finished jobs
├─ Executors → See resource usage
└─ Logs → See error messages
```

**4. Prometheus Metrics (if added)**
```
spark_job_duration_seconds
spark_job_success_total
spark_job_failure_total
spark_job_records_processed_total
```

### Common Issues & Solutions

| Issue | Symptom | Root Cause | Solution |
|-------|---------|-----------|----------|
| **Lag Building** | `kafka_consumer_lag_seconds` increasing | Spark too slow | Increase executors/cores |
| **Out of Memory** | `java.lang.OutOfMemoryError` | Too many aggregations | Reduce `maxRatePerPartition` |
| **Late Results** | Data not appearing in DB | Watermark too aggressive | Increase watermark delay |
| **Duplicate Data** | Same window written twice | Non-idempotent write | Add deduplication logic |
| **No Data** | Empty tables despite events | Kafka topic name wrong | Check `subscribe("topic_name")` |

---

## Part 11: Integration with Full System

### Event Flow Example: Complete Order

```
1. USER PLACES ORDER
   └─ Hits POST /orders on Order Service
   
2. ORDER SERVICE EMITS EVENT
   └─ Publishes to "order.created" topic
   
3. SPARK JOBS LISTEN
   Revenue Job: Ignores (not payment yet)
   Fraud Job: Notes order in fraud window
   Inventory Job: Ignores (not inventory)
   Cart Job: Starts 15-minute timer
   
4. PAYMENT SERVICE PROCESSES
   └─ Publishes to "payment.processed" topic
   
5. SPARK JOBS REACT
   Revenue Job: Includes in current 1-min window
   Fraud Job: Checks if suspicious pattern
   Inventory Job: Ignores
   Cart Job: Marks as completed (not abandoned)
   
6. WITHIN 1-3 SECONDS
   └─ Results appear in PostgreSQL:
      - revenue_metrics updated
      - fraud_alerts created (if suspicious)
      - cart_abandonment updated
      
7. EVERY 30 SECONDS
   └─ Prometheus exporter polls PostgreSQL:
      - Reads new rows
      - Exposes as metrics
      
8. GRAFANA DASHBOARD
   └─ Refreshes every 30s:
      - Shows updated metrics
      - Operators see real-time data
```

### Data Consistency Guarantees

```
At-most-once: Default (fast but can lose data)
At-least-once: With checkpoint (default, some duplicates possible)
Exactly-once: With idempotent writes (our goal)

Current Implementation:
- Checkpoints: At-least-once delivery from Spark
- PostgreSQL writes: UPSERT on (window_start, window_end) or similar
- Result: Effectively exactly-once semantics
```

---

## Summary

The Spark analytics layer processes Kafka events through 5 parallel streaming jobs, each with specific:

1. **Input source** (Kafka topics)
2. **Window strategy** (tumbling or sliding)
3. **Aggregation logic** (sums, counts, averages)
4. **Output table** (PostgreSQL)
5. **Use case** (business metrics)

All jobs run continuously in parallel, processing micro-batches with fault tolerance via checkpoints, and writing results to PostgreSQL for consumption by Prometheus/Grafana dashboards.

---

## Next Questions to Explore

1. Should we add custom metrics to track Spark job health?
2. Should we implement alerting based on Spark metrics (job failures, lag)?
3. Should we add more jobs (customer segmentation, RFM analysis, etc.)?
4. Should we add real-time dashboards for Spark job performance itself?
5. Should we optimize for lower latency (reduce window sizes)?
6. Should we add machine learning (anomaly detection, forecasting)?
