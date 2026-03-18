# Scripts Directory

This directory contains utility and testing scripts for the Kafka E-Commerce Microservices project.

## Structure

```
scripts/
├── 🧪 Testing & Simulation
│   ├── simulate-users.py              # User behavior simulation (1 or continuous mode)
│   ├── test-scenarios.sh              # Test specific order scenarios
│   ├── test-complete-workflow.sh      # Complete workflow test (all services)
│   ├── validate-metrics.sh            # Validate monitoring/metrics setup
│   └── view-carts.py                  # View active Redis shopping carts with TTL
│
├── 🧹 Database & Kafka Management
│   ├── clean-database.sh              # Clean/reset PostgreSQL tables
│   ├── clean-kafka.sh                 # Clean/reset Kafka topics and data
│   ├── auto-refill-inventory.py       # Auto-refill inventory for load tests
│   ├── kill-auto-refill.sh            # Stop the auto-refill inventory service
│   ├── dashboard-sync.sh              # Sync Grafana dashboards
│   └── schedule-inventory-velocity.sh # Schedule hourly inventory velocity job (cron utility)
│
├── ⚡ Spark Job Management
│   └── spark/
│       ├── start-spark-jobs.sh        # Start all Spark jobs in background
│       ├── run-spark-job.sh           # Run specific job (cart_abandonment, etc)
│       ├── restart-job.sh             # Restart a specific job (kill + restart fresh)
│       ├── kill-spark-jobs.sh         # Stop all or specific Spark jobs (preserves checkpoints)
│       ├── monitor-spark-jobs.sh      # Monitor running Spark jobs
│       ├── quick-status.sh            # Quick status check of Spark jobs
│       └── cleanup-checkpoints.sh     # Clean Spark checkpoints (kill + delete state)
│
└── README.md                          # This file
```

## Usage

### Testing & Simulation

**Simulate user behavior** (browse → cart → checkout → payment):
```bash
# Single user test
.venv/bin/python scripts/simulate-users.py --mode single

# Continuous load test (20 users for 5 minutes)
.venv/bin/python scripts/simulate-users.py --mode continuous --users 20 --duration 300
```

**View active shopping carts**:
```bash
.venv/bin/python scripts/view-carts.py
```

**Test specific scenarios**:
```bash
bash scripts/test-scenarios.sh 10
```

**Run complete workflow test** (all services end-to-end):
```bash
bash scripts/test-complete-workflow.sh
```

**Validate metrics and monitoring setup**:
```bash
bash scripts/validate-metrics.sh
```

### Database & Kafka Management

**Clean database** (reset all tables):
```bash
bash scripts/clean-database.sh
```

**Clean Kafka** (reset all topics and messages):
```bash
bash scripts/clean-kafka.sh
```

**Auto-refill inventory during load tests** (prevents running out of stock):
```bash
# Default settings (refill when stock < 20, add 50 units, check every 10s)
.venv/bin/python scripts/auto-refill-inventory.py

# Custom settings (light load)
.venv/bin/python scripts/auto-refill-inventory.py --threshold 50 --refill-quantity 100 --interval 5

# Heavy stress test
.venv/bin/python scripts/auto-refill-inventory.py --threshold 10 --refill-quantity 200 --interval 5
```

**Stop the auto-refill service**:
```bash
# Graceful shutdown (recommended)
bash scripts/kill-auto-refill.sh

# Force kill if process is stuck
bash scripts/kill-auto-refill.sh --force
```

**Sync Grafana dashboards**:
```bash
bash scripts/dashboard-sync.sh
```

### Spark Analytics

**Start Spark jobs** (all 5 jobs in background):
```bash
bash scripts/spark/start-spark-jobs.sh
```

**Run single Spark job** (RECOMMENDED for testing):
```bash
# Available jobs: revenue_streaming, fraud_detection, cart_abandonment, inventory_velocity, operational_metrics
bash scripts/spark/run-spark-job.sh cart_abandonment
bash scripts/spark/run-spark-job.sh inventory_velocity
bash scripts/spark/run-spark-job.sh revenue_streaming
```

