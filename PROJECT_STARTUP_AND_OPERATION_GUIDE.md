# Complete Project Startup & Operation Guide

## Overview

This guide walks you through starting the complete Kafka microservices e-commerce platform, simulating real users, running Spark analytics jobs, and monitoring everything via Grafana dashboards.

**Total Startup Time:** 5-10 minutes
**Required Memory:** ~8GB RAM (Docker Desktop)
**Required Disk:** ~5GB (images + volumes)

---

## Part 1: System Architecture & Dependencies

### Service Dependency Graph
```
┌─────────────────────────────────────────────┐
│ Kafka Cluster (3 brokers)                   │
│ ├─ kafka-broker-1:9092                      │
│ ├─ kafka-broker-2:9092                      │
│ └─ kafka-broker-3:9092                      │
│                                             │
│ Topics (auto-created):                      │
│ ├─ order.created                            │
│ ├─ order.confirmed                          │
│ ├─ payment.processed                        │
│ ├─ inventory.reserved                       │
│ ├─ notification.email_sent                  │
│ └─ notification.sms_sent                    │
└─────────────────────────────────────────────┘
        ↓ (Events)
┌─────────────────────────────────────────────┐
│ Microservices (FastAPI + Kafka Consumer)    │
│ ├─ Cart Service (8001) → Redis              │
│ ├─ Order Service (8002) → PostgreSQL        │
│ ├─ Payment Service (8003) → PostgreSQL      │
│ ├─ Inventory Service (8004) → PostgreSQL    │
│ └─ Notification Service (8005) → MailHog    │
└─────────────────────────────────────────────┘
        ↓ (SQL queries)
┌─────────────────────────────────────────────┐
│ PostgreSQL Database (5432)                  │
│ ├─ orders, payments, inventory              │
│ ├─ processed_events (idempotency)           │
│ └─ outbox_events (saga pattern)             │
└─────────────────────────────────────────────┘
        ↓ (Reads events)
┌─────────────────────────────────────────────┐
│ Spark Analytics Cluster                     │
│ ├─ Spark Master (7077)                      │
│ ├─ Spark Worker 1 (4040)                    │
│ └─ Spark Worker 2                           │
│                                             │
│ Jobs (Structured Streaming):                │
│ ├─ revenue_streaming (1-min windows)        │
│ ├─ fraud_detection (5-min windows)          │
│ ├─ inventory_velocity (1-hour windows)      │
│ ├─ cart_abandonment (15-min windows)        │
│ └─ operational_metrics                      │
│                                             │
│ Output → PostgreSQL tables                  │
│ ├─ revenue_metrics                          │
│ ├─ fraud_alerts                             │
│ ├─ inventory_velocity                       │
│ ├─ cart_abandonment                         │
│ └─ operational_metrics                      │
└─────────────────────────────────────────────┘
        ↓ (Polls every 30s)
┌─────────────────────────────────────────────┐
│ Prometheus (9090)                           │
│ ├─ Scrapes /metrics from services (15s)     │
│ └─ Scrapes /metrics from exporter (30s)     │
└─────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────┐
│ Grafana (3000)                              │
│ ├─ Services Dashboard                       │
│ └─ Spark Analytics Dashboard                │
└─────────────────────────────────────────────┘

Supporting Services:
├─ pgAdmin (5050) - PostgreSQL UI
├─ Kafka UI (8080) - Kafka cluster UI
└─ MailHog (8025) - Email testing UI
```

---

## Part 2: Starting the Complete System

### Step 1: Start Docker Compose (Everything)

```bash
# Navigate to project root
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom

# Start all services in background
docker-compose up -d

# Expected output:
# Creating kafka-broker-1 ... done
# Creating kafka-broker-2 ... done
# Creating kafka-broker-3 ... done
# Creating postgres ... done
# Creating redis ... done
# Creating mailhog ... done
# Creating cart-service ... done
# Creating order-service ... done
# Creating payment-service ... done
# Creating inventory-service ... done
# Creating notification-service ... done
# Creating spark-master ... done
# Creating spark-worker-1 ... done
# Creating spark-worker-2 ... done
# Creating prometheus ... done
# Creating grafana ... done
# Creating spark-metrics-exporter ... done
```

