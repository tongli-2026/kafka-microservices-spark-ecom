# Spark Jobs - Complete Operational Guide

> **Status:** ✅ FULLY OPERATIONAL  
> **Last Updated:** March 11, 2026  
> **System Version:** Spark 3.5.0, PySpark 3.5.0

## ⚡ TL;DR (Copy-Paste Commands)

```bash
# Check status
./scripts/spark/quick-status.sh

# Start all jobs
./scripts/spark/start-spark-jobs.sh

# Restart a job
./scripts/spark/restart-job.sh <job_name>

# Generate test data
./scripts/simulate-users.py --mode single

# View results
docker-compose exec postgres psql -U postgres -d kafka_ecom -c "SELECT COUNT(*) FROM cart_abandonment;"

# Open dashboard
open http://localhost:9080
```

## Table of Contents

1. [Quick Start](#quick-start)
2. [Job Status](#job-status)
3. [Commands Reference](#commands-reference)
4. [Job Scheduling](#job-scheduling)
5. [Monitoring](#monitoring)
6. [Testing & Data Generation](#testing--data-generation)
7. [Troubleshooting](#troubleshooting)
8. [Architecture](#architecture)
9. [Background: How This Was Fixed](#background-how-this-was-fixed)

---

## Quick Start

### Check System Status (Most Common Command)
```bash
./scripts/spark/quick-status.sh
```
Expected output: ✅ SYSTEM OPERATIONAL with 3-4 jobs running

### Start All Streaming Jobs
```bash
./scripts/spark/start-spark-jobs.sh
```

### Monitor in Real-Time
```bash
watch -n 5 './scripts/spark/quick-status.sh'
```

### Generate Test Data (Quick Test)
```bash
./scripts/simulate-users.py --mode single
```

### View Spark Dashboard
- **Master UI:** http://localhost:9080
- **Driver UI:** http://localhost:4040 (while job running)

---

## Job Status

### 📊 5 Total Jobs

#### Streaming Jobs (Real-Time Processing)

| Job | Status | Function | Batch Interval |
|-----|--------|----------|-----------------|
| **fraud_detection** | ✅ RUNNING | Real-time fraud pattern detection | 10 seconds |
| **revenue_streaming** | ✅ RUNNING | Revenue aggregation by product | 1 minute windows |
| **cart_abandonment** | ✅ RUNNING | Detect abandoned shopping carts | 5 minute windows |
| **operational_metrics** | ⏸️ ON-DEMAND | System health metrics | Per-batch |

#### Batch Job (Scheduled)

| Job | Status | Schedule | Function |
|-----|--------|----------|----------|
| **inventory_velocity** | ⏰ HOURLY | Hourly (via cron) | Product sales velocity |

### Job File Locations
```
analytics/jobs/
├── fraud_detection.py
├── revenue_streaming.py
├── cart_abandonment.py
├── inventory_velocity.py
└── operational_metrics.py
```

---

## Commands Reference

### 🎯 Most Common

```bash
# Check all jobs
./scripts/spark/quick-status.sh

# Start all jobs
./scripts/spark/start-spark-jobs.sh

# Restart a specific job
./scripts/spark/restart-job.sh <job_name>

# Generate test data
./scripts/simulate-users.py --mode single
```

### 🔧 Job Management

```bash
# Start single job
./scripts/spark/run-spark-job.sh <job_name>

# Restart job (clean checkpoint + restart)
./scripts/spark/restart-job.sh <job_name>

# Clean checkpoint for job
./scripts/spark/cleanup-checkpoints.sh <job_name>

# Clean ALL checkpoints
./scripts/spark/cleanup-checkpoints.sh
```

### 📋 Job Names (Use in Above Commands)
```
fraud_detection
revenue_streaming
cart_abandonment
inventory_velocity
operational_metrics
```

### 📊 Docker Management

```bash
# Start all containers
docker-compose up -d

# Stop all containers
docker-compose stop

# Full reset (careful - removes containers)
docker-compose down -v

# Check container status
docker-compose ps
```

### 📖 Check Logs

```bash
# Master logs
docker logs spark-master | tail -50

# Worker 1 logs
docker logs spark-worker-1 | tail -50

# Worker 2 logs
docker logs spark-worker-2 | tail -50

# Follow logs (real-time)
docker logs -f spark-worker-1
```

---

## Job Scheduling

### ⏰ Inventory Velocity Scheduler (Cron Job)

The `inventory_velocity` job runs **automatically every hour** via cron to compute product sales velocity rankings from PostgreSQL orders data.

#### Schedule Configuration
- **Frequency:** Every hour on the hour (00:00, 01:00, 02:00, etc.)
- **Script:** `/scripts/schedule-inventory-velocity.sh`
- **Logs:** `/tmp/inventory_velocity_cron.log`

#### How It Works

1. **Cron Trigger** (every hour)
   ```
   0 * * * * /Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/schedule-inventory-velocity.sh
   ```

2. **Scheduler Script** (`schedule-inventory-velocity.sh`)
   - Changes to project directory
   - Runs `./scripts/spark/run-spark-job.sh inventory_velocity`
   - Logs all output and errors

3. **Spark Job** (`analytics/jobs/inventory_velocity.py`)
   - Reads all FULFILLED orders from PostgreSQL
   - Expands items JSON array to individual products
   - Aggregates by 1-hour windows
   - Ranks top 10 products by units sold
   - **Overwrites** results in `inventory_velocity` table (prevents duplicates from repeated runs)
   - Note: Uses `mode("overwrite")` since job re-aggregates all historical data each run

#### Data Management

**Important:** The job uses `mode("overwrite")` which means:
- ✅ Each run replaces old data (no duplicates)
- ✅ Always has fresh aggregates from all historical orders
- ⚠️ Previous results are overwritten (not appended)
- ✓ This is correct since we re-aggregate ALL historical data each run

#### Scheduling Commands

##### View Current Cron Job
```bash
crontab -l
```

##### Edit Cron Settings
```bash
crontab -e
```

##### Change Schedule
Modify the cron expression in crontab:
- `0 * * * *` = Every hour (default)
- `0 */2 * * *` = Every 2 hours
- `0 9 * * *` = Daily at 9 AM
- `0 0 * * 0` = Weekly on Sunday

#### Monitoring Scheduled Jobs

##### Check Last Run
```bash
tail -50 /tmp/inventory_velocity_cron.log
```

##### Check Latest Data
```bash
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT COUNT(*), MAX(window_start) FROM inventory_velocity;"
```

##### View Top Products from Latest Hour
```bash
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT window_start, product_id, units_sold, revenue, velocity_rank 
   FROM inventory_velocity 
   WHERE window_start = (SELECT MAX(window_start) FROM inventory_velocity)
   ORDER BY velocity_rank ASC LIMIT 10;"
```

#### Manual Execution

To test or manually run the scheduled job:

```bash
# Option 1: Via scheduler script
/Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/schedule-inventory-velocity.sh

# Option 2: Direct job execution
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom
./scripts/spark/run-spark-job.sh inventory_velocity
```

#### Troubleshooting Scheduled Jobs

##### Job Not Running?

1. Verify cron job is installed:
   ```bash
   crontab -l
   ```
   You should see:
   ```
   0 * * * * /Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/schedule-inventory-velocity.sh
   ```

2. Check macOS cron daemon status:
   ```bash
   ps aux | grep cron
   # Should show output like: /usr/sbin/cron
   ```

3. Check the actual job logs:
   ```bash
   tail -100 /tmp/inventory_velocity_cron.log
   ```

##### Job Failed?

Look at the error in `/tmp/inventory_velocity_cron.log` and check:
- PostgreSQL connection (is postgres container running?)
- Spark cluster connectivity (is Spark running?)
- Disk space (is /tmp full?)

**Note on Docker/Environment:**
The scheduler script sources your shell profile (`~/.zshrc` or `~/.bash_profile`) to ensure cron has access to Docker and other commands. If cron still can't find Docker, update your crontab:
```bash
crontab -e
```
And modify the line to:
```bash
0 * * * * export PATH="/usr/local/bin:$PATH" && /Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/schedule-inventory-velocity.sh
```

---

## Monitoring

### 🌐 Web Dashboards

| URL | Purpose | When to Use |
|-----|---------|------------|
| **http://localhost:9080** | Spark Master Dashboard | View cluster health, applications, workers |
| **http://localhost:4040** | Spark Driver UI | Job details, stages, metrics (while running) |
| **http://localhost:8080** | Kafka UI | Topic inspection, message browsing |
| **http://localhost:5050** | pgAdmin | PostgreSQL admin (if available) |

### 📊 Monitor Specific Metrics

```bash
# Watch status every 5 seconds
watch -n 5 './scripts/spark/quick-status.sh'

# View checkpoint storage usage
du -sh data/checkpoints/

# See Docker resource usage
docker stats

# Check number of jobs running per container
for c in spark-master spark-worker-1 spark-worker-2; do
  echo "=== $c ==="; 
  docker exec $c pgrep -f "\.py" | wc -l
done
```

### 🔍 Verify Data Flow

```bash
# Check Kafka topics
docker exec kafka-1 kafka-topics.sh --list --bootstrap-server localhost:9092

# View messages in topic
docker exec kafka-1 kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic cart.item_added --from-beginning | head -20

# Check PostgreSQL results
docker-compose exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT COUNT(*) as count FROM cart_abandonment;"
```

---

## Testing & Data Generation

### 🧪 Test Modes

#### Light Test - Single User (~10 seconds)
```bash
./scripts/simulate-users.py --mode single
```
**Use when:** Quick sanity check, testing job startup

#### Wave Test - Multiple Users (~30-60 seconds)
```bash
./scripts/simulate-users.py --mode wave --users 10
```
**Use when:** Testing with realistic load, verifying job processing

#### Abandoned Cart Test - With Abandonment (~30-60 seconds)
```bash
./scripts/simulate-users.py --mode wave --users 10 --abandonment-rate 0.3
```
**Result:** 3 users abandon, 7 complete purchase  
**Use when:** Testing abandoned cart detection

#### Load Test - Continuous (~5 minutes)
```bash
./scripts/simulate-users.py --mode continuous --duration 300 --interval 30 --users 5
```
**Result:** ~50 total users, ~30-40 events/min  
**Use when:** Baseline performance testing

#### Heavy Load - Sustained Load (~5 minutes)
```bash
./scripts/simulate-users.py --mode continuous --duration 300 --interval 15 --users 20
```
**Result:** ~400 total users, ~120-160 events/min  
**Use when:** Testing with realistic sustained traffic

### 📈 Workflow: Generate & Verify

```bash
# Terminal 1: Monitor status
watch -n 5 './scripts/spark/quick-status.sh'

# Terminal 2: View logs  
docker logs -f spark-worker-1

# Terminal 3: Generate test data
./scripts/simulate-users.py --mode continuous --duration 300 --interval 30

# Terminal 4: Query results (after ~2 minutes)
docker-compose exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT COUNT(*) as abandoned_carts FROM cart_abandonment;"
```

---

## Troubleshooting

### ❌ Problem: Job fails with exit code 137

**Cause:** Process killed (usually memory or timeout)

**Solution:**
```bash
# Option 1: Clean checkpoint and restart
./scripts/spark/restart-job.sh <job_name>

# Option 2: Full cleanup
./scripts/spark/cleanup-checkpoints.sh <job_name>
./scripts/spark/run-spark-job.sh <job_name>
```

### ❌ Problem: "No products available" from simulate-users.py

**Cause:** Inventory service not running

**Solution:**
```bash
# Start all services
docker-compose up -d

# Verify inventory service is running
docker-compose ps | grep inventory

# Check if products endpoint works
curl http://localhost:8004/products
```

### ❌ Problem: PostgreSQL tables are empty after running test

**Cause:** Data not yet processed or jobs not running

**Solution:**
1. Verify jobs are running: `./scripts/spark/quick-status.sh`
2. Wait 60 seconds for streaming to process
3. Verify data in Kafka: `docker exec kafka-1 kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic cart.item_added --from-beginning | head -5`
4. Check PostgreSQL: `docker-compose exec postgres psql -U postgres -d kafka_ecom -c "SELECT * FROM cart_abandonment LIMIT 5;"`

### ❌ Problem: Jobs won't consume Kafka messages

**Cause:** Kafka not running, topics don't exist, or wrong broker address

**Solution:**
```bash
# Ensure Kafka is running
docker-compose ps | grep kafka

# Create topics if missing
docker exec kafka-1 kafka-topics.sh --create --bootstrap-server localhost:9092 \
  --topic cart.item_added --partitions 3 --replication-factor 1

# Verify topics exist
docker exec kafka-1 kafka-topics.sh --list --bootstrap-server localhost:9092
```

### ❌ Problem: "ClassNotFoundException: org.apache.spark.kafka010..."

**Cause:** Kafka connector JAR not loading (ALREADY FIXED)

**Solution:** System now uses Maven package resolution. No action needed.
- Packages automatically downloaded: `org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0`
- PostgreSQL JDBC auto-loaded: `org.postgresql:postgresql:42.7.1`

### ❌ Problem: Checkpoint corruption blocks restart

**Cause:** Previous job crashed, checkpoint files corrupted

**Solution:**
```bash
# Clean specific job checkpoint
./scripts/spark/cleanup-checkpoints.sh <job_name>

# Clean ALL checkpoints (if multiple jobs affected)
./scripts/spark/cleanup-checkpoints.sh

# Restart job
./scripts/spark/run-spark-job.sh <job_name>
```

### 🔍 Debug Commands

```bash
# Check if Docker containers are running
docker-compose ps

# View Spark logs for errors
docker logs spark-worker-1 | grep -i error

# Test connectivity to Kafka
docker exec spark-master ping kafka-1

# Test PostgreSQL connection
docker exec spark-master psql -h postgres -U postgres -d kafka_ecom -c "SELECT 1;"

# Check checkpoint directory
ls -la data/checkpoints/

# View container resource usage
docker stats --no-stream

# Get Spark version in container
docker exec spark-master spark-submit --version
```

---

## Architecture

### 🏗️ System Components

```
User Machine (Your Laptop)
    ↓
simulate-users.py (Test Data Generator)
    ↓ (HTTP requests to localhost:8001-8005)
Microservices (Docker)
    ├── Cart Service (8001)
    ├── Order Service (8002)
    ├── Payment Service (8003)
    ├── Inventory Service (8004)
    └── Notification Service (8005)
    ↓ (Publishes events to)
Kafka Cluster (3 Brokers in Docker)
    ├── cart.item_added
    ├── cart.checkout_initiated
    ├── order.created
    ├── payment.processed
    ├── inventory.reserved
    └── notification.send
    ↓ (Consumed by)
Spark Cluster (Docker)
    ├── spark-master (Cluster Manager)
    ├── spark-worker-1 (Executor)
    └── spark-worker-2 (Executor)
    ↓ (Runs Jobs)
    ├── fraud_detection → PostgreSQL fraud_detection table
    ├── revenue_streaming → PostgreSQL revenue_streaming table
    ├── cart_abandonment → PostgreSQL cart_abandonment table
    ├── operational_metrics → PostgreSQL operational_metrics table
    └── inventory_velocity → PostgreSQL inventory_velocity table
    ↓ (Results stored in)
PostgreSQL Database (Docker)
    └── kafka_ecom database
```

### 📡 Data Flow Example: Cart Abandonment

```
User adds items to cart
    ↓
Cart Service publishes: cart.item_added
    ↓
Kafka receives event (timestamp: T+0)
    ↓
Spark streaming job consumes event
    ↓
Watermark: 30 minutes
    ↓
User closes browser (NO checkout_initiated event)
    ↓
At T+30min: Watermark reaches the event
    ↓
Spark detects: item_added but NO checkout_initiated
    ↓
Writes to PostgreSQL: cart_abandonment table
    ↓
Result available for queries
```

### 🔧 Resource Allocation

```
Driver Memory:        2GB
Executor Memory:      2GB per executor
Executor Cores:       4 total
Spark Cluster:        3 nodes (1 master, 2 workers)
Checkpoint Storage:   ./data/checkpoints/ (typically 10-100MB)
```

---

## Background: How This Was Fixed

### 📝 The Problem (Before)

**User reported:** "Every day when I want to start the spark job, new problems come in for the same maven and jar issues"

**Root causes:**
1. ❌ Manual JAR management (pre-downloaded, often stale)
2. ❌ Version mismatches (Spark 3.5.1 vs 3.5.0)
3. ❌ Missing transitive dependencies
4. ❌ No automated checkpoint recovery
5. ❌ No status monitoring tools

### ✅ The Solution (After)

| Issue | Before | After |
|-------|--------|-------|
| JAR Management | Manual files | Maven auto-resolution |
| Version Alignment | Mixed (3.5.0 vs 3.5.1) | Unified (3.5.0 everywhere) |
| Dependencies | Missing transitive deps | Automatic with Maven |
| Checkpoint Corruption | Manual deletion | `cleanup-checkpoints.sh` script |
| Job Restart | Kill on one node | Kill on all 3 nodes |
| Status Monitoring | Manual Docker inspect | `quick-status.sh` script |
| Documentation | Scattered | This guide |

### 🔨 Changes Made

#### 1. Docker Image (`Dockerfile.spark`)
- ✅ Base image: `apache/spark:3.5.0` (was 3.5.1)
- ✅ PySpark: 3.5.0 (now matches base image)
- ✅ Removed manual JAR downloads
- ✅ Installed required Python packages

#### 2. Job Submission (`scripts/spark/run-spark-job.sh`)
- ✅ Uses `--packages` flag instead of `--jars`
- ✅ Maven coordinates: `org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.1`
- ✅ Auto-creates checkpoint directories

#### 3. Checkpoint Recovery (`scripts/spark/cleanup-checkpoints.sh`)
- ✅ NEW SCRIPT: Kills all jobs, removes corrupted checkpoints
- ✅ Works on all 3 containers
- ✅ Can clean specific job or all jobs

#### 4. Job Restart (`scripts/spark/restart-job.sh`)
- ✅ ENHANCED: Kills on all 3 containers (not just worker-1)
- ✅ Removes specific job checkpoints
- ✅ Calls run-spark-job.sh to restart

#### 5. Status Monitoring (`scripts/spark/quick-status.sh`)
- ✅ NEW SCRIPT: Fast system status check
- ✅ Shows 4 streaming + 1 batch job
- ✅ Checks infrastructure (Kafka, PostgreSQL)
- ✅ Color-coded output for clarity

#### 6. Documentation (This File)
- ✅ Consolidated all operational guidance
- ✅ Clear commands with examples
- ✅ Troubleshooting for common issues
- ✅ Architecture explanation

### 📊 Result

**Before:** Daily failures, manual JAR management, no recovery automation  
**After:** Fully operational, Maven-driven, automated recovery, status monitoring

---

## Daily Operations Checklist

### 🌅 Morning Startup
```bash
# 1. Start all containers
docker-compose up -d

# 2. Start all Spark jobs
./scripts/spark/start-spark-jobs.sh

# 3. Verify all running
./scripts/spark/quick-status.sh

# 4. Check Spark UI
open http://localhost:9080
```

### 📊 During Day
```bash
# Monitor status
./scripts/spark/quick-status.sh

# Generate test data (if needed)
./scripts/simulate-users.py --mode continuous --duration 300 --interval 30

# View logs
docker logs -f spark-worker-1
```

### 🌙 Evening Shutdown
```bash
# Graceful stop (keeps state)
docker-compose stop

# Or full cleanup (if needed)
docker-compose down
```

---

## Performance Notes

### 📈 Expected Throughput

| Scenario | Users/Wave | Frequency | Total Events/Min | Status |
|----------|-----------|-----------|-----------------|--------|
| Light Test | 5 | Every 30s | 30-40 | ✅ Stable |
| Medium Test | 20 | Every 15s | 120-160 | ✅ Stable |
| Heavy Test | 50 | Every 10s | 300-400 | ⚠️ Monitor |
| Stress Test | 100 | Every 5s | 600-800 | ⚠️ Watch memory |

### ⚠️ Monitoring Points

- **Batch lag:** Normal 10-60 second lag (watermark-based)
- **Memory:** Monitor with `docker stats`
- **Disk:** Checkpoint directory grows slowly (typically <500MB)
- **Network:** Kafka should keep up (3 brokers enough)

### 🔧 Tuning (Advanced)

To adjust memory, edit `scripts/spark/run-spark-job.sh`:
```bash
--driver-memory 4g      # Increase from 2g if needed
--executor-memory 4g    # Increase from 2g if needed
```

---

## Support & Quick Reference

### 📞 Common Questions

**Q: How do I know if jobs are running?**  
A: Run `./scripts/spark/quick-status.sh`

**Q: Where are the results stored?**  
A: PostgreSQL database `kafka_ecom`, tables: `cart_abandonment`, `fraud_detection`, etc.

**Q: How do I reset everything?**  
A: `docker-compose down -v && docker-compose up -d && ./scripts/spark/start-spark-jobs.sh`

**Q: Can I run just one job?**  
A: Yes: `./scripts/spark/run-spark-job.sh <job_name>`

**Q: What if a job crashes?**  
A: Run `./scripts/spark/restart-job.sh <job_name>`

**Q: How often should I clean checkpoints?**  
A: Only when corrupted (if job won't start). Normal cleanup: `./scripts/spark/cleanup-checkpoints.sh <job_name>`

### 📚 Key Files Location

| What | Where |
|------|-------|
| Job Code | `analytics/jobs/` |
| Spark Config | `analytics/spark_session.py` |
| Scripts | `scripts/spark/` |
| Docker Setup | `docker-compose.yml`, `Dockerfile.spark` |
| Checkpoints | `./data/checkpoints/` |
| This Guide | `SPARK_OPERATIONS.md` |

---

## System Status History

| Date | Status | Notes |
|------|--------|-------|
| 2026-03-11 | ✅ OPERATIONAL | Maven fix implemented, all 5 jobs verified |
| Previous | ⚠️ DAILY ISSUES | JAR/Maven problems, version conflicts |

---

**Last Updated:** March 11, 2026  
**Maintained By:** System  
**Version:** 1.0 - Production Ready