**Stop Spark jobs** (keeps checkpoints, can resume later):
```bash
# Stop all jobs
bash scripts/spark/kill-spark-jobs.sh

# Stop specific job
bash scripts/spark/kill-spark-jobs.sh cart_abandonment
bash scripts/spark/kill-spark-jobs.sh revenue_streaming
```

**Restart a specific Spark job** (kill + restart fresh with new checkpoints):
```bash
bash scripts/spark/restart-job.sh cart_abandonment
```

**Monitor running Spark jobs**:
```bash
bash scripts/spark/monitor-spark-jobs.sh
```

**Quick status check** of Spark cluster:
```bash
bash scripts/spark/quick-status.sh
```

**Clean Spark checkpoints** (kills jobs and resets all state):
```bash
bash scripts/spark/cleanup-checkpoints.sh
```

## Requirements

- **Python**: 3.11+ (use `.venv` virtual environment)
- **Bash**: For shell scripts
- **Docker**: For database and Kafka services
- **Dependencies**: Install from project root:
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

## Spark Job Lifecycle Commands

Understanding when to use each command:

| Command | Purpose | Checkpoints | Use Case |
|---------|---------|-------------|----------|
| `start-spark-jobs.sh` | Start all 5 jobs in background | Fresh start | Initial setup |
| `run-spark-job.sh` | Run single job | Fresh start | Test individual job |
| `kill-spark-jobs.sh` | ⏸️ Stop jobs gracefully | **Preserved** | Pause for maintenance |
| `restart-job.sh` | 🔄 Stop and restart job | Fresh (cleared) | Code changes/debugging |
| `cleanup-checkpoints.sh` | 🧹 Kill all + delete state | Deleted | Full reset, data loss OK |
| `monitor-spark-jobs.sh` | 📊 Watch and auto-restart | Depends on job | Background monitoring |

**Quick Decision Guide:**

- **Just pause jobs?** → `kill-spark-jobs.sh`
- **Resume after pause?** → `run-spark-job.sh job_name` (will use preserved checkpoints)
- **Changed job code?** → `restart-job.sh job_name`
- **Full system reset?** → `cleanup-checkpoints.sh` (then start fresh)
- **One-time test?** → `run-spark-job.sh job_name`

## Common Workflows

### 1. Quick System Test
```bash
# 1. Clean everything
bash scripts/clean-kafka.sh && bash scripts/clean-database.sh

# 2. Start Spark jobs
bash scripts/spark/run-spark-job.sh revenue_streaming &
bash scripts/spark/run-spark-job.sh cart_abandonment &

# 3. Simulate users
.venv/bin/python scripts/simulate-users.py --mode continuous --users 5 --duration 60

# 4. Check results in pgAdmin or PostgreSQL
```

### 2. Load Testing with Auto-Refill
```bash
# Terminal 1: Auto-refill inventory
.venv/bin/python scripts/auto-refill-inventory.py --threshold 20 --refill-quantity 50

# Terminal 2: Run load test
.venv/bin/python scripts/simulate-users.py --mode continuous --users 20 --duration 300

# Terminal 3: Monitor Spark
bash scripts/spark/monitor-spark-jobs.sh
```

### 3. Test Order Cancellation Flow
```bash
# Start fresh
bash scripts/clean-kafka.sh
bash scripts/clean-database.sh

# Simulate users
.venv/bin/python scripts/simulate-users.py --mode single

# View results and carts
.venv/bin/python scripts/view-carts.py
```

### 4. Analytics & Reporting
```bash
# Start Spark jobs to collect data
bash scripts/spark/start-spark-jobs.sh

# Run simulation to generate data
.venv/bin/python scripts/simulate-users.py --mode continuous --users 10 --duration 120

# Monitor job progress
bash scripts/spark/monitor-spark-jobs.sh

# View results
# - Spark Master: http://localhost:9080 (check driver UI)
# - PostgreSQL analytics tables in pgAdmin
```

### 5. Validate Complete Setup
```bash
# Check all services and metrics
bash scripts/validate-metrics.sh
```

## Auto-Refill Inventory Utility

For sustained load testing without running out of stock:

### Quick Start
```bash
# Install dependency (one-time)
pip install psycopg2-binary

# Run auto-refill service (in background)
.venv/bin/python scripts/auto-refill-inventory.py &

# In another terminal, run load test
.venv/bin/python scripts/simulate-users.py --mode continuous --duration 600 --users 20
```