### Step 2: Verify All Services Are Running

```bash
# Check container status
docker-compose ps

# Expected output should show 16 containers all with status "Up"
CONTAINER ID   IMAGE                       STATUS
abc123...      apache/kafka:latest         Up 2 minutes
def456...      postgres:15                 Up 2 minutes
ghi789...      redis:7-alpine              Up 2 minutes
...
```

### Step 3: Wait for Services to be Ready (2-3 minutes)

```bash
# Check Kafka broker readiness
docker-compose logs kafka-broker-1 | grep "started"

# Check PostgreSQL readiness
docker-compose logs postgres | grep "ready to accept"

# Check Spark Master UI is accessible
curl http://localhost:9080
# Expected: HTML response with Spark UI

# Check Prometheus is scraping
curl http://localhost:9090/api/v1/query?query=up
# Expected: JSON with "status":"success"
```

### Quick Health Check Script

**Create file:** `scripts/health-check.sh`

```bash
#!/bin/bash

echo "🔍 Checking Kafka microservices health..."
echo ""

# Service endpoints
declare -A SERVICES=(
    ["cart-service"]="http://localhost:8001/docs"
    ["order-service"]="http://localhost:8002/docs"
    ["payment-service"]="http://localhost:8003/docs"
    ["inventory-service"]="http://localhost:8004/docs"
    ["notification-service"]="http://localhost:8005/docs"
)

echo "📋 Microservices Status:"
for service in "${!SERVICES[@]}"; do
    url="${SERVICES[$service]}"
    status=$(curl -s -o /dev/null -w "%{http_code}" $url)
    if [ "$status" = "200" ]; then
        echo "  ✅ $service (HTTP $status)"
    else
        echo "  ❌ $service (HTTP $status)"
    fi
done

echo ""
echo "🔌 Supporting Services Status:"

# Kafka
kafka_status=$(docker-compose ps kafka-broker-1 | grep -i "up")
if [ ! -z "$kafka_status" ]; then
    echo "  ✅ Kafka Cluster"
else
    echo "  ❌ Kafka Cluster"
fi

# PostgreSQL
pg_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5050)
if [ "$pg_status" = "200" ]; then
    echo "  ✅ PostgreSQL (pgAdmin at http://localhost:5050)"
else
    echo "  ❌ PostgreSQL"
fi

# Redis
redis_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:6379 2>/dev/null || echo "failed")
if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
    echo "  ✅ Redis"
else
    echo "  ❌ Redis"
fi

# Spark
spark_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9080)
if [ "$spark_status" = "200" ]; then
    echo "  ✅ Spark Master (UI at http://localhost:9080)"
else
    echo "  ❌ Spark Master"
fi

# Monitoring
prom_status=$(curl -s http://localhost:9090/api/v1/query?query=up | grep -q "status")
if [ "$prom_status" = "0" ]; then
    echo "  ✅ Prometheus (http://localhost:9090)"
else
    echo "  ❌ Prometheus"
fi

grafana_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)
if [ "$grafana_status" = "200" ] || [ "$grafana_status" = "302" ]; then
    echo "  ✅ Grafana (http://localhost:3000)"
else
    echo "  ❌ Grafana"
fi

echo ""
echo "🎯 Quick Links:"
echo "  - Cart Service API:        http://localhost:8001/docs"
echo "  - Order Service API:       http://localhost:8002/docs"
echo "  - Payment Service API:     http://localhost:8003/docs"
echo "  - Inventory Service API:   http://localhost:8004/docs"
echo "  - Notification Service:    http://localhost:8005/docs"
echo "  - Kafka UI:                http://localhost:8080"
echo "  - pgAdmin:                 http://localhost:5050"
echo "  - Spark Master UI:         http://localhost:9080"
echo "  - Prometheus:              http://localhost:9090"
echo "  - Grafana:                 http://localhost:3000"
echo "  - MailHog:                 http://localhost:8025"
```

**Run it:**
```bash
chmod +x scripts/health-check.sh
./scripts/health-check.sh
```

