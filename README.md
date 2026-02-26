# Kafka Microservices E-Commerce with Spark Analytics

A complete event-driven e-commerce backend built with Apache Kafka, FastAPI microservices, PostgreSQL, Redis, and PySpark analytics.

**Live Components**: Kafka (3 brokers), PostgreSQL, Redis, Spark (1 master + 2 workers), FastAPI microservices, pgAdmin, Mailhog, Kafka UI

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
14. [Troubleshooting](#troubleshooting)
15. [Cleanup](#cleanup)
16. [Architecture Highlights](#architecture-highlights)

## Architecture

### Microservices
- **Cart Service** (Port 8001): Shopping cart management with Redis
- **Order Service** (Port 8002): Order orchestration with saga pattern and background fulfillment job
- **Payment Service** (Port 8003): Payment processing (80% success rate)
- **Inventory Service** (Port 8004): Stock management with optimistic locking
- **Notification Service** (Port 8005): Email notifications via Mailhog

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
│   ├── API.md                        # API endpoint documentation
│   ├── PORTS.md                      # Port reference guide
│   ├── DOCKER_IMAGES.md              # Docker image information
│   └── TEST_*.md                     # Testing workflow guides
│
├── 🔧 Scripts
│   ├── clean-database.sh             # Clean PostgreSQL data
│   ├── clean-kafka.sh                # Clean Kafka topics
│   ├── run-spark-job.sh              # Submit Spark jobs
│   ├── generate-orders.sh            # Generate test orders
│   ├── test-complete-workflow.sh     # Run complete workflow test
│   └── view_carts.py                 # View Redis carts (Python)
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
│   ├── requirements.txt              # Spark dependencies
│   │
│   └── jobs/                         # Streaming jobs (5 jobs)
│       ├── revenue_streaming.py      # 1-min revenue aggregation
│       ├── fraud_detection.py        # 5-min fraud detection
│       ├── cart_abandonment.py       # 30-min cart abandonment
│       ├── inventory_velocity.py     # 1-hour inventory analysis
│       └── operational_metrics.py    # Topic-level monitoring
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

# Mailhog Web UI (emails)
open http://localhost:8025
```

### 4. Run Spark Analytics Jobs

```bash
# Submit a streaming job to the Spark cluster
./run-spark-job.sh revenue_streaming

# Or run manually
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
| **Kafka UI** | http://localhost:8080 | None | View topics, partitions, messages |
| **Spark Master** | http://localhost:9080 | None | Monitor cluster resources |
| **Spark Worker 1** | http://localhost:8081 | None | Worker 1 tasks and executor details |
| **Spark Worker 2** | http://localhost:8082 | None | Worker 2 tasks and executor details |
| **Spark Driver UI** | http://localhost:4040 | None | Active job SQL and streaming stats |
| **pgAdmin** | http://localhost:5050 | See below | PostgreSQL database browser |
| **Mailhog** | http://localhost:8025 | None | Email testing and viewing |
| **Redis Commander** | http://localhost:6379 | None | Redis key-value browser |

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
   - Name: `kafka_ecom_db`
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
SELECT window_start, total_orders, total_revenue, avg_order_value 
FROM revenue_metrics ORDER BY window_start DESC LIMIT 20;

-- View fraud alerts
SELECT * FROM fraud_alerts ORDER BY created_at DESC LIMIT 10;

-- View cart abandonment
SELECT * FROM cart_abandonment ORDER BY abandoned_at DESC LIMIT 10;

-- Top selling products
SELECT product_id, SUM(units_sold) as total_units, COUNT(*) as windows
FROM inventory_velocity
GROUP BY product_id ORDER BY total_units DESC LIMIT 20;

-- View all table sizes and record counts
SELECT tablename, n_live_tup as records, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_stat_user_tables ORDER BY tablename;
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
python view_carts.py
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

Two helper scripts are provided:

```bash
# Clean PostgreSQL (truncate all tables)
./clean-database.sh

# Clean Kafka (delete all messages from all topics)
./clean-kafka.sh

# Both together for complete reset
./clean-database.sh && ./clean-kafka.sh
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

### Cart Service

```bash
# Add item to cart
curl -X POST http://localhost:8001/cart/user123/items \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "PROD-123",
    "quantity": 2,
    "price": 49.99
  }'

# Get cart
curl http://localhost:8001/cart/user123

# Remove item
curl -X DELETE http://localhost:8001/cart/user123/items/PROD-123

# Checkout
curl -X POST http://localhost:8001/cart/user123/checkout
```

### Inventory Service

```bash
# List products
curl http://localhost:8004/products

# Get product details
curl http://localhost:8004/products/PROD-001
```

### Order Service

```bash
# Get order details
curl http://localhost:8002/orders/ORD-ABC123

# Get all orders for a user
curl http://localhost:8002/orders/user/user123

# Health check
curl http://localhost:8002/health
```

### Payment Service

```bash
# Get payment details
curl http://localhost:8003/payments/PAY-XYZ789
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

-- Analytics
CREATE TABLE revenue_metrics (
  window_start TIMESTAMP,
  window_end TIMESTAMP,
  total_revenue FLOAT,
  order_count BIGINT,
  avg_order_value FLOAT
);

CREATE TABLE fraud_alerts (
  user_id VARCHAR(255),
  window_start TIMESTAMP,
  window_end TIMESTAMP,
  order_count BIGINT,
  max_order_amount FLOAT,
  payment_count BIGINT,
  alert_type VARCHAR(100)
);

CREATE TABLE cart_abandonment (
  user_id VARCHAR(255),
  product_id VARCHAR(255),
  item_added_time TIMESTAMP
);

CREATE TABLE inventory_velocity (
  product_id VARCHAR(255),
  window_start TIMESTAMP,
  window_end TIMESTAMP,
  units_sold BIGINT,
  rank INTEGER
);

CREATE TABLE operational_metrics (
  metric_name VARCHAR(100),
  value FLOAT,
  topic VARCHAR(255),
  window_start TIMESTAMP
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
   - Consumer: Mailhog (Email Service)

9. **Email delivered**
   - Order confirmation email sent via Mailhog

10. **Order Service fulfillment job publishes** 
    - Event: `order.fulfilled` (Order shipped with tracking number)
    - Producer: Fulfillment Job (Order Service background thread)
    - Consumer: Order Service, Notification Service

11. **Notification Service sends shipment email** 
    - Event consumed: `order.fulfilled`
    - Includes: Tracking number, estimated delivery date
    - Publishes: `notification.send` event
    - Producer: Notification Service
    - Consumer: Mailhog (Email Service)

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
   - Consumer: Mailhog (Email Service)
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
   - Consumer: Mailhog (Email Service)
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
│                    KAFKA TOPICS (16 Total)                                    │
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
│  ├─ notification.send ──────────────→ Mailhog (Email Service)                 │
│  ├─ fraud.detected ─────────────────→ Fraud Detection (Spark)                 │
│  └─ dlq.events ─────────────────────→ Dead Letter Queue                       │
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
| `notification.send` | Send email notification | Notification Service | Mailhog (Email Service) |
| `fraud.detected` | Fraud detection alert | Fraud Detection (Spark) | Monitoring |
| `dlq.events` | Failed message processing | Any Service | Dead Letter Handler |

### Dead Letter Queue (DLQ) Pattern

A **Dead Letter Queue (DLQ)** is a special Kafka topic (`dlq.events`) that stores messages that **failed to process** after retrying multiple times. It prevents:
- ❌ Infinite retry loops that crash services
- ❌ Data loss (failed messages are preserved)
- ❌ System hangs waiting for problematic messages

#### How It Works

```
Normal Flow:
Message → Service → Process → Success ✓

Error Flow:
Message → Service → Error → Retry 1 → Retry 2 → Retry 3 → FAIL ✗
                                                              ↓
                                                         DLQ Topic
                                                              ↓
                                                      Manual Review
```

#### Retry Logic

Each service implements **exponential backoff**:
- Attempt 1: Immediate retry
- Attempt 2: Wait 1 second, retry
- Attempt 3: Wait 2 seconds, retry
- After 3 failures → Send to `dlq.events` topic

#### Message Format in DLQ

```json
{
  "original_topic": "order.created",
  "event_id": "evt-123",
  "error_reason": "Database connection failed",
  "retry_count": 3,
  "timestamp": "2026-02-18T15:30:45Z",
  "payload": { /* original event data */ }
}
```

#### How to Investigate DLQ Messages

**1. View DLQ messages in Kafka UI:**
```
http://localhost:8080 → Topics → dlq.events → View messages
```

**2. Check service logs:**
```bash
docker-compose logs order-service | grep "DLQ"
docker-compose logs payment-service | grep "ERROR"
```

**3. Consume DLQ messages:**
```bash
docker-compose exec kafka-broker-1 \
  /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic dlq.events \
  --from-beginning
```

#### Handling DLQ Messages

| Option | Process | Use Case |
|--------|---------|----------|
| **Manual Fix & Replay** | Fix issue → consume from DLQ → replay | Most common |
| **Automated Handler** | Service monitors DLQ, alerts ops | Production systems |
| **Manual Intervention** | Review in Kafka UI, delete or fix | One-off issues |

#### Best Practices

1. ✅ **Monitor DLQ regularly** - Set up alerts when messages appear
2. ✅ **Log detailed error info** - Include stack trace and original data
3. ✅ **Don't ignore DLQ** - Messages = potential data loss
4. ✅ **Test DLQ behavior** - Simulate failures and verify recovery

#### In Our E-Commerce System

When a customer's order fails:
```
Customer checks out
  ↓
Order Service creates → order.created published
  ↓
Inventory Service receives order.created
  ↓
Try to reserve stock from database → FAIL (Attempt 1)
  ↓
Retry after 1 second → FAIL (Attempt 2)
  ↓
Retry after 2 seconds → FAIL (Attempt 3)
  ↓
All retries fail → Message sent to dlq.events
  ↓
Payment Service never receives order.reservation_confirmed
  ↓
Order stuck in PENDING state (never progresses to payment) ✗
  ↓
Operations team sees alert, fixes database connection
  ↓
Replay message from DLQ
  ↓
Inventory reserved → order.reservation_confirmed → payment processes
  ↓
Order fulfills successfully ✓
```

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
MAILHOG_HOST=mailhog
MAILHOG_PORT=1025
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

**Spark Master UI**: http://localhost:9080
- Monitor cluster resources (workers, cores, memory)
- Track running applications and jobs
- View application history

**Spark Worker UIs**:
- Worker 1: http://localhost:8081
- Worker 2: http://localhost:8082

**Spark Driver UI**: http://localhost:4040 (when job is running)
- SQL queries and execution plans
- Streaming query statistics
- Storage and executor details

**Mailhog**: http://localhost:8025
- View all sent emails
- SMTP on port 1025

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

### Spark cluster issues
```bash
# Check Spark Master is running
docker logs spark-master

# Check workers are connected
open http://localhost:9080  # Should show 2 workers

# Verify worker resources
docker logs spark-worker-1
docker logs spark-worker-2

# Submit test job
./run-spark-job.sh revenue_streaming
```

### Database connection errors
```bash
# Verify PostgreSQL is running
docker-compose exec postgres pg_isready

# Check database exists
docker-compose exec postgres psql -U postgres -c "\\l"
```

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

### Saga Orchestration
Order Service implements the Outbox Pattern + Saga Choreography:
- Transactions: Order + OutboxEvent created atomically
- Background thread publishes events every 2 seconds
- Idempotency tracking prevents duplicate processing

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
4. Mailhog: http://localhost:8025
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

**Using Helper Script** (Recommended):
```bash
./run-spark-job.sh revenue_streaming
```

**Manual Submission**:
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
