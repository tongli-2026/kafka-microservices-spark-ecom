# Complete Workflow Test - Quick Start Guide

## 🚀 One Command to Test Everything

```bash
./test-complete-workflow.sh
```

**That's it!** This single command will:

1. ✅ **Start Spark Analytics Jobs**
   - Revenue streaming analytics
   - Fraud detection monitoring
   - Cart abandonment tracking

2. ✅ **Test All Microservices**
   - Cart service (add items)
   - Order service (create orders)
   - Payment service (process payments)
   - Inventory service (reserve stock)
   - Notification service (send emails)

3. ✅ **Verify Kafka Event Flow**
   - Check all topics are active
   - Verify event counts

4. ✅ **Check Analytics Results**
   - Query PostgreSQL for analytics data
   - Verify Spark jobs are processing events

5. ✅ **Generate Test Report**
   - Color-coded test results
   - Pass/fail summary

## 📋 Prerequisites

Make sure Docker containers are running:

```bash
# Start all services
docker-compose up -d

# Verify containers are up
docker-compose ps
```

You should see all containers running:
- ✅ kafka-broker-1
- ✅ zookeeper
- ✅ postgres
- ✅ redis
- ✅ spark-master
- ✅ spark-worker-1
- ✅ spark-worker-2
- ✅ cart-service
- ✅ order-service
- ✅ payment-service
- ✅ inventory-service
- ✅ notification-service

## 🎯 What Happens

### Phase 1: Spark Job Startup (Automatic)
```
▶ Starting Spark Analytics Jobs
✓ Spark cluster is running
✓ Revenue streaming job started
✓ Fraud detection job started
✓ Cart abandonment job started
⏳ Initializing Spark jobs... 15 seconds
✓ Spark analytics jobs are ready!
```

### Phase 2: Microservices Testing
```
▶ TEST 1: Add Items to Cart
✓ Added Product 1 (Qty: 2, Price: $49.99)
✓ Added Product 2 (Qty: 1, Price: $129.99)

▶ TEST 2: Checkout Process
✓ Checkout initiated

▶ TEST 3: Order Creation (Saga Orchestration)
✓ Order created successfully
✓ Order ID: order-1234567890

▶ TEST 4: Payment Processing
✓ Payment processed successfully

▶ TEST 5: Inventory Reservation
✓ Inventory reserved for product-123
✓ Current stock for product-123: 48 units

▶ TEST 6: Email Notifications
✓ Order confirmation email sent

▶ TEST 7: Spark Streaming Analytics
✓ Revenue metrics table has 12 records
✓ Fraud alerts: 3 alerts detected

▶ TEST 8: Kafka Event Flow
✓ Kafka cluster operational
ℹ cart.item_added: 15 events
ℹ order.created: 10 events
ℹ payment.processed: 8 events

▶ TEST 9: PostgreSQL Database State
✓ Database connected
  • orders: 10 records
  • payments: 8 records
  • revenue_metrics: 12 records
  • fraud_alerts: 3 records
```

### Phase 3: Summary
```
╔════════════════════════════════════════════════════════════════════╗
║  🎉 ALL TESTS PASSED! E-commerce workflow complete!              ║
╚════════════════════════════════════════════════════════════════════╝

Next Steps:
  • View Spark UI: http://localhost:8080
  • View Driver UI: http://localhost:4040
  • View pgAdmin: http://localhost:5050
  • Generate more data: ./generate-orders.sh

Spark Jobs:
  • Revenue streaming: RUNNING
  • Fraud detection: RUNNING
  • Cart abandonment: RUNNING
```

## 📊 Viewing Results

### Option 1: pgAdmin Web UI
```
URL: http://localhost:5050
Login: admin@kafka-ecom.com / admin
```

Navigate to Tables:
- `revenue_metrics` - Real-time revenue analytics
- `fraud_alerts` - Suspicious activity alerts
- `cart_abandonment` - Abandoned shopping carts
- `orders` - All customer orders
- `payments` - Payment transactions

### Option 2: SQL Queries
```bash
# View revenue metrics
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT * FROM revenue_metrics ORDER BY window_start DESC LIMIT 10;"

# View fraud alerts
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT * FROM fraud_alerts ORDER BY window_start DESC LIMIT 10;"

# View recent orders
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;"
```

