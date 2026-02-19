#!/bin/bash

# test-complete-workflow.sh - UPDATED FOR MULTIPLE ORDERS
# 
# CHANGES MADE:
# ✅ Now creates multiple orders (default: 3, configurable)
# ✅ Each order has randomized products and quantities
# ✅ Better tracking with arrays (USER_IDS, CART_IDS, ORDER_IDS)
# ✅ Improved output showing all orders created
# ✅ All Spark jobs continue running to process the orders

# USAGE:

# Create 3 orders (default):
#   ./test-complete-workflow.sh

# Create 5 orders:
#   ./test-complete-workflow.sh 5

# Create 10 orders:
#   ./test-complete-workflow.sh 10

# WHAT IT DOES:

# For each order:
# 1. Creates a unique user ID
# 2. Randomly selects 1-3 products from 10 product types
# 3. Each product has random quantity (1-5 items)
# 4. Each order goes through complete workflow:
#    - Cart → Checkout → Order → Payment → Inventory → Notification
# 5. Spark jobs process all orders and populate analytics

# PRODUCTS AVAILABLE:
# - LAPTOP ($899.99)
# - SMARTPHONE ($599.99)
# - HEADPHONES ($199.99)
# - SMARTWATCH ($299.99)
# - TABLET ($449.99)
# - KEYBOARD ($79.99)
# - MOUSE ($49.99)
# - MONITOR ($349.99)
# - SPEAKER ($129.99)
# - CAMERA ($799.99)

# KEY FEATURES:

# ✓ Multiple concurrent orders
# ✓ Random product selection per order
# ✓ Randomized quantities (1-5 items per product)
# ✓ Real event flow through all microservices
# ✓ Automatic Spark job startup
# ✓ Comprehensive test reporting
# ✓ Analytics population in PostgreSQL
# ✓ Full Kafka event tracing

# MONITORING:

# While script runs, check:
# 1. Spark Master UI: http://localhost:9080
# 2. Spark Driver UI: http://localhost:4040
# 3. Kafka UI: http://localhost:8080
# 4. pgAdmin: http://localhost:5050

# After completion, query results:
# psql postgresql://postgres:postgres@localhost:5432/kafka_ecom
# SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;
# SELECT * FROM revenue_metrics ORDER BY window_start DESC LIMIT 10;
# SELECT * FROM fraud_alerts ORDER BY created_at DESC LIMIT 10;

# EXAMPLE OUTPUT:
# 
# ═══ Order #1 ═══
# ▶ Order #1 - Adding 2 items to cart (User: test-user-1771058436-1)...
# ✓ Added SPEAKER (Qty: 4, Price: $129.99)
# ✓ Added MOUSE (Qty: 2, Price: $49.99)
# ✓ Cart #1 Total: $619.94
# 
# ═══ Order #2 ═══
# ▶ Order #2 - Adding 2 items to cart (User: test-user-1771058438-2)...
# ✓ Added SMARTWATCH (Qty: 3, Price: $299.99)
# ✓ Added KEYBOARD (Qty: 1, Price: $79.99)
# ✓ Cart #2 Total: $899.96
# 
# ... continues for all orders ...

# TROUBLESHOOTING:

# If script fails:
# 1. Check all services are running: docker-compose up -d
# 2. Verify Spark is ready: docker logs spark-master
# 3. Check PostgreSQL: docker logs postgres
# 4. View service errors: docker logs cart-service

# Restart Spark jobs:
#   pkill -f "spark-submit.*jobs"
#   docker exec spark-worker-1 pkill -f python
#   ./test-complete-workflow.sh 3

# Clear data and start fresh:
#   ./clean-database.sh
#   ./clean-kafka.sh
#   ./test-complete-workflow.sh 5

