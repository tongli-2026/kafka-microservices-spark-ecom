# Testing Operational Metrics Job

## Current Status

The `operational_metrics.py` job is fully implemented but has a **known issue with resource contention** when writing to PostgreSQL while the microservices are under load.

**Problem:**
- The Spark job's psycopg2 database writes can block the Docker container network
- This causes timeouts (5s) for HTTP requests from simulate-users.py
- Kafka brokers also timeout during heavy Spark write operations

## Solution

### Option 1: Run Spark Job Separately (Recommended for Testing)

**Step 1: Test microservices WITHOUT Spark job**
```bash
# Terminal 1: Run user simulator
source .venv/bin/activate
./scripts/simulate-users.py --mode continuous --duration 300 --users 5
```

**Step 2: In another terminal, run Spark job (after users stop)**
```bash
./scripts/spark/run-spark-job.sh operational_metrics
```

This avoids network contention and lets each component work independently.

### Option 2: Run Spark Job in Separate Spark Cluster (Production)

For production, deploy the Spark job to a separate Spark cluster (not Docker Compose) that writes metrics asynchronously.

## Testing Checklist

### Unit Tests
- [ ] Test window aggregation logic
- [ ] Test status determination (HEALTHY/WARNING/CRITICAL thresholds)
- [ ] Test JSON serialization for services_checked

### Integration Tests
```bash
# 1. Start Kafka and PostgreSQL
docker-compose up -d postgres kafka-broker-1 kafka-broker-2 kafka-broker-3

# 2. Wait 10 seconds for brokers to start
sleep 10

# 3. Send test events to Kafka
kafka-console-producer --broker-list localhost:9092 --topic order.created
# Type: {"order_id": "123"}
# (Ctrl+C to exit)

# 4. Run Spark job
./scripts/spark/run-spark-job.sh operational_metrics

# 5. Verify data in PostgreSQL
psql -h localhost -U postgres -d kafka_ecom -c "SELECT * FROM operational_metrics LIMIT 10;"
```

### Performance Tests
```bash
# Generate continuous load
./scripts/simulate-users.py --mode continuous --duration 300 --users 10

# While running, check Spark metrics
open http://localhost:4040

# After simulation, query results
psql -h localhost -U postgres -d kafka_ecom \
  -c "SELECT window_start, metric_value, status FROM operational_metrics ORDER BY window_start DESC LIMIT 20;"
```

## Expected Output

```
window_start         │ metric_value │ status
─────────────────────┼──────────────┼─────────
2026-03-10 23:55:00  │ 9500         │ HEALTHY
2026-03-10 23:56:00  │ 8200         │ HEALTHY
2026-03-10 23:57:00  │ 4500         │ CRITICAL
```

## Monitoring

### Spark UI
```
http://localhost:4040/
```
Monitor:
- Batch processing time
- Number of batches processed
- Task success/failure rates

### PostgreSQL Metrics
```sql
-- Check all metrics
SELECT * FROM operational_metrics;

-- Find critical metrics
SELECT * FROM operational_metrics WHERE status = 'CRITICAL' ORDER BY window_start DESC;

-- Count events by status
SELECT status, COUNT(*) as count FROM operational_metrics GROUP BY status;
```

### Kafka Topics
```bash
# Check topic offset lag
docker-compose exec kafka-broker-1 kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --group operational-metrics \
  --describe
```

## Troubleshooting

### Issue: "Column services_checked is of type jsonb but expression is of type character varying"

**Solution:** The SQL INSERT now uses explicit CAST:
```sql
VALUES (..., %s::jsonb)
```

### Issue: Spark job hangs or times out

**Solution:** Increase Spark memory allocation in docker-compose.yml:
```yaml
spark-master:
  environment:
    - SPARK_DRIVER_MEMORY=4G
    - SPARK_EXECUTOR_MEMORY=4G
```

### Issue: "No such table: operational_metrics"

**Solution:** Ensure PostgreSQL schema is initialized:
```bash
psql -h localhost -U postgres -d kafka_ecom -f db-init.sql
```

## Next Steps

1. ✅ Fix JSONB serialization issue (DONE - using ::jsonb cast)
2. ✅ Add trigger timing (DONE - added 10s processing trigger)
3. ⏳ Performance optimization: Use batch inserts instead of row-by-row
4. ⏳ Add more metrics: success_rate, latency, error_rate
5. ⏳ Create dashboard visualization in Grafana
6. ⏳ Set up alerting for CRITICAL metrics