### Option 3: Spark UI
- **Master**: http://localhost:8080 - Cluster overview
- **Driver**: http://localhost:4040 - Active job metrics
- **Worker 1**: http://localhost:8081
- **Worker 2**: http://localhost:8082

## 🔍 Monitoring Spark Jobs

### View Spark Job Logs
```bash
# Revenue streaming logs
tail -f /tmp/spark-revenue.log

# Fraud detection logs
tail -f /tmp/spark-fraud.log

# Cart abandonment logs
tail -f /tmp/spark-cart.log
```

### Check Spark Job Status
```bash
# List running Spark jobs
docker exec spark-master ps aux | grep spark-submit

# View Spark Master UI
open http://localhost:8080
```

## 🛑 Stopping Spark Jobs

The script leaves Spark jobs running in the background for continuous processing.

To stop them:
```bash
# Stop all Spark jobs
pkill -f 'run-spark-job.sh'

# Or stop individual jobs
kill <PID>  # Use PID shown in test output
```

## 🔄 Running Multiple Tests

```bash
# Run the test
./test-complete-workflow.sh

# Generate more orders to see analytics update
./generate-orders.sh
# Enter: 20

# Run the test again (will detect existing Spark jobs)
./test-complete-workflow.sh
```

## 🐛 Troubleshooting

### Test Fails: "Spark cluster not running"
```bash
# Check Spark containers
docker-compose ps | grep spark

# Restart Spark cluster
docker-compose restart spark-master spark-worker-1 spark-worker-2
```

### Test Fails: Microservices not responding
```bash
# Check service logs
docker logs cart-service
docker logs order-service
docker logs payment-service

# Restart services
docker-compose restart cart-service order-service payment-service
```

### Spark Jobs Not Processing Events
```bash
# Check Kafka connectivity
docker exec kafka-broker-1 kafka-topics --bootstrap-server localhost:9092 --list

# Check Spark logs
tail -100 /tmp/spark-revenue.log
```

### No Analytics Data
```bash
# 1. Make sure Spark jobs are running
ps aux | grep spark-submit

# 2. Generate test data
./generate-orders.sh

# 3. Wait 30 seconds for processing

# 4. Check PostgreSQL
docker exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT COUNT(*) FROM revenue_metrics;"
```

## 📚 What You're Learning

By running this test, you'll understand:

1. **Event-Driven Architecture**
   - How microservices communicate via Kafka events
   - Asynchronous message passing patterns

2. **Saga Pattern**
   - Distributed transaction coordination
   - Compensation logic for failures

3. **Stream Processing**
   - Real-time analytics with Apache Spark
   - Windowing and aggregation strategies

4. **Microservices Design**
   - Service boundaries and responsibilities
   - API design and health checks

5. **Data Pipeline**
   - Events → Kafka → Spark → PostgreSQL → Dashboard

## 🎓 Next Steps

After running the test successfully:

1. **Explore the Code**
   - Check `services/*/main.py` for microservice implementations
   - Review `analytics/jobs/*.py` for Spark job logic

2. **Modify and Experiment**
   - Change fraud detection thresholds
   - Add new analytics metrics
   - Create custom Spark jobs

3. **Generate More Data**
   - Use `./generate-orders.sh` to create bulk orders
   - Watch real-time analytics update

4. **Build Dashboards**
   - Connect BI tools to PostgreSQL
   - Create custom visualizations

## 📖 Additional Resources

- **WORKFLOW_GUIDE.md** - Detailed workflow documentation
- **SPARK_JOB_GUIDE.md** - Spark job reference
- **SPARK_JOBS_FIXES.md** - Troubleshooting guide
- **run-spark-job.sh** - Manual Spark job launcher
- **generate-orders.sh** - Bulk data generator

## ✨ Summary

```bash
# Everything you need in one command:
./test-complete-workflow.sh
```

**Automatically:**
- ✅ Starts Spark analytics jobs
- ✅ Tests all microservices
- ✅ Verifies Kafka event flow
- ✅ Checks analytics results
- ✅ Generates comprehensive report

**No manual setup required!** 🚀