### Configuration Options
```bash
.venv/bin/python scripts/auto-refill-inventory.py [options]

--threshold N           # Refill when stock < N (default: 20)
--refill-quantity N     # Add N units per refill (default: 50)
--interval N            # Check every N seconds (default: 10)
--verbose              # Show debug logging
```

### Example Scenarios
```bash
# Light load (default)
.venv/bin/python scripts/auto-refill-inventory.py

# Heavy stress test
.venv/bin/python scripts/auto-refill-inventory.py --threshold 10 --refill-quantity 100 --interval 5

# Realistic inventory management
.venv/bin/python scripts/auto-refill-inventory.py --threshold 30 --refill-quantity 30 --interval 15

# Debug mode with detailed logging
.venv/bin/python scripts/auto-refill-inventory.py --verbose
```

### How It Works
- Connects to PostgreSQL and monitors product stock every N seconds
- When stock drops below threshold, automatically adds refill quantity units
- Runs in background alongside your load tests
- Press Ctrl+C to stop and see statistics (total refills, units added, timing)

### Statistics Output Example
```
✅ Auto-refill service started
   Threshold: 20 units
   Refill quantity: 50 units
   Check interval: 10 seconds

[15:30:45] Refilled PROD-001 from 18 → 68 units
[15:31:05] Refilled PROD-003 from 5 → 55 units
[15:31:25] Refilled PROD-002 from 12 → 62 units

Ctrl+C pressed - Summary:
  Total refills: 3
  Total units added: 150
  Runtime: 40 seconds
```

## Troubleshooting

**Script not found?**
- Ensure you're running from project root: `/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`
- Check that file paths are correct: `scripts/your-script.sh`

**Permission denied?**
```bash
chmod +x scripts/*.sh
chmod +x scripts/spark/*.sh
```

**Module not found (Python)?**
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**Redis/Postgres/Kafka not running?**
```bash
docker-compose up -d
```

## Notes

- All Python scripts should be run with `.venv/bin/python` or activate the venv first
- All shell scripts should be run from the project root directory
- Database scripts may require confirmation before executing destructive operations
- For Spark jobs, use helper scripts in `scripts/spark/` rather than running job files directly

## Best Practices

### 1. Always Run from Project Root
```bash
# ✓ Correct
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom
./scripts/test-scenarios.sh

# ❌ Wrong - changes will fail
cd scripts
./test-scenarios.sh
```

### 2. Use Virtual Environment
```bash
# ✓ Correct
source .venv/bin/activate
python scripts/simulate-users.py --mode single

# Or without activation
.venv/bin/python scripts/simulate-users.py --mode single

# ❌ Wrong - may use wrong Python version
python scripts/simulate-users.py --mode single
```

### 3. Run Spark Jobs via Helper Script
```bash
# ✓ Correct - uses helper script
./scripts/spark/run-spark-job.sh cart_abandonment

# ❌ Wrong - import path issues
.venv/bin/python analytics/jobs/cart_abandonment.py

# ⚠️ Problematic - must be from project root
cd analytics/jobs
python cart_abandonment.py  # ModuleNotFoundError!
```

### 4. Grant Permissions First
```bash
# Make all scripts executable once
chmod +x scripts/*.sh
chmod +x scripts/spark/*.sh

# Verify
ls -la scripts/spark/
# Should show: -rwxr-xr-x (rwx = read, write, execute)
```

### 5. Use Auto-Refill for Sustained Testing
```bash
# For load tests > 5 minutes, start auto-refill first to prevent stockouts
.venv/bin/python scripts/auto-refill-inventory.py --threshold 20 --refill-quantity 50 &

# Then run load test in another terminal
.venv/bin/python scripts/simulate-users.py --mode continuous --users 20 --duration 600
```

### 6. Monitor Running Jobs
```bash
# For Spark jobs
open http://localhost:4040/  # Spark UI
bash scripts/spark/monitor-spark-jobs.sh

# For Kafka/Postgres flow
docker-compose logs -f order-service
docker-compose logs -f notification-service

# For specific service
docker-compose logs notification-service | grep -i cancelled
```