---

## Part 3: Simulating Real User Behavior

### Option A: Use Python Test Script (Recommended)

**Create file:** `scripts/simulate-users.py`

```python
#!/usr/bin/env python3
"""
Simulate real e-commerce user behavior:
- Browse products (view inventory)
- Add items to cart
- Checkout (create order)
- Complete payment
- Trigger notifications
"""

import requests
import json
import time
import random
import logging
from datetime import datetime
from typing import List, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Service base URLs
CART_SERVICE = "http://localhost:8001"
ORDER_SERVICE = "http://localhost:8002"
PAYMENT_SERVICE = "http://localhost:8003"
INVENTORY_SERVICE = "http://localhost:8004"
NOTIFICATION_SERVICE = "http://localhost:8005"

# Sample products (IDs and prices)
PRODUCTS = {
    "PROD001": {"name": "Laptop", "price": 999.99, "quantity": 50},
    "PROD002": {"name": "Mouse", "price": 29.99, "quantity": 200},
    "PROD003": {"name": "Keyboard", "price": 79.99, "quantity": 150},
    "PROD004": {"name": "Monitor", "price": 299.99, "quantity": 30},
    "PROD005": {"name": "USB-C Cable", "price": 19.99, "quantity": 500},
}

class UserSimulator:
    """Simulates a single user journey through the e-commerce platform."""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session = requests.Session()
        self.cart = {}
        self.order_id = None
        
    def log(self, message: str, level: str = "info"):
        """Log with user context."""
        msg = f"[User {self.user_id}] {message}"
        if level == "info":
            logger.info(msg)
        elif level == "error":
            logger.error(msg)
        elif level == "warning":
            logger.warning(msg)
    
    def browse_products(self):
        """Step 1: Browse and view products."""
        self.log("👀 Browsing products...")
        
        try:
            # Call inventory service to view available products
            response = self.session.get(
                f"{INVENTORY_SERVICE}/inventory/products",
                timeout=5
            )
            
            if response.status_code == 200:
                products = response.json()
                self.log(f"✅ Found {len(products)} products")
                return products
            else:
                self.log(f"❌ Failed to fetch products (HTTP {response.status_code})", "error")
                return []
        except Exception as e:
            self.log(f"❌ Error browsing products: {e}", "error")
            return []
    
    def add_to_cart(self, product_id: str, quantity: int = 1):
        """Step 2: Add items to shopping cart."""
        self.log(f"🛒 Adding {quantity}x {product_id} to cart...")
        
        try:
            response = self.session.post(
                f"{CART_SERVICE}/cart/{self.user_id}/items",
                json={
                    "product_id": product_id,
                    "quantity": quantity
                },
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                self.cart[product_id] = quantity
                self.log(f"✅ Added to cart")
                return True
            else:
                self.log(f"❌ Failed to add to cart (HTTP {response.status_code})", "error")
                return False
        except Exception as e:
            self.log(f"❌ Error adding to cart: {e}", "error")
            return False
    
    def view_cart(self):
        """Step 3: View shopping cart."""
        self.log("📋 Viewing cart...")
        
        try:
            response = self.session.get(
                f"{CART_SERVICE}/cart/{self.user_id}",
                timeout=5
            )
            
            if response.status_code == 200:
                cart = response.json()
                total = sum(item.get("price", 0) * item.get("quantity", 0) 
                           for item in cart.get("items", []))
                self.log(f"✅ Cart has {len(cart.get('items', []))} items, total: ${total:.2f}")
                return cart
            else:
                self.log(f"❌ Failed to fetch cart (HTTP {response.status_code})", "error")
                return None
        except Exception as e:
            self.log(f"❌ Error viewing cart: {e}", "error")
            return None
    
    def checkout(self):
        """Step 4: Checkout and create order."""
        self.log("💳 Checking out...")
        
        try:
            # Calculate total
            items = [
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "price": PRODUCTS.get(product_id, {}).get("price", 0)
                }
                for product_id, quantity in self.cart.items()
            ]
            total_amount = sum(
                item["price"] * item["quantity"] for item in items
            )
            
            response = self.session.post(
                f"{ORDER_SERVICE}/orders",
                json={
                    "user_id": self.user_id,
                    "items": items,
                    "total_amount": total_amount,
                    "shipping_address": f"{self.user_id}@example.com",
                    "email": f"{self.user_id}@example.com"
                },
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                order = response.json()
                self.order_id = order.get("order_id", "unknown")
                self.log(f"✅ Order created: {self.order_id}")
                return order
            else:
                self.log(f"❌ Checkout failed (HTTP {response.status_code})", "error")
                return None
        except Exception as e:
            self.log(f"❌ Error during checkout: {e}", "error")
            return None
    
    def complete_payment(self):
        """Step 5: Complete payment."""
        if not self.order_id:
            self.log("❌ No order to pay for", "error")
            return False
        
        self.log("💰 Processing payment...")
        
        try:
            response = self.session.post(
                f"{PAYMENT_SERVICE}/payments",
                json={
                    "order_id": self.order_id,
                    "amount": random.uniform(50, 2000),
                    "currency": "USD",
                    "payment_method": "credit_card"
                },
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                payment = response.json()
                self.log(f"✅ Payment successful: {payment.get('transaction_id', 'unknown')}")
                return True
            else:
                self.log(f"❌ Payment failed (HTTP {response.status_code})", "error")
                return False
        except Exception as e:
            self.log(f"❌ Error processing payment: {e}", "error")
            return False
    
    def run_complete_journey(self):
        """Execute complete user journey: browse → add → checkout → pay."""
        self.log("🚀 Starting user journey...")
        
        # Step 1: Browse products
        self.browse_products()
        time.sleep(0.5)
        
        # Step 2: Add random items to cart (2-5 items)
        num_items = random.randint(2, 5)
        for _ in range(num_items):
            product_id = random.choice(list(PRODUCTS.keys()))
            quantity = random.randint(1, 3)
            self.add_to_cart(product_id, quantity)
            time.sleep(0.3)
        
        # Step 3: View cart
        self.view_cart()
        time.sleep(0.5)
        
        # Step 4: Checkout
        order = self.checkout()
        if not order:
            self.log("⚠️  Checkout failed, stopping journey", "warning")
            return False
        time.sleep(1)
        
        # Step 5: Complete payment
        if self.complete_payment():
            self.log("✅ User journey complete!")
            return True
        else:
            self.log("⚠️  Payment failed, order may be incomplete", "warning")
            return False

class LoadSimulator:
    """Simulate multiple concurrent users."""
    
    def __init__(self, num_users: int = 5):
        self.num_users = num_users
        self.users = [UserSimulator(f"user_{i:03d}") for i in range(num_users)]
    
    def simulate_wave(self):
        """Simulate a wave of users (all concurrently for ~5 seconds)."""
        logger.info(f"🌊 Simulating {self.num_users} concurrent users...")
        
        for i, user in enumerate(self.users):
            # Start each user with slight delay
            user.run_complete_journey()
            time.sleep(0.2)  # 200ms delay between user starts
        
        logger.info(f"✅ Wave complete")
    
    def simulate_continuous(self, duration_seconds: int = 300, wave_interval: int = 30):
        """Simulate continuous user traffic for specified duration."""
        logger.info(f"🔄 Starting continuous simulation for {duration_seconds}s...")
        logger.info(f"   New wave every {wave_interval}s")
        
        start_time = time.time()
        wave_count = 0
        
        while time.time() - start_time < duration_seconds:
            wave_count += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"Wave #{wave_count} at {datetime.now().strftime('%H:%M:%S')}")
            logger.info(f"{'='*60}")
            
            self.simulate_wave()
            
            # Wait before next wave
            remaining = duration_seconds - (time.time() - start_time)
            if remaining > wave_interval:
                logger.info(f"⏳ Waiting {wave_interval}s until next wave...\n")
                time.sleep(wave_interval)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✅ Simulation complete! {wave_count} waves executed")
        logger.info(f"{'='*60}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Simulate realistic e-commerce user behavior"
    )
    parser.add_argument(
        "--users",
        type=int,
        default=5,
        help="Number of concurrent users per wave (default: 5)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=300,
        help="Total simulation duration in seconds (default: 300 = 5 minutes)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Interval between user waves in seconds (default: 30)"
    )
    parser.add_argument(
        "--mode",
        choices=["single", "wave", "continuous"],
        default="wave",
        help="Simulation mode (default: wave)"
    )
    
    args = parser.parse_args()
    
    logger.info("🎬 E-Commerce User Simulator")
    logger.info(f"   Mode: {args.mode}")
    logger.info(f"   Users: {args.users}")
    if args.mode == "continuous":
        logger.info(f"   Duration: {args.duration}s")
        logger.info(f"   Wave interval: {args.interval}s")
    logger.info("")
    
    simulator = LoadSimulator(num_users=args.users)
    
    if args.mode == "single":
        # Single user journey
        user = UserSimulator("test_user_001")
        user.run_complete_journey()
    elif args.mode == "wave":
        # Single wave
        simulator.simulate_wave()
    elif args.mode == "continuous":
        # Continuous load
        simulator.simulate_continuous(
            duration_seconds=args.duration,
            wave_interval=args.interval
        )

if __name__ == "__main__":
    main()
```

