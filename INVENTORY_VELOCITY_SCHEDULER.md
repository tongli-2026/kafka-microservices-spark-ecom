# Inventory Velocity Scheduler

## Overview
The `inventory_velocity` job runs **every hour** via cron to compute product sales velocity rankings from PostgreSQL orders data.

## Schedule
- **Frequency:** Every hour on the hour (00:00, 01:00, 02:00, etc.)
- **Script:** `/scripts/schedule-inventory-velocity.sh`
- **Logs:** `/tmp/inventory_velocity_cron.log`

## How It Works

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

## Data Management

**Important:** The job uses `mode("overwrite")` which means:
- ✅ Each run replaces old data (no duplicates)
- ✅ Always has fresh aggregates from all historical orders
- ⚠️ Previous results are overwritten (not appended)
- ✓ This is correct since we re-aggregate ALL historical data each run

## Monitoring

### Check Last Run
```bash
tail -50 /tmp/inventory_velocity_cron.log
```

### Check Latest Data
```bash
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT COUNT(*), MAX(window_start) FROM inventory_velocity;"
```

### View Top Products from Latest Hour
```bash
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT window_start, product_id, units_sold, revenue, velocity_rank 
   FROM inventory_velocity 
   WHERE window_start = (SELECT MAX(window_start) FROM inventory_velocity)
   ORDER BY velocity_rank ASC LIMIT 10;"
```

## Cron Configuration

### View Current Cron Job
```bash
crontab -l
```

### Edit Cron Settings
```bash
crontab -e
```

### Change Schedule
Modify the cron expression in crontab:
- `0 * * * *` = Every hour
- `0 */2 * * *` = Every 2 hours
- `0 9 * * *` = Daily at 9 AM
- `0 0 * * 0` = Weekly on Sunday

## Troubleshooting

### Job Not Running?
1. Verify cron is installed and shows your job:
   ```bash
   crontab -l
   ```
   You should see:
   ```
   0 * * * * /Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/schedule-inventory-velocity.sh
   ```

2. Check macOS cron daemon status:
   ```bash
   # Note: launchctl won't show cron, but you can verify it's running with:
   ps aux | grep cron
   # Should show output like: /usr/sbin/cron
   ```

3. Check the actual job logs:
   ```bash
   tail -100 /tmp/inventory_velocity_cron.log
   ```

### Job Failed?
Look at the error in `/tmp/inventory_velocity_cron.log` and check:
- PostgreSQL connection (is postgres container running?)
- Spark cluster connectivity (is Spark running?)
- Disk space (is /tmp full?)

**Note on Docker/Environment:**
The scheduler script sources your shell profile (`~/.zshrc` or `~/.bash_profile`) to ensure cron has access to Docker and other commands. If cron still can't find Docker, add this to your crontab:
```bash
crontab -e
```
And update the line to:
```bash
0 * * * * export PATH="/usr/local/bin:$PATH" && /Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/schedule-inventory-velocity.sh
```

## Manual Run
To test or manually run the job:
```bash
/Users/tong/KafkaProjects/kafka-microservices-spark-ecom/scripts/schedule-inventory-velocity.sh
```

Or directly:
```bash
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom
./scripts/spark/run-spark-job.sh inventory_velocity
```
