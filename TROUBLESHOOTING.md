# Troubleshooting Common Issues

## Quick Reference

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: No module named 'spark_session'` | Running job from wrong directory | Use helper script: `./scripts/spark/run-spark-job.sh job_name` |
| `permission denied: ./scripts/spark/run-spark-job.sh` | Scripts not executable | Run: `chmod +x scripts/*.sh` |
| `No module named 'requests'` | Mixing Conda and venv | Run: `conda deactivate` then `source .venv/bin/activate` |
| `redis.ResponseError` | Redis server not running | Run: `docker-compose up redis -d` |
| Port already in use | Service already running on port | Check: `lsof -i :PORT_NUMBER` |

---

## Issue 1: ModuleNotFoundError - spark_session

### Symptoms
```
Traceback (most recent call last):
  File "...cart_abandonment.py", line 95, in <module>
    from spark_session import get_spark_session, get_kafka_options
ModuleNotFoundError: No module named 'spark_session'
```

### Root Cause
Spark job files are in `analytics/jobs/` but `spark_session.py` is in `analytics/`.
Python cannot find the parent module when running from the job directory.

### Solution 1: Use Helper Script (Recommended) ✅
```bash
./scripts/spark/run-spark-job.sh cart_abandonment
# or
./scripts/spark/run-spark-job.sh fraud_detection
```

**What Success Looks Like:**
```
╔══════════════════════════════════════════════════════════════════╗
║  Submitting Spark Job: cart_abandonment
╚══════════════════════════════════════════════════════════════════╝

Job File: /opt/spark-apps/jobs/cart_abandonment.py
Spark Master: spark://spark-master:7077
Deploy Mode: client
...
INFO:spark_session:Spark session created for cart-abandonment
INFO:__main__:Starting streaming query for cart abandonment detection...
26/03/05 16:55:41 WARN ResolveWriteToStream: spark.sql.adaptive.enabled is not supported...
```

✅ **Success indicators:**
- "Spark session created" message appears
- "Starting streaming query" message appears
- Job continues running (streaming jobs run indefinitely)
- Monitor at: http://localhost:4041/ (or 4040, 4042 if ports taken)

### Solution 2: Run from Project Root
```bash
# From project root, with sys.path adjustment in job file:
.venv/bin/python analytics/jobs/cart_abandonment.py

# The job file should have:
import sys
sys.path.insert(0, '..')
from spark_session import get_spark_session, get_kafka_options
```

### Solution 3: Install Project as Package
```bash
# From project root
pip install -e .

# Then run from anywhere
python -m analytics.jobs.cart_abandonment
```

---

## Issue 2: Permission Denied - Script Not Executable

### Symptoms
```
zsh: permission denied: ./scripts/spark/run-spark-job.sh
bash: ./scripts/test-scenarios.sh: Permission denied
```

### Root Cause
Shell scripts don't have execute permission after being created or moved.

### Solution
```bash
# Make all scripts executable
chmod +x scripts/*.sh
chmod +x scripts/spark/*.sh

# Verify
ls -la scripts/spark/run-spark-job.sh
# Output should show: -rwxr-xr-x (notice the x's)

# Check individual script
file scripts/spark/run-spark-job.sh
# Output should show: shell script text executable
```

---

## Issue 3: ModuleNotFoundError - requests (Virtual Environment Conflict)

### Symptoms
```
ModuleNotFoundError: No module named 'requests'
```

When running with both `(base)` and `(.venv)` active.

### Root Cause
Anaconda base environment is interfering with Python venv.
The Python interpreter gets confused about which environment to use.

### Solution
```bash
# Deactivate Anaconda base first
conda deactivate

# Then activate venv
source .venv/bin/activate

# Verify you see (.venv) only, not (base)
# Prompt should look like: (.venv) tong@MacBook-Pro project %

# Now run your command
.venv/bin/python scripts/simulate-users.py --mode single
```

### Prevention
Disable auto-activation of Anaconda base:
```bash
conda config --set auto_activate_base false
source ~/.zshrc  # reload shell
```

---

## Issue 4: Redis Connection Error

### Symptoms
```
redis.exceptions.ConnectionError: Error 61 connecting to localhost:6379.
redis.ConnectionError: [Errno 61] Connection refused
```

### Root Cause
Redis server is not running in Docker.

### Solution
```bash
# Start Redis
docker-compose up redis -d

# Verify it's running
docker-compose ps redis
# Status should show: Up

# Test connection
docker-compose exec redis redis-cli ping
# Response should be: PONG
```

---

## Issue 5: Port Already in Use

### Symptoms
```
Address already in use: ('0.0.0.0', 8080)
ERROR: for kafka-broker-1  Cannot start service kafka-broker-1: driver failed
```

### Root Cause
Another process is using the port, or a previous container didn't fully stop.

### Solution
```bash
# Find what's using the port
lsof -i :8080          # For Kafka UI
lsof -i :4040          # For Spark UI
lsof -i :5432          # For PostgreSQL

# Kill the process (if needed)
kill -9 PID_NUMBER

# Or stop all Docker containers and restart
docker-compose down
docker-compose up -d

# Check specific service
docker-compose logs kafka-broker-1
```

---

## Issue 6: Spark Job Runs but No Output

### Symptoms
- Job starts successfully
- No errors in logs
- But data doesn't appear in PostgreSQL or no results shown

### Root Cause
- Kafka topics are empty (no events flowing)
- Job is waiting for events (streaming jobs never "finish")
- Checkpoint contains old state

### Solution
```bash
# 1. Verify Kafka has data
docker-compose exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-servers localhost:9092 \
  --topic cart.item_added \
  --from-beginning \
  --max-messages 5

# 2. Generate test data
./scripts/simulate-users.py --mode wave --users 5

# 3. Check PostgreSQL results
docker-compose exec postgres psql -U postgres -d kafka_ecom \
  -c "SELECT COUNT(*) FROM cart_abandonment;"

# 4. Monitor Spark UI
open http://localhost:4040/

# 5. Clear checkpoint if needed
rm -rf /tmp/checkpoints/cart-abandonment
# Then restart job
```

---

## Issue 7: Database Connection Issues

### Symptoms
```
ERROR: can't initialize PoolManager with
java.io.IOException: Cannot run program "psql"
```

### Root Cause
PostgreSQL service is down or credentials are wrong.

### Solution
```bash
# Verify PostgreSQL is running
docker-compose ps postgres
# Status should show: Up

# Test connection
docker-compose exec postgres psql -U postgres -c "SELECT 1;"
# Response should be: 1

# Check credentials in docker-compose.yml
# Default: user=postgres, password=postgres, database=kafka_ecom

# If wrong, update and restart
docker-compose down
docker-compose up -d postgres
```

---

## Issue 8: Event Not Flowing Through System

### Symptoms
- Order created but no notification email
- Event in Kafka but not in database
- Service processing stops

### Root Cause
- Topic subscription wrong
- Event format doesn't match schema
- Consumer group has lag

### Solution
```bash
# 1. Check topic subscriptions
docker-compose logs notification-service | grep -i "subscribe\|topic"

# 2. Check consumer lag
docker-compose exec kafka-broker-1 kafka-consumer-groups.sh \
  --bootstrap-servers localhost:9092 \
  --group notification-service-group \
  --describe

# 3. Verify event format
docker-compose exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-servers localhost:9092 \
  --topic order.cancelled \
  --from-beginning \
  --max-messages 1

# 4. Check service logs for parsing errors
docker-compose logs notification-service | grep -i "error\|exception"

# 5. Reset consumer group if needed
docker-compose exec kafka-broker-1 kafka-consumer-groups.sh \
  --bootstrap-servers localhost:9092 \
  --group notification-service-group \
  --reset-offsets \
  --to-earliest \
  --execute
```

---

## Issue 9: How to Monitor Running Spark Job

### Symptoms
- Job is running but you want to check status/logs
- Need to see SQL execution plans and metrics
- Want to monitor data flow into PostgreSQL

### Solution

**1. Monitor via Spark UI (Real-time metrics):**
```bash
open http://localhost:4041/
# or 4040, 4042, 4043 if ports taken
```

**What you'll see:**
- Jobs tab: Running stages and tasks
- SQL/DataFrame tab: Spark SQL execution plans
- Streaming tab: Streaming query statistics
- Executors tab: Memory/CPU usage by worker

**2. Check PostgreSQL results (in another terminal):**
```bash
docker-compose exec postgres psql -U postgres -d kafka_ecom \
  -c "SELECT COUNT(*) as abandoned_carts FROM cart_abandonment;"
```

**3. View job logs:**
```bash
docker-compose logs spark-worker-1 | grep "cart_abandonment\|ERROR"
```

**4. Stop the job (when ready):**
```bash
# Press Ctrl+C in the terminal where job is running
# This cleanly shuts down the streaming query
```

---

- [ ] Running from project root directory?
- [ ] Virtual environment activated? `.venv/bin/python` or `source .venv/bin/activate`
- [ ] Scripts have execute permission? `chmod +x scripts/*.sh`
- [ ] Docker services running? `docker-compose ps`
- [ ] Correct Python/venv version? `which python` or `python --version`
- [ ] No Anaconda interference? `conda deactivate` first
- [ ] Kafka has data? Check with `kafka-console-consumer.sh`
- [ ] PostgreSQL accessible? `docker-compose exec postgres psql ...`
- [ ] No port conflicts? `lsof -i :PORT`

---

## Getting Help

1. **Check relevant README files:**
   - Main: `README.md`
   - Scripts: `scripts/README.md`
   - Spark: `SPARK_ANALYTICS_DEEP_DIVE.md`

2. **Review logs:**
   ```bash
   docker-compose logs SERVICE_NAME
   docker-compose logs SERVICE_NAME --since 5m  # Last 5 minutes
   docker-compose logs SERVICE_NAME -f          # Follow (tail -f)
   ```

3. **Check system resources:**
   ```bash
   docker stats                          # CPU/memory usage
   docker-compose ps                     # All services status
   docker-compose logs --timestamps      # With timestamps
   ```

4. **Reset everything (nuclear option):**
   ```bash
   docker-compose down
   rm -rf /tmp/checkpoints/*
   docker-compose up -d
   ```