**Make executable and run:**
```bash
chmod +x scripts/simulate-users.py

# Mode 1: Single user journey (test connectivity)
python scripts/simulate-users.py --mode single

# Mode 2: Single wave of 5 users
python scripts/simulate-users.py --mode wave --users 5

# Mode 3: Continuous simulation (5 users, every 30s, for 5 minutes)
python scripts/simulate-users.py --mode continuous --users 5 --duration 300 --interval 30

# Mode 3 variant: Heavy load (20 users every 15s for 10 minutes)
python scripts/simulate-users.py --mode continuous --users 20 --duration 600 --interval 15
```

### Option B: Use curl Commands (Manual)

If you prefer to manually test:

```bash
# 1. View available inventory
curl http://localhost:8004/inventory/products

# 2. Add item to cart
curl -X POST http://localhost:8001/cart/user_001/items \
  -H "Content-Type: application/json" \
  -d '{"product_id": "PROD001", "quantity": 2}'

# 3. View cart
curl http://localhost:8001/cart/user_001

# 4. Create order
curl -X POST http://localhost:8002/orders \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_001",
    "items": [{"product_id": "PROD001", "quantity": 2, "price": 999.99}],
    "total_amount": 1999.98,
    "shipping_address": "123 Main St",
    "email": "user@example.com"
  }'

# 5. Process payment (replace ORDER_ID with actual order ID)
curl -X POST http://localhost:8003/payments \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORDER_ID",
    "amount": 1999.98,
    "currency": "USD",
    "payment_method": "credit_card"
  }'
```

