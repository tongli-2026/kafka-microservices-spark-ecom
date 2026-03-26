# Kafka Microservices E-Commerce with Spark Analytics

A complete event-driven e-commerce backend built with Apache Kafka, FastAPI microservices, PostgreSQL, Redis, and PySpark analytics.

**Live Components**: Kafka (3 brokers), PostgreSQL, Redis, Spark (1 master + 2 workers), FastAPI microservices, pgAdmin, Mailpit, Kafka UI

## Table of Contents

1. [Architecture](#architecture)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Quick Start](#quick-start)
5. [Web UI Access](#web-ui-access--setup)
6. [Database Setup & Access](#database-setup--access)
7. [API Endpoints](#api-endpoints)
8. [Kafka Topics](#kafka-topics)
9. [Event Flow](#event-flow)
10. [Database Schema](#database-schema)
11. [Configuration](#configuration)
12. [Spark Cluster Details](#spark-cluster-details)
13. [Monitoring & Development](#monitoring--development)
14. [Prometheus & Grafana Setup Guide](#prometheus--grafana-setup-guide)
15. [Troubleshooting](#troubleshooting)
16. [Cleanup](#cleanup)
17. [Architecture Highlights](#architecture-highlights)

## Architecture

### Microservices
- **Cart Service** (Port 8001): Shopping cart management with Redis
- **Order Service** (Port 8002): Order orchestration with saga pattern and background fulfillment job
- **Payment Service** (Port 8003): Payment processing (80% success rate)
- **Inventory Service** (Port 8004): Stock management with optimistic locking
- **Notification Service** (Port 8005): Email notifications via Mailpit

### Data Infrastructure
- **Kafka Cluster**: 3-broker KRaft cluster with Kafka UI
- **PostgreSQL**: Persistent data storage
- **Redis**: Cart state and caching

### Analytics
- **Spark Cluster**: Distributed processing with 1 master + 2 workers
  - **Master**: Resource allocation and job scheduling
  - **Worker 1**: 4 cores, 4GB RAM (driver + executor)
  - **Worker 2**: 4 cores, 4GB RAM (executor)
- **PySpark Jobs**: 5 streaming jobs for real-time insights
  1. Revenue streaming (1-min windows)
  2. Fraud detection (5-min sliding windows)
  3. Cart abandonment (30-min stream join)
  4. Inventory velocity (1-hour windows, top 10 products)
  5. Operational metrics (topic-level monitoring)

## Project Structure

```
kafka-microservices-spark-ecom/
│
├── 📄 Configuration Files
│   ├── .env                          # Environment variables (local)
│   ├── .env.example                  # Example environment template
│   ├── docker-compose.yml            # Docker services definition
│   ├── Dockerfile.spark              # Spark cluster Dockerfile
│   ├── pyproject.toml                # Python project config
│   └── setup.py                      # Setup configuration
│
├── 📚 Documentation
│   ├── README.md                     # Main documentation (this file)
│   ├── API.md                        # API endpoint documentation (941 lines)
│   ├── SPARK_ANALYTICS.md            # Spark streaming jobs & analytics (814 lines)
│   ├── MONITORING_QUICK_REFERENCE.md # Monitoring guide + DLQ monitoring (800+ lines)
│   ├── IDEMPOTENCY_IMPLEMENTATION.md # Saga + outbox pattern details (976 lines)
│   ├── DASHBOARDS_COMPLETE_SUITE.md  # All dashboards + DLQ dashboard panels (632+ lines)
│   ├── TROUBLESHOOTING.md            # Problem resolution guide (393 lines)
│   └── conftest.py                   # Pytest configuration
│
├── 🔧 Scripts
│   ├── README.md                     # Scripts usage guide
│   ├── simulate-users.py             # User behavior simulation
│   ├── test-scenarios.sh             # Test order scenarios
│   ├── test-complete-workflow.sh     # Run complete workflow test
│   ├── auto-refill-inventory.py      # Auto-refill utility for load tests
│   ├── view-carts.py                 # View Redis carts (Python)
│   ├── clean-database.sh             # Clean PostgreSQL data
│   ├── clean-kafka.sh                # Clean Kafka topics
│   ├── dashboard-sync.sh             # Sync Grafana dashboards
│   ├── validate-metrics.sh           # Validate monitoring setup
│   ├── schedule-inventory-velocity.sh # Schedule inventory velocity job
│   ├── kill-auto-refill.sh           # Stop auto-refill service
│   ├── dlq-replay.py                 # DLQ recovery tool (view, replay, diagnose)
│   ├── dlq-replay.py                 # Replay failed events from DLQ after fixing root cause
│   ├── dlq-auto-replay.py            # Auto-replay DLQ when threshold exceeded with health checks
│   ├── setup-dlq-monitoring.sh       # Setup script for DLQ monitoring & auto-replay
│   └── spark/                        # Spark job management
│       ├── cleanup-checkpoints.sh    # Clean Spark checkpoints
│       ├── kill-spark-jobs.sh        # Kill running Spark jobs
│       ├── monitor-spark-jobs.sh     # Monitor running jobs
│       ├── quick-status.sh           # Quick status check
│       ├── restart-job.sh            # Restart specific job
│       ├── run-spark-job.sh          # Run specific Spark job
│       └── start-spark-jobs.sh       # Start all Spark jobs
│
├── 📁 services/                      # Microservices (5 services)
│   ├── cart-service/
│   │   ├── main.py                   # FastAPI app entry point
│   │   ├── cart_repository.py        # Data access layer
│   │   ├── schemas.py                # Pydantic models
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── inventory-service/
│   │   ├── main.py                   # FastAPI app entry point
│   │   ├── inventory_repository.py   # Optimistic locking logic
│   │   ├── schemas.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── order-service/
│   │   ├── main.py                   # FastAPI app entry point
│   │   ├── order_repository.py       # Order persistence
│   │   ├── saga_handler.py           # Saga orchestration logic
│   │   ├── outbox_handler.py         # Outbox pattern implementation
│   │   ├── schemas.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── payment-service/
│   │   ├── main.py                   # FastAPI app entry point
│   │   ├── payment_repository.py     # Payment persistence
│   │   ├── schemas.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   └── notification-service/
│       ├── main.py                   # FastAPI app entry point
│       ├── schemas.py
│       ├── Dockerfile
│       └── requirements.txt
│
├── 📁 analytics/                     # Spark Cluster & Jobs
│   ├── spark_session.py              # Spark session factory
│   ├── Dockerfile                    # Spark cluster Docker image
│   ├── Dockerfile.exporter           # Metrics exporter Docker image
│   ├── metrics_exporter.py           # Spark metrics exporter
│   ├── requirements.txt              # Spark dependencies
│   │
│   └── jobs/                         # Streaming jobs (5 jobs)
│       ├── revenue_streaming.py      # 1-min revenue aggregation
│       ├── fraud_detection.py        # 5-min fraud detection
│       ├── cart_abandonment.py       # 30-min cart abandonment
│       ├── inventory_velocity.py     # 1-hour inventory analysis
│       └── operational_metrics.py    # Topic-level monitoring
│
├── 📁 monitoring/                    # Monitoring & Observability
│   ├── Dockerfile.grafana            # Grafana Docker image
│   ├── Dockerfile.prometheus         # Prometheus Docker image
│   ├── prometheus.yml                # Prometheus configuration
│   ├── dashboards/                   # Grafana dashboards (JSON)
│   │   ├── microservices-dashboard.json
│   │   ├── order-fulfillment-dashboard.json
│   │   ├── financial-operations-dashboard.json
│   │   ├── customer-experience-dashboard.json
│   │   ├── infrastructure-health-dashboard.json
│   │   └── spark-analytics-dashboard.json
│   └── provisioning/                 # Grafana provisioning
│       ├── dashboards.yml            # Dashboard provisioning config
│       └── datasources.yml           # Data source provisioning config
│
├── 📁 shared/                        # Shared utilities
│   ├── database.py                   # PostgreSQL client
│   ├── events.py                     # Event models & types
│   ├── kafka_client.py               # Kafka producer/consumer
│   ├── logging_config.py             # Logging setup
│   └── topic_initializer.py          # Kafka topic creation
│
├── 📁 data/                          # Data files (SQL, fixtures)
│
└── pgAdmin_queries.sql               # Pre-written SQL queries
```

### Directory Details

**services/** - Microservices Architecture
- 5 independent FastAPI services on ports 8001-8005
- Each service has its own Docker container
- Kafka producers/consumers for event handling
- Database persistence layers with optimistic locking/saga patterns

**analytics/** - Spark Analytics Cluster
- 1 master + 2 worker nodes
- 5 streaming jobs reading from Kafka topics
- Results written to PostgreSQL analytics tables
- Watermarking, windowing, and stateful operations
- Metrics exporter for Prometheus integration

**monitoring/** - Observability Stack
- Prometheus: Metrics collection and time-series database
- Grafana: Dashboard visualization and alerting
- 6 pre-built dashboards for different teams (microservices, order fulfillment, financial ops, customer experience, infrastructure health, spark analytics)
- Provisioning configs for automatic dashboard/datasource setup

**scripts/** - Helper Scripts & Automation
- User simulation and workflow testing
- Database and Kafka cleanup utilities
- DLQ recovery and auto-replay tools (dlq-replay.py, dlq-auto-replay.py)
- DLQ monitoring setup script (setup-dlq-monitoring.sh)
- Spark job management (start, stop, monitor, restart)
- Checkpoint cleanup and status checking
- 11 scripts in root + 7 Spark management scripts

**shared/** - Common Code
- Kafka client with retry logic and DLQ support
- PostgreSQL connection pooling
- Event schema definitions
- Logging and topic initialization

## Prerequisites

- Docker & Docker Compose 20.10+
- 4GB RAM minimum
- macOS, Linux, or WSL2 (Windows)

## Quick Start

### 1. Clone and Setup

```bash
cd kafka-microservices-spark-ecom
cp .env.example .env
```

### 2. Start All Services

```bash
docker-compose up --build
```

### 3. Verify Services

```bash
# Health checks (wait 30-60s for services to start)
curl http://localhost:8001/health  # Cart Service
curl http://localhost:8002/health  # Order Service
curl http://localhost:8003/health  # Payment Service
curl http://localhost:8004/health  # Inventory Service
curl http://localhost:8005/health  # Notification Service

# Kafka UI
open http://localhost:8080

# Spark Master UI
open http://localhost:9080

# Mailpit Web UI (emails)
open http://localhost:8025
```

### 4. Run Spark Analytics Jobs

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

```bash
# Submit a streaming job to the Spark cluster (using helper script - RECOMMENDED)
./scripts/spark/run-spark-job.sh revenue_streaming

# Or run manually from project root
docker exec spark-worker-1 /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /opt/spark-apps/revenue_streaming.py

# Available jobs:
# - revenue_streaming
# - fraud_detection
# - cart_abandonment
# - inventory_velocity
# - operational_metrics
```

## Web UI Access & Setup

All UIs are now configured to use **Seattle Timezone (America/Los_Angeles)** for consistent time display.

### Web Interfaces

| Service | URL | Credentials | Purpose |
|---------|-----|-------------|---------|
| **Kafka UI** | http://localhost:8080 | None | View topics, partitions, messages, consumer groups |
| **Spark Master UI** | http://localhost:9080 | None | Monitor cluster resources, workers, applications |
| **Spark Worker 1 UI** | http://localhost:8081 | None | Worker 1 executor tasks and resource details |
| **Spark Worker 2 UI** | http://localhost:8082 | None | Worker 2 executor tasks and resource details |
| **Spark Driver UI** | http://localhost:4040 | None | Active job SQL execution plans and streaming stats |
| **Prometheus** | http://localhost:9090 | None | Metrics collection, queries, and time-series data |
| **Grafana** | http://localhost:3000 | admin / admin | Pre-built dashboards for all system components |
| **pgAdmin** | http://localhost:5050 | admin@kafka-ecom.com / admin | PostgreSQL database browser and query tool |
| **Mailpit** | http://localhost:8025 | None | Email capture, testing, and viewing interface |
| **Redis** | localhost:6379 | None | In-memory cache (CLI: `redis-cli`) |

### pgAdmin Setup (PostgreSQL Browser)

#### Access
- **URL**: http://localhost:5050
- **Email**: `admin@kafka-ecom.com`
- **Password**: `admin`

#### Add PostgreSQL Server

Follow these steps to connect to the database:

1. **Open pgAdmin** → http://localhost:5050
2. **Login** with credentials above
3. **Right-click "Servers"** in left sidebar → **"Register" → "Server"**
4. **Fill in the connection details:**

**General Tab:**
   - Name: `kafka_ecom`
   - Description: (optional) Main Kafka E-commerce Database

**Connection Tab:**
   - Host name/address: `postgres`
   - Port: `5432`
   - Maintenance database: `postgres`
   - Username: `postgres`
   - Password: `postgres`
   - ✓ Save password?

**SSL Mode:**
   - SSL mode: `Prefer` (or Allow)

5. **Click "Save"**

The server should now appear in your sidebar with a green indicator.

#### View Database Tables

After adding the server:
1. Expand **kafka_ecom_db** → **Databases** → **kafka_ecom** → **Schemas** → **public** → **Tables**
2. You'll see all analytics and data tables:
   - `orders`, `payments`, `products`, `stock_reservations`
   - `revenue_metrics`, `fraud_alerts`, `cart_abandonment`, `inventory_velocity`
   - `operational_metrics`, `processed_events`, `outbox_events`

#### Run Queries in pgAdmin

1. Click on the `kafka_ecom_db` server or `kafka_ecom` database
2. Go to **Tools → Query Tool**
3. Paste any query from `pgAdmin_queries.sql`
4. Press **F5** or click "Execute"

**Example Queries:**

```sql
-- View recent orders
SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;

-- View revenue metrics (hourly)
SELECT window_start, order_count, total_revenue, avg_order_value 
FROM revenue_metrics ORDER BY window_start DESC LIMIT 20;

-- View fraud alerts
SELECT * FROM fraud_alerts ORDER BY alert_timestamp DESC LIMIT 10;

-- View cart abandonment
SELECT * FROM cart_abandonment ORDER BY detected_at DESC LIMIT 10;

-- Top selling products
SELECT product_id, SUM(units_sold) as total_units, COUNT(*) as windows
FROM inventory_velocity
GROUP BY product_id ORDER BY total_units DESC LIMIT 20;

-- View all table sizes and record counts
SELECT relname as tablename, n_live_tup as records, pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) as size
FROM pg_stat_user_tables ORDER BY relname;
```

See `pgAdmin_queries.sql` for 50+ pre-written queries.

#### Troubleshooting pgAdmin

| Issue | Solution |
|-------|----------|
| **Server not appearing** | Refresh page (F5) or click refresh icon in sidebar |
| **"Connection refused"** | Verify PostgreSQL running: `docker ps \| grep postgres` |
| **Password not saving** | Go to Server Properties → Connection tab → Re-enter password → Save |
| **Query Tool not loading** | Click on a specific table first, then go to Tools → Query Tool |
| **Port 5050 not responding** | Restart pgAdmin: `docker restart pgadmin` |

## Database Setup & Access

### Redis (In-Memory Cache)

#### What is Redis?

Redis is an in-memory data store used in this project to:
- **Store cart state**: Fast read/write for shopping carts
- **TTL management**: Automatically expire abandoned carts after 24 hours
- **Session management**: Cache user session data
- **Real-time operations**: Serve cart data instantly without database queries

#### Viewing Cart Data

**Option 1: Python Script (Recommended)**

```bash
# 1. Navigate to the project root
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom

# 2. Make sure virtual environment is activated
source .venv/bin/activate

# 3. Run the script to view all active carts with TTL and items
.venv/bin/python scripts/view-carts.py
```

Output:
```
✅ Found 1 active carts:

👤 User: user123
⏱️  TTL: 84134 seconds remaining
🛒 Items: {
  "laptop": {
    "quantity": 2,
    "price": 999.99
  },
  "smartphone": {
    "quantity": 1,
    "price": 599.99
  }
}
```

**Option 2: Redis CLI (Direct)**

```bash
# Connect to Redis
docker exec -it redis redis-cli

# View all cart keys
KEYS "cart:*"

# View specific cart
GET cart:user123

# Check remaining TTL (in seconds)
TTL cart:user123

# Useful commands:
DBSIZE                    # Total keys in Redis
GET cart:user123          # Get cart for user123
DEL cart:user123          # Delete a cart
EXPIRE cart:user123 3600  # Set TTL to 1 hour
PERSIST cart:user123      # Remove TTL (keep forever)
FLUSHDB                   # Clear all data (be careful!)
MONITOR                   # Watch all operations in real-time
INFO                      # Redis server info
MEMORY STATS              # Memory usage
EXIT                      # Exit Redis CLI
```

**Option 3: Real-Time Monitoring**

```bash
# Monitor all Redis operations as they happen
docker exec -it redis redis-cli MONITOR

# In another terminal, add items to cart:
curl -X POST http://localhost:8001/cart/user123/items \
  -H "Content-Type: application/json" \
  -d '{"product_id": "laptop", "quantity": 1, "price": 999.99}'

# You'll see in MONITOR:
# [timestamp] [0 127.0.0.1:12345] "SET" "cart:user123" "{...}" "EX" "86400"
```

#### Cart Data Format

**Key**: `cart:{user_id}` (example: `cart:user123`)

**Value** (JSON):
```json
{
  "product_id_1": {"quantity": 2, "price": 999.99},
  "product_id_2": {"quantity": 1, "price": 599.99}
}
```

**TTL**: 86400 seconds (24 hours) - resets on each update

#### Troubleshooting Redis

| Issue | Solution |
|-------|----------|
| Connection refused | Start Redis: `docker-compose up redis -d` |
| No carts found | Add items via `/cart/add` API endpoint first |
| TTL shows -2 | Key expired or doesn't exist |
| TTL shows -1 | Key exists but has no expiration |
| Memory usage high | Run `FLUSHDB` to clear all keys |

### PostgreSQL via psql

```bash
# Connect directly to database
docker-compose exec postgres psql -U postgres -d kafka_ecom

# Useful commands:
\dt                    # List tables
\d orders              # Describe orders table
SELECT * FROM orders;  # Query orders
\q                     # Quit
```

### Clean Up Database & Kafka

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

Two helper scripts are provided:

```bash
# Clean PostgreSQL (truncate all tables)
./scripts/clean-database.sh

# Clean Kafka (delete all messages from all topics)
./scripts/clean-kafka.sh

# Both together for complete reset
./scripts/clean-database.sh && ./scripts/clean-kafka.sh
```

### System Timezone Configuration

All containers are configured to use **America/Los_Angeles (Seattle)** timezone.

If you need to change timezone:

1. **Edit docker-compose.yml:**
   - Find all `TZ: America/Los_Angeles` entries
   - Replace with your timezone (e.g., `TZ: UTC` or `TZ: Europe/London`)

2. **Restart containers:**
   ```bash
   ./restart-with-timezone.sh
   ```

Available timezones: Use standard IANA format like:
- `UTC`
- `America/Los_Angeles`
- `America/New_York`
- `Europe/London`
- `Asia/Tokyo`

## API Endpoints

### Cart Service (Port 8001)

```bash
# Health check
curl http://localhost:8001/health | jq .

# Add item to cart
curl -X POST http://localhost:8001/cart/user_001/items \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "PROD-D0934F50871D",
    "quantity": 2,
    "price": 24.99
  }' | jq .

# Get cart
curl http://localhost:8001/cart/user_001 | jq .

# Update item quantity
curl -X PUT http://localhost:8001/cart/user_001/items/PROD-D0934F50871D \
  -H "Content-Type: application/json" \
  -d '{"quantity": 5}' | jq .

# Remove item
curl -X DELETE http://localhost:8001/cart/user_001/items/PROD-D0934F50871D | jq .

# Checkout (initiates order saga)
curl -X POST http://localhost:8001/cart/user_001/checkout | jq .
```

### Order Service (Port 8002)

```bash
# Health check
curl http://localhost:8002/health | jq .

# Get order details
curl http://localhost:8002/orders/ORD-ABC123 | jq .

# Get all orders for a user
curl http://localhost:8002/orders/user/user123 | jq .
```110910

### Inventory Service (Port 8004)

```bash
# Health check
curl http://localhost:8004/health | jq .

# List products
curl http://localhost:8004/products | jq .

# Get product details
curl http://localhost:8004/products/PROD-001 | jq .
```

### Payment Service (Port 8003)

```bash
# Health check
curl http://localhost:8003/health | jq .

# Get payment details
curl http://localhost:8003/payments/PAY-XYZ789 | jq .
```

## Database Schema

### PostgreSQL Tables

```sql
-- Orders
CREATE TABLE orders (
  id UUID PRIMARY KEY,
  order_id VARCHAR(255) UNIQUE,
  user_id VARCHAR(255),
  status VARCHAR(50),
  items JSONB,
  total_amount FLOAT,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- Outbox (reliable publishing)
CREATE TABLE outbox_events (
  id UUID PRIMARY KEY,
  order_id VARCHAR(255),
  event_type VARCHAR(100),
  event_data TEXT,
  published CHAR(1),
  created_at TIMESTAMP,
  published_at TIMESTAMP
);

-- Processed Events (idempotency)
CREATE TABLE processed_events (
  id UUID PRIMARY KEY,
  event_id VARCHAR(255) UNIQUE,
  event_type VARCHAR(100),
  processed_at TIMESTAMP
);

-- Inventory
CREATE TABLE products (
  id UUID PRIMARY KEY,
  product_id VARCHAR(255) UNIQUE,
  name VARCHAR(255),
  description VARCHAR(1000),
  price FLOAT,
  stock INTEGER,
  version INTEGER,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE TABLE stock_reservations (
  id UUID PRIMARY KEY,
  order_id VARCHAR(255),
  product_id VARCHAR(255),
  quantity INTEGER,
  created_at TIMESTAMP
);

-- Payments
CREATE TABLE payments (
  id UUID PRIMARY KEY,
  payment_id VARCHAR(255) UNIQUE,
  order_id VARCHAR(255),
  user_id VARCHAR(255),
  amount FLOAT,
  currency VARCHAR(3),
  method VARCHAR(50),
  status VARCHAR(50),
  reason VARCHAR(255),
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- Analytics
CREATE TABLE revenue_metrics (
  id SERIAL PRIMARY KEY,
  window_start TIMESTAMP NOT NULL,
  window_end TIMESTAMP NOT NULL,
  total_revenue DECIMAL(12, 2),
  order_count INTEGER,
  avg_order_value DECIMAL(12, 2),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE fraud_alerts (
  id SERIAL PRIMARY KEY,
  alert_id VARCHAR(255) UNIQUE,
  alert_timestamp TIMESTAMP NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  order_id VARCHAR(255),
  alert_type VARCHAR(50),
  severity VARCHAR(20),
  details TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE cart_abandonment (
  user_id VARCHAR(255) NOT NULL,
  product_id VARCHAR(255) NOT NULL,
  item_added_time TIMESTAMP NOT NULL,
  detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory_velocity (
  id SERIAL PRIMARY KEY,
  window_start TIMESTAMP NOT NULL,
  window_end TIMESTAMP NOT NULL,
  product_id VARCHAR(255) NOT NULL,
  units_sold INTEGER,
  revenue DECIMAL(12, 2),
  velocity_rank INTEGER
);

CREATE TABLE operational_metrics (
  id SERIAL PRIMARY KEY,
  window_start TIMESTAMP NOT NULL,
  window_end TIMESTAMP NOT NULL,
  metric_name VARCHAR(255),
  metric_value DECIMAL(12, 2),
  threshold DECIMAL(12, 2),
  status VARCHAR(20),
  services_checked JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Event Flow

### Complete Event Flow Diagram

```
                    ┌───────────────────────────────────────────────────────────┐
                    │    Successful Purchase Flow (Inventory before Payment)    │
                    └───────────────────────────────────────────────────────────┘

User adds items to cart
           │
           ├─→ [cart.item_added] ──→ Cart Service (stores in Redis)
           │
User checks out
           │
           ├─→ [cart.checkout_initiated] ──→ Order Service
           │
           ├─→ [order.created] ──→ Inventory Service
           │                       (tries to reserve stock)
           │
           ├─→ [inventory.reserved ✓] ──→ Order Service
           │
           ├─→ [order.reservation_confirmed] ──→ Payment Service
           │                                     (only if stock reserved)
           │
           ├─→ [payment.processed ✓] ──→ Order Service
           │
           ├─→ [order.confirmed] ──→ Notification Service
           │
           ├─→ [notification.send] ──→ Customer Email ✓
           │
           └─→ [order.fulfilled] ──→ Order Service, Notification Service
                   (async fulfillment/shipping)
                   │
                   └─→ [notification.send] ──→ Shipment Email with Tracking ✓

                    ┌──────────────────────────────────────────────┐
                    │   Failed Flow When Stock is Out              │
                    │   (Prevents Customer Being Charged!)         │
                    └──────────────────────────────────────────────┘

[order.created] ──→ Inventory Service
           │        (tries to reserve stock)
           │
           ├─→ [inventory.depleted ✗]
           │    "Last item sold to another customer"
           │
           ├─→ [order.cancelled] ──→ Notification Service
           │                         (no payment processed!)
           │
           └─→ Customer Email: "Sorry, out of stock"
                (NO CHARGE ✓)


                    ┌──────────────────────────────────────────────────┐
                    │   Failed Flow due to Payment Failure             │
                    │   (Inventory Released Automatically)             │
                    └──────────────────────────────────────────────────┘

[order.reservation_confirmed] ──→ Payment Service
           │                      (payment processing)
           │
           ├─→ [payment.failed ✗]
           │    "Card declined"
           │
           ├─→ [order.cancelled] ──→ Inventory Service
           │                         (release reserved stock)
           │
           └─→ Notification Service sends failure email
                (Stock back in inventory ✓)
```

### Successful Purchase Flow (Step by Step) - PRODUCTION-STYLE ✅

**Work Flow:** Inventory reserved BEFORE payment (prevents charging for out-of-stock items)

1. **User adds items to cart** 
   - Event: `cart.item_added`
   - Producer: Cart Service
   - Consumer: Cart Service (stores in Redis)

2. **User checks out** 
   - Event: `cart.checkout_initiated`
   - Producer: Cart Service
   - Consumer: Order Service

3. **Order Service creates order** 
   - Event: `order.created` (Status: PENDING)
   - Producer: Order Service
   - Consumer: Inventory Service (RESERVES STOCK FIRST - PRODUCTION STYLE)

4. **Inventory Service reserves stock** 
   - If stock available → Event: `inventory.reserved`
   - Producer: Inventory Service
   - Consumer: Order Service

5. **Order Service confirms reservation** 
   - Event: `order.reservation_confirmed` (Status: RESERVATION_CONFIRMED)
   - Producer: Order Service
   - Consumer: Payment Service (NOW SAFE TO PROCESS PAYMENT)

6. **Payment Service processes payment** 
   - Event: `payment.processed` (80% success rate)
   - Producer: Payment Service
   - Consumer: Order Service

7. **Order Service finalizes** 
   - If payment.processed → Status: PAID, publishes `order.confirmed`
   - Producer: Order Service
   - Consumer: Notification Service

8. **Notification Service processes event** 
   - Event consumed: `order.confirmed`
   - Publishes: `notification.send` event
   - Producer: Notification Service
   - Consumer: Mailpit (Email Service)

9. **Email delivered**
   - Order confirmation email sent via Mailpit

10. **Order Service fulfillment job publishes** 
    - Event: `order.fulfilled` (Order shipped with tracking number)
    - Producer: Fulfillment Job (Order Service background thread)
    - Consumer: Order Service, Notification Service

11. **Notification Service sends shipment email** 
    - Event consumed: `order.fulfilled`
    - Includes: Tracking number, estimated delivery date
    - Publishes: `notification.send` event
    - Producer: Notification Service
    - Consumer: Mailpit (Email Service)

12. **Shipment email delivered**
    - Order shipment confirmation with tracking number sent to customer

### Failed Purchase Flow (Out of Stock)

1. **Order Service creates order** 
   - Event: `order.created` (Status: PENDING)
   - Producer: Order Service
   - Consumer: Inventory Service

2. **Inventory Service checks stock** 
   - Event: `inventory.depleted` (Out of stock - last item sold to another customer)
   - Producer: Inventory Service
   - Consumer: Order Service, Notification Service

3. **Order Service cancels order** 
   - Event: `order.cancelled` (Status: PENDING → CANCELLED)
   - **IMPORTANT: NO PAYMENT PROCESSED**
   - Producer: Order Service
   - Consumer: Inventory Service, Notification Service

4. **Notification Service sends cancellation email** 
   - Event: `order.cancelled` (consumed)
   - Publishes: `notification.send` event
   - Producer: Notification Service
   - Consumer: Mailpit (Email Service)
   - Result: Customer receives "Sorry, out of stock" email
   - **CUSTOMER NOT CHARGED** ✓

### Failed Purchase Flow (Payment Failure)

1. **Payment processing fails** 
   - Event: `payment.failed` (20% failure rate)
   - Producer: Payment Service
   - Consumer: Order Service
   - **CUSTOMER NOT CHARGED** ✓

2. **Order cancelled** 
   - Event: `order.cancelled`
   - Producer: Order Service
   - Consumer: Inventory Service, Notification Service

3. **Stock released automatically** 
   - Inventory Service consumes `order.cancelled`
   - Reserved stock is incremented back to inventory
   - Stock reservation record is deleted from database
   - (implicit operation, no separate event published)

4. **Notification Service sends failure email** 
   - Event: `order.cancelled` (consumed)
   - Producer: Notification Service (publishes `notification.send`)
   - Consumer: Mailpit (Email Service)
   - Result: Payment failure/cancellation email sent to customer

### Order Status Lifecycle

Orders progress through the following states:

```
PENDING (initial state - order just created)
  │
  ├─→ RESERVATION_CONFIRMED (inventory reserved successfully)
  │   │
  │   ├─→ PAID (payment processed successfully)
  │   │   │
  │   │   └─→ FULFILLED (order shipped/delivered via fulfillment job)
  │   │
  │   └─→ CANCELLED (payment failed - inventory released)
  │
  └─→ CANCELLED (inventory out of stock - NO PAYMENT CHARGED)
```

**Status Descriptions**:

| Status | Trigger Event | Meaning | Customer Impact |
|--------|---------------|---------|-----------------|
| **PENDING** | `cart.checkout_initiated` | Order being processed | Order awaiting inventory check |
| **RESERVATION_CONFIRMED** | `inventory.reserved` | Stock reserved | Order confirmed, awaiting payment |
| **PAID** | `payment.processed` | Payment successful | Charge applied to card ✓ |
| **FULFILLED** | `order.fulfilled` | Order shipped/delivered | Order completed, tracking available |
| **CANCELLED** | `inventory.depleted` OR `payment.failed` | Order cancelled | No charge |

**Key Points**:
- ✓ Customer NOT charged if inventory is out of stock (CANCELLED via `inventory.depleted`) or payment is failed
- ✓ Customer ONLY charged if inventory reserved → stock is guaranteed
- ✓ FULFILLED status indicates order is ready/shipped (set by background fulfillment job)
- ✓ Complete successful order lifecycle: PENDING → RESERVATION_CONFIRMED → PAID → FULFILLED

## Kafka Topics

All topics are created with:
- **Partitions**: 3 (one per broker)
- **Replication Factor**: 3 (across all brokers)
- **Producer acks**: all (durability)

### Kafka Topic Topology

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                    KAFKA TOPICS (15 Total)                                    │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  CART EVENTS:                                                                 │
│  ├─ cart.item_added ────────────────→ Cart Service                            │
│  ├─ cart.item_removed ──────────────→ Cart Service                            │
│  └─ cart.checkout_initiated ───────→ Order Service                            │
│                                                                               │
│  ORDER EVENTS:                                                                │
│  ├─ order.created ──────────────────→ Inventory Service                       │
│  ├─ order.reservation_confirmed ───→ Payment Service                          │
│  ├─ order.confirmed ────────────────→ Notification Service                    │
│  ├─ order.fulfilled ───────────────→ Order Service, Notification Service      │
│  └─ order.cancelled ───────────────→ Inventory Service, Notification Service  │
│                                                                               │
│  INVENTORY EVENTS:                                                            │
│  ├─ inventory.reserved ✓ ──────────→ Order Service                            │
│  ├─ inventory.low ──────────────────→ Notification Service                    │
│  └─ inventory.depleted ────────────→ Notification Service                     │
│                                                                               │
│  PAYMENT EVENTS:                                                              │
│  ├─ payment.processed ✓ ───────────→ Order Service                            │
│  └─ payment.failed ✗ ──────────────→ Order Service                            │
│                                                                               │
│  SYSTEM EVENTS:                                                               │
│  ├─ notification.send ──────────────→ Mailpit (Email Service)                 │
│  └─ dlq.events ─────────────────────→ Dead Letter Queue                       │
│                                                                               │
│  ANALYTICS (PostgreSQL + Prometheus):                                         │
│  └─ fraud_alerts table (Spark output) ──→ Prometheus metrics → Grafana        │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘

Legend:
  ✓ = Success path
  ✗ = Failure path
  → = Event flow direction
```

### Topics List

| Topic | Purpose | Producer | Consumers |
|-------|---------|----------|-----------|
| `cart.item_added` | Item added to cart | Cart Service | Cart Service (Redis) |
| `cart.item_removed` | Item removed from cart | Cart Service | Cart Service (Redis) |
| `cart.checkout_initiated` | User initiates checkout | Cart Service | Order Service |
| `order.created` | New order created, triggers inventory reservation | Order Service | Inventory Service |
| `order.reservation_confirmed` | Stock reserved, ready for payment | Order Service | Payment Service |
| `order.confirmed` | Order confirmed (payment successful + stock reserved) | Order Service | Notification Service |
| `order.fulfilled` | Order fulfilled (shipped/delivered) | Fulfillment Job | Order Service, Notification Service |
| `order.cancelled` | Order cancelled (payment failed or out of stock) | Order Service | Inventory Service, Notification Service |
| `inventory.reserved` | Stock reserved ✓ | Inventory Service | Order Service |
| `inventory.depleted` | Out of stock ✗ (cancel order, no payment) | Inventory Service | Order Service, Notification Service |
| `inventory.low` | Low stock alert | Inventory Service | Notification Service |
| `payment.processed` | Payment successful ✓ | Payment Service | Order Service |
| `payment.failed` | Payment failed ✗ | Payment Service | Order Service |
| `notification.send` | Send email notification | Notification Service | Mailpit (Email Service) |
| `dlq.events` | Failed message processing | Any Service | Dead Letter Handler |

### Dead Letter Queue (DLQ) Pattern

A **Dead Letter Queue (DLQ)** is a special Kafka topic (`dlq.events`) that stores messages that **failed to process** after 3 retry attempts. It prevents data loss by preserving failed events for manual review and recovery.

**Retry Strategy:**
- Attempt 1: Immediate retry
- Attempt 2: Wait 1 second, retry  
- Attempt 3: Wait 2 seconds, retry
- After 3 failures → Sent to `dlq.events` topic

**DLQ Message Format:**
```json
{
  "original_topic": "order.created",
  "event_id": "evt-123",
  "correlation_id": "corr-456",
  "error_reason": "Can't reconnect until invalid transaction is rolled back.  Please rollback() fully before proceeding (Background on this error at: https://sqlalche.me/e/20/8s2b)",
  "error_type": "PendingRollbackError",
  "retry_count": 3,
  "timestamp": 1708277445.123456,
  "payload": { "order_id": "ORD-123", "user_id": "user_001", "items": [...] }
}
```

**Key Fields:**
- `original_topic`: Kafka topic where message came from
- `error_reason`: Exact error that caused failure
- `error_type`: Exception class (e.g., `OperationalError`, `PendingRollbackError`)
- `payload`: Complete original event data

#### Viewing DLQ Messages

**Option 1: Kafka UI (Visual - Easiest)**
```
http://localhost:8080 → Topics → dlq.events → View messages
```

**Option 2: CLI (Recommended - Scriptable)**
```bash
# Quick check (exits after 5 seconds)
docker-compose exec kafka-broker-1 \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic dlq.events \
  --from-beginning \
  --max-messages 50 \
  --timeout-ms 5000

# Output: "Processed a total of 0 messages" (system healthy) or shows failed events
```

**Option 3: Automated Replay Script (Recommended for Recovery)**
```bash
python scripts/dlq-replay.py --view
```

#### Recovering from DLQ Messages

**Step 1: Identify the Root Cause**

Read `error_reason` and `error_type` from the DLQ message:

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused: postgres:5432` | PostgreSQL down | `docker-compose up -d postgres` |
| `Network unreachable` | Kafka down | `docker-compose up -d kafka-broker-1 kafka-broker-2 kafka-broker-3` |
| `PendingRollbackError` | Broken DB session | `docker-compose restart <service>` (order/cart/payment) |
| `duplicate key value` | Idempotency key collision | Check if event_id already exists |
| `timeout` | Service slow/overloaded | Increase timeouts or scale services |

**For detailed investigation:**
```bash
# Get event_id from DLQ message
EVENT_ID="evt-123"

# Search service logs for that event
docker-compose logs order-service 2>&1 | grep "$EVENT_ID" -A 5 -B 5

# Show only ERROR lines
docker-compose logs order-service 2>&1 | grep "ERROR" | tail -20
```

**Step 2: Fix the Underlying Issue**
- Restart failed services/infrastructure
- Fix application code if needed
- Verify system is healthy

> ⚠️ **IMPORTANT: Service Restart Method**
> 
> Use `docker-compose restart <service>` for quick targeted fixes (e.g., clearing broken DB transactions):
> ```bash
> docker-compose restart order-service
> ```
> 
> Use `docker-compose up -d` only for full stack startup or after modifying docker-compose.yml:
> ```bash
> docker-compose up -d  # Starts/updates ALL containers
> ```
> 
> **Why:** A single service restart is faster (~5-10 seconds) and won't interrupt healthy services. A full `up -d` is slower (~30-60 seconds) and may cause race conditions if services are starting simultaneously. For DLQ recovery, always use targeted `restart` after fixing the root cause, then verify with `dlq-replay.py --view`.

**Step 3: Replay DLQ Events (Recommended)**

```bash
# View all DLQ events
python scripts/dlq-replay.py --view

# Replay one event
python scripts/dlq-replay.py --replay <event-id>

# Replay all events (after fixing root cause)
python scripts/dlq-replay.py --replay-all
```

**Full Recovery Example (PostgreSQL Outage):**
```bash
# 1. Stop PostgreSQL and generate traffic to create DLQ events
docker-compose stop postgres
./scripts/simulate-users.py --duration 30 --users 3

# 2. Restart PostgreSQL
docker-compose up -d postgres
sleep 5

# 3. Restart affected services to clear broken connections
docker-compose restart order-service cart-service inventory-service payment-service

# 4. Replay all DLQ events
python scripts/dlq-replay.py --replay-all

# 5. Verify recovery in PostgreSQL
docker-compose exec postgres psql -U postgres -d kafka_ecom -c \
  "SELECT COUNT(*) FROM processed_events WHERE event_type = 'order.created';"
```

#### Auto-Replay DLQ Messages (Production-Ready)

**New Feature**: Automatically replay DLQ messages when threshold is exceeded + system is healthy.

For complete DLQ monitoring setup and auto-replay documentation, see:
**`MONITORING_QUICK_REFERENCE.md` → "Dead Letter Queue (DLQ) Monitoring" section**

**For comprehensive testing plan**, see: **`DLQ_TESTING_PLAN.md`** (12-phase testing strategy)

**For dashboard deployment**, see: **`DLQ_DASHBOARD_DEPLOYMENT.md`** (panel specifications + deployment methods)

**Dashboard Status:** ✅ DLQ panels already added to JSON files:
- Infrastructure Health Dashboard: 7 panels (including 3 DLQ panels: Message Count, Growth Rate, System Health)
- Microservices Dashboard: 12 panels (including 2 DLQ panels: Errors by Service, Failures vs DLQ Correlation)

This includes:
- ✅ Auto-replay daemon setup (runs continuously with health checks)
- ✅ Manual recovery procedures
- ✅ Prometheus metrics for dashboards
- ✅ Troubleshooting guide
- ✅ Dashboard panels in Infrastructure Health & Microservices dashboards

**Quick Start:**
```bash
# 1. Setup dependencies
bash scripts/setup-dlq-monitoring.sh

# 2. Start auto-replay daemon
nohup python scripts/dlq-auto-replay.py --daemon --interval 300 --threshold 50 > logs/dlq-auto-replay.log 2>&1 &

# 3. Import dashboards (automatic if using docker-compose provisioning)
# Or import manually:
# - Infrastructure Health: monitoring/dashboards/infrastructure-health-dashboard.json
# - Microservices: monitoring/dashboards/microservices-dashboard.json

# 4. View DLQ status in dashboards
# - Infrastructure Health → "Dead Letter Queue Status" section (Row 3, Panels 5-7)
# - Microservices → "DLQ Alerts" section (Row 5, Panels 11-12)
```

**Testing:**
```bash
# Run complete DLQ test suite (see MONITORING_QUICK_REFERENCE.md)
# Phase 1: Setup
bash scripts/setup-dlq-monitoring.sh

# Phase 2: Baseline (verify no errors in normal operation)
python scripts/simulate-users.py --duration 30
python scripts/dlq-replay.py --view  # Should show 0 messages

# Phase 3: Error Simulation
docker-compose stop postgres
python scripts/simulate-users.py --duration 60
python scripts/dlq-replay.py --view  # Should show accumulating messages

# Phase 4: Auto-Replay
docker-compose up -d postgres
# Wait 60s - auto-replay should trigger automatically
python scripts/dlq-replay.py --view  # Should show 0 messages (cleared)
```

See `MONITORING_QUICK_REFERENCE.md` and `DASHBOARDS_COMPLETE_SUITE.md` for complete documentation.

## Configuration

### Environment Variables (.env)

```env
# Kafka
KAFKA_BOOTSTRAP_SERVERS=kafka-broker-1:9092,kafka-broker-2:9092,kafka-broker-3:9092

# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=kafka_ecom
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Email
MAILPIT_HOST=mailpit
MAILPIT_PORT=1025
ADMIN_EMAIL=admin@kafka-ecom.local

# Service Ports
CART_SERVICE_PORT=8001
ORDER_SERVICE_PORT=8002
PAYMENT_SERVICE_PORT=8003
INVENTORY_SERVICE_PORT=8004
NOTIFICATION_SERVICE_PORT=8005

# Fulfillment Job (Order Service Background Thread)
POLL_INTERVAL_SECONDS=10           # How often to check for PAID orders
FULFILLMENT_DELAY_SECONDS=5        # Delay before marking order fulfilled (simulates shipping time)
```

**Fulfillment Job Details**:
- Runs automatically as a background thread in Order Service
- Periodically queries database for PAID orders
- Publishes `order.fulfilled` events to Kafka
- Configurable via `POLL_INTERVAL_SECONDS` and `FULFILLMENT_DELAY_SECONDS`
- No separate deployment needed - integrated into Order Service

## Monitoring & Development

### Docker Container Architecture

![Docker Containers Overview](./images/docker_containers.png)
*Docker Containers - All 21 containers running in the system architecture*

### Running Single Service

```bash
# Start infrastructure only
docker-compose up -d postgres redis kafka-broker-1 kafka-broker-2 kafka-broker-3 kafka-ui

# Run service locally
cd services/cart-service
pip install -r requirements.txt
python main.py
```

### Monitoring

**Kafka UI**: http://localhost:8080
- View topics, partitions, consumer groups
- Inspect messages in real-time

![Kafka UI - Topics Overview](./images/kafka-ui-topics-overview.png)
*Kafka UI - Topics Overview showing all topics and partitions*

![Kafka UI - Message Details](./images/kafka-ui-topics-message.png)
*Kafka UI - Message Details for real-time message inspection*

**Spark Master UI**: http://localhost:9080
- Monitor cluster resources (workers, cores, memory)
- Track running applications and jobs
- View application history

![Spark Master - Workers Overview](./images/spark_workers.png)
*Spark Master - Workers status and resources*

**Spark Worker UIs**:
- Worker 1: http://localhost:8081
- Worker 2: http://localhost:8082

**Spark Driver UI**: http://localhost:4040 (when job is running)
- SQL queries and execution plans
- Streaming query statistics
- Storage and executor details

![Spark Jobs](./images/spark_jobs.png)
*Spark Master - Job execution details and status*

![Spark Streaming Query Statistics](./images/spark_streaming_query_statistics.png)
*Spark Driver UI - Real-time query statistics and metrics*

**pgAdmin**: http://localhost:5050 (admin@kafka-ecom.com / admin)
- PostgreSQL database browser and management
- View tables, schemas, and relationships
- Run SQL queries directly

![pgAdmin - Database Browser](./images/pgadmin-database-browser.png)
*pgAdmin - Database browser showing all tables and schemas*

![pgAdmin - Database Tables](./images/pgadmin-database-tables.png)
*pgAdmin - Table structure and content viewer*

**Mailpit**: http://localhost:8025
- View all sent emails
- SMTP on port 1025

![Mailpit - Email Testing Interface](./images/mailpit.png)
*Mailpit - Email capture and testing interface*

**Prometheus**: http://localhost:9090
- Time-series metric collection
- Query builder for custom metrics
- Alert management

![Prometheus Endpoints](./images/prometheus_endpoints.png)
*Prometheus - Service endpoints and metrics collection*

![Prometheus Query Graph](./images/prometheus_query_graph.png)
*Prometheus - Query graph showing metrics over time*

**Grafana**: http://localhost:3000 (admin/admin)
- Pre-built dashboards for all components
- Custom metric visualization
- Alert notifications

![Grafana - Microservices Dashboard](./images/grafana-dashboard-microservices_1.png)
*Grafana - Microservices Dashboard #1 with service metrics*

![Grafana - Microservices Dashboard #2](./images/grafana-dashboard-microservices_2.png)
*Grafana - Microservices Dashboard #2 with additional service metrics*

![Grafana - Customer Experience Dashboard](./images/grafana-dashboard-customer_experiecne.png)
*Grafana - Customer Experience Dashboard tracking user behavior*

![Grafana - Financial Operation Dashboard](./images/grafana-dashboard-financial_operation.png)
*Grafana - Financial Operation Dashboard showing payment metrics and revenue*

![Grafana - Order Fulfillment Dashboard](./images/grafana-dashboard-order_fulfillment.png)
*Grafana - Order Fulfillment Dashboard tracking order statuses and completion rates*

![Grafana - Infrastructure Health Dashboard](./images/grafana-dashboard-infrastructure_health.png)
*Grafana - Infrastructure Health Dashboard monitoring system resources*

![Grafana - Spark Analysis Dashboard #1](./images/grafana-dashboard-spark_analysis_1.png)
*Grafana - Spark Analysis Dashboard #1 with streaming job outputs*

![Grafana - Spark Analysis Dashboard #2](./images/grafana-dashboard-spark_analysis_2.png)
*Grafana - Spark Analysis Dashboard #2 with advanced analytics insights*

## Prometheus & Grafana Setup Guide

### Quick Start

**1. Access Services**
```
Prometheus: http://localhost:9090
Grafana:    http://localhost:3000 (admin/admin)
```

**2. Configure Prometheus Data Source in Grafana**

By default, Grafana is pre-configured with Prometheus as a data source. To verify or reconfigure:

1. Open Grafana: http://localhost:3000
2. Login: `admin/admin`
3. Go to **Configuration** → **Data Sources**
4. You should see "Prometheus" already configured with URL: `http://prometheus:9090`
5. Click **Test** to verify connection

If the data source is missing:
- Click **Add data source** → Select **Prometheus**
- Set URL to: `http://prometheus:9090`
- Click **Save & Test**

### What is Prometheus?

**Prometheus** is a time-series database for collecting metrics from your services. Key concepts:

| Concept | Explanation |
|---------|------------|
| **Metrics** | Time-series data points (e.g., `http_requests_total`, `payment_success_rate`) |
| **Labels** | Metadata tags (e.g., `service="order"`, `endpoint="/orders"`) |
| **Scrape** | Prometheus pulls metrics from `/metrics` endpoint every 15 seconds |
| **Query** | PromQL language to filter and aggregate metrics |

### Collecting Metrics

All services expose metrics on `/metrics` endpoint:

```bash
# Cart Service
curl http://localhost:8001/metrics

# Order Service
curl http://localhost:8002/metrics

# Payment Service
curl http://localhost:8003/metrics

# Inventory Service
curl http://localhost:8004/metrics

# Notification Service
curl http://localhost:8005/metrics
```

Example output:
```
# HELP http_requests_total Total HTTP requests by service
# TYPE http_requests_total counter
http_requests_total{service="cart",method="POST",status="200"} 1234
http_requests_total{service="order",method="GET",status="200"} 5678
```

### Common Prometheus Queries

Use these queries in Prometheus Query Builder (http://localhost:9090):

**1. Request Rate (requests per second) by Service**
```promql
rate(http_requests_total[1m])
```
- Shows how many requests each service is receiving per second
- `[1m]` = calculate rate over 1-minute window
- Use for: Monitoring traffic, detecting spikes, debugging load

**2. Error Rate by Service**
```promql
rate(http_requests_total{status=~"5.."}[1m]) / rate(http_requests_total[1m]) * 100
```
- Percentage of requests returning 5xx errors
- Target: < 1% in healthy system
- Use for: Alerting on service failures, debugging issues

**3. Payment Success Rate (Last Hour)**
```promql
sum(rate(payment_processing_total{status="success"}[1h])) / sum(rate(payment_processing_total[1h])) * 100
```
- Payment success percentage
- Target: > 95%
- Use for: Financial monitoring, SLA tracking

**4. Order Processing Latency P95 (95th Percentile)**
```promql
histogram_quantile(0.95, rate(order_processing_duration_seconds_bucket[5m]))
```
- 95% of orders complete within this time
- Target: < 1 second
- Use for: Performance SLA tracking, debugging slowdowns

**5. Inventory Reservation Success Rate**
```promql
sum(rate(inventory_reservation_total{status="success"}[1h])) / sum(rate(inventory_reservation_total[1h])) * 100
```
- Stock reservation success percentage
- Target: > 98%
- Use for: Inventory system health, overselling detection

**6. Cart Operations Breakdown**
```promql
sum by (operation) (rate(cart_operations_total[1m]))
```
- Requests per second by operation (add, remove, update)
- Use for: Understanding customer behavior, cart service load

**7. Database Connection Pool Usage**
```promql
(pg_stat_activity_count / pg_setting_max_connections) * 100
```
- Active database connections as % of max pool
- Alert if > 80%
- Use for: Database performance, connection leak detection

**8. Saga Compensation Rate (Rollbacks)**
```promql
rate(saga_compensation_total[5m])
```
- Transactions being rolled back due to failures
- Target: < 1% of orders
- Use for: System reliability, transaction integrity

**9. Idempotency Cache Hit Rate**
```promql
rate(idempotency_cache_hits_total[1m]) / (rate(idempotency_cache_hits_total[1m]) + rate(idempotency_cache_misses_total[1m])) * 100
```
- Cache effectiveness for preventing duplicate processing
- Target: > 90%
- Use for: Financial reliability, duplicate prevention

**10. Kafka Message Publishing Rate by Topic**
```promql
sum by (topic) (rate(kafka_message_published_total[1m]))
```
- Messages/second per topic
- Use for: Event flow monitoring, bottleneck detection

### Using Prometheus Query Builder

**Step 1: Access Query Editor**
- Go to http://localhost:9090
- Top menu: Click **Graph** (or **Table** for tabular data)
- In the query box, type your PromQL query

**Step 2: Execute Query**
- Press **Enter** or click **Execute**
- Results display as graph or table below

**Step 3: Customize Visualization**
- **Time Range** (top right): Change from 1h to custom range
- **Step**: How often to sample data (auto or manual)
- **Legend**: Show/hide metric labels below graph
- **Refresh**: Auto-update interval

**Step 4: Export/Share**
- Click **Share** (top right) to share query URL
- Click **Export** to download as PNG or JSON

### What is Grafana?

**Grafana** is a visualization platform that:
- Connects to Prometheus and queries metrics
- Creates beautiful dashboards with panels, graphs, gauges, tables
- Shows business metrics, operational health, and system performance
- Pre-built dashboards tailored for different teams

### Pre-Built Dashboards Overview

| Dashboard | Purpose | Team | URL |
|-----------|---------|------|-----|
| **Microservices Dashboard** | Service health, request rates, latency | Platform | http://localhost:3000/d/microservices-dashboard |
| **Order Fulfillment** | Order status, payment success, notifications | Operations | http://localhost:3000/d/order-fulfillment-dashboard |
| **Financial Operations** | Payment metrics, transaction reliability | Finance | http://localhost:3000/d/financial-operations-dashboard |
| **Customer Experience** | Conversion, cart operations, user behavior | Product/UX | http://localhost:3000/d/customer-experience-dashboard |
| **Infrastructure Health** | System resources, HTTP status distribution, cache | DevOps/SRE | http://localhost:3000/d/infrastructure-health-dashboard |
| **Spark Analytics** | Revenue trends, fraud detection, inventory velocity | Analytics | http://localhost:3000/d/spark-analytics-dashboard |

See [DASHBOARDS_COMPLETE_SUITE.md](./DASHBOARDS_COMPLETE_SUITE.md) for detailed documentation on each dashboard.

### Accessing Dashboards

**Method 1: Web UI**
1. Open Grafana: http://localhost:3000
2. Login: `admin/admin`
3. Click **Dashboards** in left sidebar
4. Click the dashboard you want

**Method 2: Direct Links**
Click any dashboard directly:
- [Microservices](http://localhost:3000/d/microservices-dashboard)
- [Order Fulfillment](http://localhost:3000/d/order-fulfillment-dashboard)
- [Financial Operations](http://localhost:3000/d/financial-operations-dashboard)
- [Customer Experience](http://localhost:3000/d/customer-experience-dashboard)
- [Infrastructure Health](http://localhost:3000/d/infrastructure-health-dashboard)
- [Spark Analytics](http://localhost:3000/d/spark-analytics-dashboard)

### Creating Custom Dashboards

**1. Create New Dashboard**
- Grafana → **+** icon (left sidebar) → **Dashboard**
- Click **Add new panel**

**2. Add Panel**
- Click **Add new panel** or **+** button
- In Data Source dropdown, select **Prometheus**
- In Metrics section, start typing metric name (e.g., `payment_success_rate`)
- Choose visualization type (Graph, Gauge, Stat, Table, etc.)

**3. Configure Panel**
- **Title**: Give panel a descriptive name
- **Query**: Use PromQL query from "Common Queries" section above
- **Legend**: Show/hide metric labels
- **Thresholds**: Set color-coded alerts (green/yellow/red)

**4. Save Dashboard**
- Click **Save** (top right) → Enter dashboard name → Save

### Troubleshooting Prometheus & Grafana

| Issue | Solution |
|-------|----------|
| **Grafana won't connect to Prometheus** | Verify Prometheus running: `docker-compose logs prometheus`. Check data source URL: `http://prometheus:9090` (use container name, not localhost) |
| **No metrics appearing in Prometheus** | Metrics endpoint down. Test: `curl http://localhost:8001/metrics`. Start services: `docker-compose up -d`. Wait 30s for scrape to complete |
| **"No data" in Grafana dashboards** | (1) Verify data source connection (Configuration → Data Sources → Test). (2) Generate traffic: `./scripts/simulate-users.py`. (3) Wait 30+ seconds for metrics to appear |
| **Prometheus storage full** | Old metrics data. Clean up: `docker-compose down -v`. Or reduce retention: Edit `monitoring/prometheus.yml` → `global.retention` |
| **Can't login to Grafana** | Default: `admin/admin`. Change password: Grafana → Configuration → Users → Change Password. Reset: `docker-compose exec grafana grafana-cli admin reset-admin-password newpassword` |
| **Grafana panels show errors** | (1) Check query syntax in panel. (2) Verify metric exists in Prometheus. (3) Look at panel error message for details. (4) Try simpler query first |
| **Slow query response** | Reduce time range or use shorter `[time_window]` in query. Example: `rate(http_requests_total[5m])` instead of `[1h]` |

### Performance Tips

- **Generate Test Traffic**: Dashboards need data. Run: `./scripts/simulate-users.py`
- **Auto-Refresh**: Set dashboard refresh to 30 seconds (default) for real-time monitoring
- **Time Range**: Use "Last 1 hour" for fastest queries, "Last 24 hours" for trend analysis
- **Metric Cardinality**: High label combinations slow down queries (e.g., tracking every unique user ID)

### Next Steps

1. ✅ **Verify data source** - Test Prometheus connection in Grafana
2. ✅ **Generate traffic** - Run `./scripts/simulate-users.py` to populate metrics
3. ✅ **Explore dashboards** - Visit each pre-built dashboard
4. ✅ **Try queries** - Go to Prometheus UI, try common queries above
5. ✅ **Create custom dashboard** - Build dashboard for your use case

**PostgreSQL**:
```bash
psql postgresql://postgres:postgres@localhost:5432/kafka_ecom
```

**Redis**:
```bash
redis-cli -h localhost -p 6379
KEYS cart:*
```

## Performance Notes

- **Payment Success Rate**: 80%
- **Stock Reservation Retries**: 3 with exponential backoff (1s, 2s, 4s)
- **Event Processing Retries**: 3 retries before DLQ
- **Outbox Poll Interval**: 2 seconds
- **Cart TTL**: 24 hours

## Troubleshooting

### Services won't start
```bash
# Check logs
docker-compose logs cart-service
docker-compose logs order-service
docker-compose logs spark-master

# Wait for Kafka to stabilize
docker-compose logs kafka-broker-1 | grep "started"
```

### Spark Job Issues

**ModuleNotFoundError: No module named 'spark_session'**

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

```bash
# ❌ Problem: Running jobs directly from analytics/jobs/ directory
.venv/bin/python analytics/jobs/cart_abandonment.py
# Result: ModuleNotFoundError: No module named 'spark_session'

# ✓ Solution 1: Run from project root with proper path
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom
.venv/bin/python -c "import sys; sys.path.insert(0, 'analytics'); from analytics.jobs.cart_abandonment import cart_abandonment; cart_abandonment()"

# ✓ Solution 2: Use the helper script (RECOMMENDED)
./scripts/spark/run-spark-job.sh cart_abandonment
```

**Permission denied: ./scripts/spark/run-spark-job.sh**

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

```bash
# ❌ Problem: Scripts don't have execute permission
./scripts/spark/run-spark-job.sh cart_abandonment
# Result: zsh: permission denied: ./scripts/spark/run-spark-job.sh

# ✓ Solution: Make all scripts executable
chmod +x scripts/*.sh
chmod +x scripts/spark/*.sh

# Verify permission is set correctly
ls -la scripts/spark/run-spark-job.sh
# Should show: -rwxr-xr-x (with x for execute)
```

**Spark job runs but no output**

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

```bash
# Check if Kafka topics have data
# (Run from project root)
docker-compose exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-servers localhost:9092 \
  --topic cart.item_added \
  --from-beginning \
  --max-messages 5

# Check PostgreSQL for results (Run from project root)
docker-compose exec postgres psql -U postgres -d kafka_ecom \
  -c "SELECT COUNT(*) FROM cart_abandonment;"

# Monitor Spark job (Open in browser)
open http://localhost:4040/

# Check Spark Master logs (Run from project root)
docker-compose logs spark-master
```

**Port already in use (Spark UI port 4040)**
```bash
# If port 4040 is busy, Spark will use 4041, 4042, etc.
# Check Spark UI on: http://localhost:4040 (or 4041, 4042...)

# Or kill existing Spark process
pkill -f "org.apache.spark"
```

### Spark Jobs Directory Structure

```
analytics/                      # Spark cluster & jobs
├── spark_session.py           # Spark session factory (shared by all jobs)
├── metrics_exporter.py        # Prometheus metrics exporter for Spark jobs
├── Dockerfile                 # Spark cluster Docker image
├── Dockerfile.exporter        # Metrics exporter container
├── requirements.txt           # Python dependencies
├── jars/                      # Spark external JARs
│   ├── kafka-clients-3.7.0.jar
│   ├── spark-sql-kafka-0-10_2.12-3.5.1.jar
│   └── postgresql-42.7.1.jar
├── jobs/                      # PySpark streaming jobs (5 total)
│   ├── revenue_streaming.py   # 1-minute revenue aggregation
│   ├── fraud_detection.py     # 5-minute fraud pattern detection
│   ├── cart_abandonment.py    # 30-minute cart abandonment analysis
│   ├── inventory_velocity.py  # 1-hour product sales velocity ranking
│   └── operational_metrics.py # Topic-level system health metrics
└── logs/                      # Checkpoint and log data
    └── checkpoints/           # Spark streaming checkpoints (fault tolerance)
```

**Important Notes:**
- ✅ All jobs must be run from **project root**, not from `analytics/jobs/` directory
- ✅ Use helper script: `./scripts/spark/run-spark-job.sh <job_name>`
- ✅ Jobs read from Kafka topics and write to PostgreSQL tables
- ✅ Metrics exported to Prometheus (`localhost:9090`) for Grafana dashboards
- ✅ Checkpoints enable recovery if jobs are stopped/restarted

### Spark Cluster Issues

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

```bash
# Check Spark Master is running
docker-compose logs spark-master

# Check workers are connected (Open in browser)
open http://localhost:9080  # Should show 2 workers

# Verify worker resources
docker-compose logs spark-worker-1
docker-compose logs spark-worker-2

# Submit test job (from project root)
./scripts/spark/run-spark-job.sh revenue_streaming
```

### Database connection errors

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

```bash
# Verify PostgreSQL is running
docker-compose exec postgres pg_isready

# Check database exists (Run from project root)
docker-compose exec postgres psql -U postgres -c "\\l"
```

**Cannot simulate users when PostgreSQL is stopped:**

If you get "❌ Failed to fetch products (HTTP 500)" when running simulate-users.py:
- ✅ This is EXPECTED - PostgreSQL must be running for inventory service to respond
- ✅ To test DLQ, start the simulation FIRST, then stop PostgreSQL mid-simulation
- ✅ See "Testing DLQ: Simulate Error Conditions" section for proper procedure

### Messages not flowing
```bash
# Check Kafka topics in Kafka UI
open http://localhost:8080

# Check consumer groups
docker-compose exec kafka-broker-1 \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --list
```

## Cleanup

```bash
# Stop all containers
docker-compose down

# Remove volumes (data loss!)
docker-compose down -v

# View container logs
docker-compose logs -f cart-service
```

## Architecture Highlights

### Production-Style Inventory-First Flow
Order Service implements the production-standard e-commerce pattern:
- **Reserve inventory BEFORE payment**: Prevents charging for out-of-stock items
- **Automatic order cancellation**: If inventory unavailable, no customer charge
- **Complete order lifecycle**: PENDING → RESERVATION_CONFIRMED → PAID → FULFILLED → CANCELLED
- **All 6 event handlers**: Cart, Inventory (reserved/depleted), Payment (success/failure), Fulfillment
- **Key advantage**: No refunds needed, better customer experience

### Background Fulfillment Job
Automatic order fulfillment as integrated background thread:
- Runs as daemon thread in Order Service (no separate deployment)
- Polls database every 10 seconds for PAID orders
- Publishes `order.fulfilled` events with tracking numbers
- Configurable delays via environment variables
- Simulates realistic shipping delays for testing

### Saga Orchestration with Outbox Pattern & Idempotency
Order Service implements Saga Choreography with:
- **Outbox Pattern**: Order + OutboxEvent created in atomic transaction, background thread publishes every 2 seconds
- **Guaranteed Delivery**: Even if service crashes before Kafka publish, OutboxPublisher restarts and republishes
- **Idempotency Tracking**: processed_events table prevents duplicate processing with UNIQUE(event_id) constraint
- **Result**: No event loss, no duplicate charges/emails, practical exactly-once semantics

👉 **See [IDEMPOTENCY_IMPLEMENTATION.md](./IDEMPOTENCY_IMPLEMENTATION.md)** for detailed architecture, code examples, crash recovery scenarios, test procedures, and verification queries.

### Optimistic Locking
Inventory Service uses version-based optimistic locking:
- Stock = numeric field, version = increment counter
- Retry up to 3 times on concurrent conflicts
- Prevents overselling in high-concurrency scenarios

### DLQ Pattern
All consumers implement Dead Letter Queue:
- Retry up to 3 times with exponential backoff
- Failed messages sent to `dlq.events` topic
- Prevents infinite retry loops

### Streaming Analytics
Spark cluster with:
- **Distributed Processing**: 1 master + 2 workers (8 cores, 8GB total)
- **Watermarking**: 10-minute delay for late-arriving data
- **Tumbling/Sliding Windows**: For time-based aggregation
- **Stream-Stream Joins**: For cart abandonment detection
- **Dense Ranking**: For top product inventory analysis
- **Checkpointing**: Fault-tolerant state management

## License

MIT

## Support

For issues, check:
1. Docker logs: `docker-compose logs <service>`
2. Kafka UI: http://localhost:8080
3. Spark Master UI: http://localhost:9080
4. Mailpit: http://localhost:8025
5. PostgreSQL queries against analytics tables

## Spark Cluster Details

### Architecture
- **Standalone Mode**: Self-managed cluster without YARN or Mesos
- **Master**: Allocates resources and schedules applications
- **Worker 1**: Driver + Executor (can submit and run jobs)
- **Worker 2**: Executor only (runs tasks)

### Resource Allocation
```
Total Cluster Resources:
- Cores: 8 (4 per worker)
- Memory: 8GB (4GB per worker)
```

### Submitting Jobs

**Using Helper Script** (RECOMMENDED)

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

```bash
./scripts/spark/run-spark-job.sh revenue_streaming
```

**Manual Submission**

**Run from: Project root directory** (`/Users/tong/KafkaProjects/kafka-microservices-spark-ecom`)

```bash
docker exec spark-worker-1 /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --deploy-mode client \
  --driver-memory 2g \
  --executor-memory 2g \
  --total-executor-cores 4 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 \
  /opt/spark-apps/revenue_streaming.py
```

### Monitoring Jobs
1. **Spark Master UI** (http://localhost:9080): View running applications
2. **Spark Driver UI** (http://localhost:4040): When job is active, see query details
3. **Worker UIs**: http://localhost:8081, http://localhost:8082

### Data Flow
```
Kafka Topics → Spark Streaming Jobs → PostgreSQL Analytics Tables
```

Each job continuously reads from Kafka, aggregates data, and writes results to PostgreSQL.

## Quick Access URLs & Ports

### All Ports Used in This Project (21 total)

#### Kafka Cluster
| Service | Host Port | Purpose |
|---------|-----------|---------|
| kafka-broker-1 | 9092, 9094 | Kafka brokers |
| kafka-broker-2 | 9093, 9095 | Kafka brokers |
| kafka-broker-3 | 9091, 9096 | Kafka brokers |
| kafka-ui | 8080 | Web UI for Kafka management |

#### Spark Cluster
| Service | Host Port | Purpose |
|---------|-----------|---------|
| spark-master | 9080, 7077 | Spark Master Web UI & communication |
| spark-worker-1 | 8081, 4040 | Worker UI & Driver UI |
| spark-worker-2 | 8082 | Worker 2 UI |

#### Monitoring & Metrics
| Service | Host Port | Purpose |
|---------|-----------|---------|
| prometheus | 9090 | Prometheus metrics & queries |
| grafana | 3000 | Grafana dashboards |
| spark-metrics-exporter | 9097 | Spark analytics metrics exporter |

#### Database & Cache
| Service | Host Port | Purpose |
|---------|-----------|---------|
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Redis cache |

#### Microservices
| Service | Host Port | Purpose |
|---------|-----------|---------|
| cart-service | 8001 | Cart REST API |
| order-service | 8002 | Order REST API |
| payment-service | 8003 | Payment REST API |
| inventory-service | 8004 | Inventory REST API |
| notification-service | 8005 | Notification REST API |

#### Email
| Service | Host Port | Purpose |
|---------|-----------|---------|
| mailpit | 1025, 8025 | SMTP & Web UI |

### Quick Access URLs

**Monitoring & Management:**
- Prometheus: http://localhost:9090 (metrics)
- Grafana: http://localhost:3000 (dashboards - admin/admin)
- Kafka UI: http://localhost:8080
- Spark Master UI: http://localhost:9080 (⚡ moved from 8080)
- Spark Worker 1 UI: http://localhost:8081
- Spark Worker 2 UI: http://localhost:8082
- Spark Driver UI: http://localhost:4040 (when running)
- Mailpit UI: http://localhost:8025

**Microservices APIs (Swagger docs):**
- Cart: http://localhost:8001/docs
- Order: http://localhost:8002/docs
- Payment: http://localhost:8003/docs
- Inventory: http://localhost:8004/docs
- Notification: http://localhost:8005/docs

**Database Connections:**
- PostgreSQL: localhost:5432 (user: postgres, pwd: postgres, db: kafka_ecom)
- Redis: localhost:6379

## Docker Images & Architecture Compatibility

### ARM64 (Apple Silicon) Native Support

All services run natively on ARM64 architecture without emulation:

| Service | Image | Architecture |
|---------|-------|--------------|
| Kafka Brokers | `apache/kafka:latest` | ARM64 native ✅ |
| Spark | `apache/spark:3.5.1` | ARM64 native ✅ |
| PostgreSQL | `postgres:15` | ARM64 native ✅ |
| Redis | `redis:7-alpine` | ARM64 native ✅ |
| Kafka UI | `provectuslabs/kafka-ui:latest` | ARM64 native ✅ |
| Mailpit | `axllent/mailpit:latest` | ARM64 native ✅ |
| Microservices | Python 3.11-slim | ARM64 native ✅ |

**Total: 15/15 containers running ARM64-native** 🎉

## Auto-Refill Inventory Utility

For sustained load testing without running out of stock:

### Quick Start
```bash
# Install dependency (one-time)
pip install psycopg2-binary

# Run auto-refill service
./scripts/auto-refill-inventory.py

# In another terminal, run load test
./scripts/simulate-users.py --mode continuous --duration 600 --users 20
```

### Configuration Options
```bash
./scripts/auto-refill-inventory.py [options]

--threshold N           # Refill when stock < N (default: 20)
--refill-quantity N     # Add N units per refill (default: 50)
--interval N            # Check every N seconds (default: 10)
--verbose              # Debug logging
```

### Example Use Cases
```bash
# Light load (default)
./scripts/auto-refill-inventory.py

# Heavy stress test
./scripts/auto-refill-inventory.py --threshold 10 --refill-quantity 100

# Realistic inventory
./scripts/auto-refill-inventory.py --threshold 30 --refill-quantity 30 --interval 15

# Debug mode
./scripts/auto-refill-inventory.py --verbose
```

### How It Works
- Connects to PostgreSQL and monitors product stock every N seconds
- When stock drops below threshold, automatically adds refill quantity units
- Runs in background alongside your load tests
- Press Ctrl+C to stop and see statistics (total refills, units added, timing)

For complete details, see the script's built-in docstring: `head -250 ./scripts/auto-refill-inventory.py`
