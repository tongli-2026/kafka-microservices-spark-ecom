# Scripts Directory

This directory contains utility and testing scripts for the Kafka E-Commerce Microservices project.

## Structure

```
scripts/
├── simulate-users.py          # User behavior simulation
├── test-scenarios.sh          # Test order scenarios
├── test-complete-workflow.sh  # Complete workflow testing
├── generate-orders.sh         # Generate test orders
├── view-carts.py              # View active Redis shopping carts
├── clean-database.sh          # Clean/reset database
├── clean-kafka.sh             # Clean/reset Kafka topics
├── spark/                     # Spark job management scripts
│   ├── start-spark-jobs.sh
│   ├── start-spark-jobs-with-ui.sh
│   ├── submit-spark-jobs.sh
│   └── run-spark-job.sh
└── README.md                  # This file
```

## Usage

### User & Order Testing

**Simulate user behavior** (browse → cart → checkout → payment):
```bash
.venv/bin/python scripts/simulate-users.py --mode single
```

**View active shopping carts**:
```bash
.venv/bin/python scripts/view-carts.py
```

**Generate test orders**:
```bash
bash scripts/generate-orders.sh
```

**Test specific scenarios**:
```bash
bash scripts/test-scenarios.sh 10
```

**Run complete workflow test**:
```bash
bash scripts/test-complete-workflow.sh
```

### Database & Kafka Management

**Clean database** (reset all tables):
```bash
bash scripts/clean-database.sh
```

**Clean Kafka** (reset all topics):
```bash
bash scripts/clean-kafka.sh
```

### Spark Analytics

**Start Spark jobs**:
```bash
bash scripts/spark/start-spark-jobs.sh
```

**Start Spark with UI** (includes Spark history server):
```bash
bash scripts/spark/start-spark-jobs-with-ui.sh
```

**Submit Spark jobs**:
```bash
bash scripts/spark/submit-spark-jobs.sh
```

**Run single Spark job**:
```bash
bash scripts/spark/run-spark-job.sh
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

## Common Workflows

### 1. Test Order Cancellation Flow
```bash
# Start fresh
bash scripts/clean-kafka.sh
bash scripts/clean-database.sh

# Simulate users
.venv/bin/python scripts/simulate-users.py --mode single

# View results
.venv/bin/python scripts/view-carts.py
```

### 2. Load Testing
```bash
# Continuous simulation for 5 minutes
.venv/bin/python scripts/simulate-users.py --mode continuous --users 20 --duration 300
```

### 3. Complete System Test
```bash
bash scripts/test-complete-workflow.sh
```

### 4. Analytics & Reporting
```bash
bash scripts/spark/start-spark-jobs-with-ui.sh
# View results at http://localhost:18080
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