---

## Part 4: Running Spark Analytics Jobs

### Option A: Spark Jobs Auto-Run in docker-compose

If you added Spark job services to docker-compose:

```yaml
spark-revenue-job:
  image: bitnami/spark:3.5.0
  depends_on:
    - spark-master
  command: spark-submit --master spark://spark-master:7077 ...
  restart: unless-stopped
```

**They start automatically!**

```bash
# Check job status
docker-compose logs spark-revenue-job | tail -50

# All jobs should show:
# "Starting Spark job..."
# "Connected to Kafka..."
# "Writing to PostgreSQL..."
```

### Option B: Manually Trigger Spark Jobs

If jobs aren't auto-running, submit them manually:

```bash
# 1. Submit revenue streaming job
docker-compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 \
  /opt/spark-apps/analytics/jobs/revenue_streaming.py

# 2. Submit fraud detection job
docker-compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 \
  /opt/spark-apps/analytics/jobs/fraud_detection.py

# 3. Submit inventory velocity job
docker-compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 \
  /opt/spark-apps/analytics/jobs/inventory_velocity.py

# 4. Submit cart abandonment job
docker-compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 \
  /opt/spark-apps/analytics/jobs/cart_abandonment.py

# 5. Submit operational metrics job
docker-compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 \
  /opt/spark-apps/analytics/jobs/operational_metrics.py
```

### Monitor Spark Jobs

**Spark Master UI:** http://localhost:9080
- Shows running applications
- Click on app to see task progress
- Check executor logs for errors

**Check job logs:**
```bash
# Revenue job logs
docker-compose logs -f spark-revenue-job

# Fraud job logs
docker-compose logs -f spark-fraud-job

# All Spark logs
docker-compose logs -f spark-master spark-worker-1 spark-worker-2
```

**Verify output tables exist:**
```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U postgres -d kafka_ecom -c "
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
"

# Expected tables:
# revenue_metrics
# fraud_alerts
# inventory_velocity
# cart_abandonment
# operational_metrics
```

---

## Part 5: Accessing Monitoring Dashboards

### Step 1: Login to Grafana

**URL:** http://localhost:3000

**Credentials:**
- Username: `admin`
- Password: `admin`

### Step 2: Add Prometheus Data Source

1. Go to **Configuration** → **Data Sources**
2. Click **Add data source**
3. Select **Prometheus**
4. URL: `http://prometheus:9090`
5. Click **Save & test**

Expected: "✅ Data source is working"

### Step 3: Import Dashboards

**Option A: Import via JSON**

1. Go to **Dashboards** → **Import**
2. Upload `monitoring/dashboards/services-overview.json`
3. Select **Prometheus** as data source
4. Click **Import**
5. Repeat for `spark-analytics.json`

**Option B: Create Dashboards Manually**

1. Create **New Dashboard**
2. Add panels with these queries:

#### Services Dashboard Panels

**Panel 1: Payment Service - Requests/sec**
```
Query: rate(service_requests_total{service="payment-service"}[1m])
Type: Graph
Legend: Payment requests/sec
```

**Panel 2: Order Service - Saga Success Rate**
```
Query: rate(saga_orchestration_steps_total{status="success"}[1m]) / rate(saga_orchestration_steps_total[1m]) * 100
Type: Gauge
Unit: percent
Thresholds: 0-90 (red), 90-99 (yellow), 99-100 (green)
```

**Panel 3: Payment Latency (p99)**
```
Query: histogram_quantile(0.99, rate(payment_request_duration_seconds_bucket[5m]))
Type: Graph
Unit: seconds
Legend: Payment p99 latency
```

**Panel 4: Error Rate**
```
Query: rate(service_errors_total[1m])
Type: Graph
Legend: {{error_type}}
```

**Panel 5: Idempotency Cache Hit Rate**
```
Query: rate(idempotency_cache_hits_total[5m]) / (rate(idempotency_cache_hits_total[5m]) + rate(idempotency_cache_misses_total[5m])) * 100
Type: Gauge
Unit: percent
Thresholds: 0-80 (red), 80-95 (yellow), 95-100 (green)
```

#### Spark Analytics Dashboard Panels

**Panel 1: 24-Hour Revenue**
```
Query: spark_revenue_total_24h
Type: Stat (gauge)
Unit: currencyUSD
Sparkline: Yes
```

**Panel 2: Revenue Trend (7 days)**
```
Query: spark_revenue_total_24h
Type: Graph
Range: Last 7 days
Legend: Revenue by day
```

**Panel 3: Fraud Alerts by Severity**
```
Query: spark_fraud_alerts_total
Type: Bar chart
Group by: severity
```

**Panel 4: Top 10 Products**
```
Query: spark_top_product_units_sold
Type: Bar chart
Sort: Descending
Legend: {{product_id}} ({{rank}})
Limit: 10
```

**Panel 5: Cart Abandonment Rate**
```
Query: spark_cart_abandonment_rate
Type: Gauge
Unit: percent
Thresholds: 0-30 (green), 30-50 (yellow), 50-100 (red)
```

### Step 4: View Real-Time Metrics

Once you have dashboards set up:

1. Start user simulator (Part 3)
2. Watch metrics appear in real-time
3. Grafana refreshes every 30 seconds

**Expected metrics appearing:**
- Request rates going up
- Latencies increasing during load
- Error rates spike (if any fail)
- Revenue total increasing
- Fraud alerts appearing
- Inventory velocity updating

---

## Part 6: Complete End-to-End Example

### Full Startup Procedure (10 minutes)

**Terminal 1: Start everything**
```bash
cd /Users/tong/KafkaProjects/kafka-microservices-spark-ecom
docker-compose up -d
```

**Terminal 2: Wait for services to be ready (2-3 min)**
```bash
./scripts/health-check.sh

# Keep checking until all services show ✅
```

**Terminal 3: Submit Spark jobs**
```bash
# Start revenue job
docker-compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 \
  /opt/spark-apps/analytics/jobs/revenue_streaming.py &

# Start fraud job
docker-compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 \
  /opt/spark-apps/analytics/jobs/fraud_detection.py &

# Start inventory job
docker-compose exec spark-master spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 \
  /opt/spark-apps/analytics/jobs/inventory_velocity.py &
```

**Terminal 4: Simulate users**
```bash
python scripts/simulate-users.py --mode continuous --users 10 --duration 600 --interval 20
```

**Browser Tab 1: Open Grafana**
```
http://localhost:3000
Login: admin / admin
Select: Services Overview Dashboard
```

**Browser Tab 2: Open Spark UI**
```
http://localhost:9080
Watch jobs run in real-time
```

**Browser Tab 3: Open Kafka UI**
```
http://localhost:8080
Watch events flow through topics
```

**Browser Tab 4: Open Prometheus**
```
http://localhost:9090
Query: rate(service_requests_total[1m])
```

---

## Part 7: Monitoring & Troubleshooting

### Check Kafka Topics

```bash
# List all topics
docker-compose exec kafka-broker-1 kafka-topics.sh --list --bootstrap-server localhost:9092

# See topic details
docker-compose exec kafka-broker-1 kafka-topics.sh --describe --topic order.created --bootstrap-server localhost:9092

# Consume messages in real-time
docker-compose exec kafka-broker-1 kafka-console-consumer.sh \
  --topic payment.processed \
  --bootstrap-server localhost:9092 \
  --from-beginning \
  --max-messages 10
```

### Check Database State

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U postgres -d kafka_ecom

# View orders
SELECT * FROM orders LIMIT 5;

# View payments
SELECT * FROM payments LIMIT 5;

# View processed events (deduplication)
SELECT COUNT(*) FROM processed_events;

# View revenue metrics
SELECT * FROM revenue_metrics ORDER BY window_start DESC LIMIT 5;

# View fraud alerts
SELECT * FROM fraud_alerts ORDER BY timestamp DESC LIMIT 5;

# Exit
\q
```

### View Service Logs

```bash
# Order service logs
docker-compose logs -f order-service | grep -i "error\|warn\|created"

# Payment service logs
docker-compose logs -f payment-service | grep -i "error\|processing"

# Spark logs
docker-compose logs -f spark-master | grep -i "application\|running"

# All logs
docker-compose logs -f --tail=50
```

### Check Metrics Directly

```bash
# Service metrics endpoint
curl http://localhost:8003/metrics | grep "payment_"

# Prometheus scrape status
curl http://localhost:9090/api/v1/targets

# Check Spark exporter metrics
curl http://localhost:9090/metrics | grep "spark_"
```

---

## Part 8: Cleanup & Teardown

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove only containers (keep data)
docker-compose stop

# Restart stopped containers
docker-compose start

# View resource usage
docker stats

# Clean up unused Docker resources
docker system prune -a
```

---

## Part 9: Common Issues & Solutions

### Issue 1: Services not starting

**Symptom:** `docker-compose up -d` fails or services show "Exited"

**Solution:**
```bash
# Check detailed error
docker-compose logs service-name

# Restart services
docker-compose restart

# Rebuild images
docker-compose down
docker-compose up -d --build
```

### Issue 2: Kafka topics not created

**Symptom:** Kafka UI shows no topics

**Solution:**
```bash
# Trigger topic auto-creation by publishing
docker-compose exec kafka-broker-1 kafka-topics.sh \
  --create \
  --topic order.created \
  --bootstrap-server localhost:9092 \
  --replication-factor 3 \
  --partitions 3 \
  --if-not-exists
```

### Issue 3: Spark jobs not producing data

**Symptom:** Spark UI shows running jobs but no output in PostgreSQL

**Solution:**
```bash
# Check Spark logs
docker-compose logs spark-master | tail -100

# Check Kafka connectivity
docker-compose exec spark-worker-1 kafka-console-consumer.sh \
  --topic payment.processed \
  --bootstrap-server kafka-broker-1:9092 \
  --max-messages 1

# Check PostgreSQL connectivity
docker-compose exec spark-master psql -h postgres -U postgres -d kafka_ecom -c "SELECT 1"
```

### Issue 4: Grafana dashboards show no data

**Symptom:** "No data" in all panels

**Solution:**
```bash
# Verify Prometheus is scraping
curl http://localhost:9090/api/v1/targets

# Check data exists in Prometheus
curl 'http://localhost:9090/api/v1/query?query=up'

# Rebuild dashboards with correct queries
```

### Issue 5: High memory/CPU usage

**Symptom:** Docker containers consuming too much resources

**Solution:**
```bash
# Check resource usage
docker stats

# Stop Spark workers temporarily
docker-compose stop spark-worker-2

# Reduce concurrent users in simulator
python scripts/simulate-users.py --users 3 --duration 300

# Clear Prometheus data
docker-compose exec prometheus rm -rf /prometheus/*
```

---

## Part 10: Performance Expectations

### Baseline Metrics (Normal Operations)

| Metric | Value | Status |
|--------|-------|--------|
| Payment requests/sec | 10-20 | ✅ Normal |
| Order latency (p99) | 500-1000ms | ✅ Good |
| Kafka lag | < 5s | ✅ Healthy |
| Error rate | < 1% | ✅ Acceptable |
| Idempotency hit rate | > 95% | ✅ Excellent |
| Spark job duration | 30-60s | ✅ Normal |
| Saga success rate | > 99% | ✅ Reliable |

### High Load Metrics (Continuous Simulation)

| Metric | Value | Status |
|--------|-------|--------|
| Payment requests/sec | 50-100 | ⚠️ Peak |
| Order latency (p99) | 1-3s | ⚠️ Elevated |
| Kafka lag | 5-30s | ⚠️ Slight backlog |
| Error rate | 0.1-2% | ⚠️ Watch |
| Idempotency hit rate | > 90% | ✅ Still good |
| Memory usage | 6-8GB | ⚠️ High |

### When to Scale

```
If any of these occur consistently:
- Payment latency p99 > 5 seconds
- Error rate > 5%
- Kafka consumer lag > 60 seconds
- Out of memory errors
- Spark job timeout/failure

Solution:
1. Increase docker memory limits
2. Add more Spark workers
3. Increase Kafka partitions
4. Add database connection pool size
5. Scale microservices to multiple replicas
```

---

## Quick Start Cheat Sheet

```bash
# 1. Start everything
docker-compose up -d && sleep 30

# 2. Verify health
./scripts/health-check.sh

# 3. Start Spark jobs
docker-compose exec spark-master spark-submit --master spark://spark-master:7077 --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.7.0 /opt/spark-apps/analytics/jobs/revenue_streaming.py &

# 4. Simulate users
python scripts/simulate-users.py --mode continuous --users 5 --duration 300

# 5. Open dashboards
# Grafana:    http://localhost:3000
# Spark:      http://localhost:9080
# Kafka:      http://localhost:8080
# Prometheus: http://localhost:9090

# 6. Stop everything
docker-compose down
```

---

## Next Steps

1. **Start the system** using Part 2
2. **Simulate users** using Part 3
3. **Monitor dashboards** using Part 5
4. **Troubleshoot** using Part 9 if needed
5. **Iterate** on system design based on metrics

---

## Additional Resources

- **Kafka Topics:** http://localhost:8080
- **pgAdmin:** http://localhost:5050 (postgres / postgres)
- **MailHog (Email):** http://localhost:8025
- **Spark Master:** http://localhost:9080
- **Prometheus Queries:** http://localhost:9090/graph
- **Grafana:** http://localhost:3000

Good luck! 🚀
