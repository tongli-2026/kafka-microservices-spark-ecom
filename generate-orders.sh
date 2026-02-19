#!/bin/bash

###############################################################################
# Order Generation Script for E-Commerce Analytics Demo
#
# Purpose:
#   Generates multiple e-commerce orders to demonstrate real-time analytics
#   with Kafka and Spark Structured Streaming.
#
# What This Script Does:
#   1. Checks if Spark revenue_streaming job is running (starts it if not)
#   2. Prompts for number of orders to generate
#   3. Creates orders one by one with 3-second delays
#   4. Tracks success/failure rates (80% payment success rate)
#   5. Displays final revenue metrics from PostgreSQL
#
# Data Flow:
#   Script → Cart Service → Order Service → Payment Service → Kafka Topics
#   → Spark Streaming → PostgreSQL Analytics
#
# Usage:
#   ./generate-orders.sh
#   
#   Then follow the prompts:
#   - Enter number of orders (default: 5)
#   - Watch as orders are created and processed
#
# Monitoring:
#   - Open http://localhost:4040 to see Spark streaming dashboard
#   - Run ./watch-revenue.sh in another terminal for live metrics
#
###############################################################################

# Script to generate multiple orders and trigger the complete e-commerce workflow
# This will create orders that flow through: Cart → Order → Payment → Analytics

# Exit immediately if any command fails
set -e

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║         Generating Orders for Real-Time Analytics               ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Check if Spark job is running
# The revenue_streaming job must be active to process payment events
SPARK_JOB=$(docker exec spark-worker-1 ps aux | grep revenue_streaming | grep -v grep | wc -l)

if [ "$SPARK_JOB" -eq 0 ]; then
    # Spark job is not running - offer to start it
    echo "⚠️  Spark revenue_streaming job is not running!"
    echo ""
    read -p "Do you want to start it now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # User chose to start the Spark job
        echo "🚀 Starting Spark job..."
        ./run-spark-job.sh revenue_streaming > /tmp/spark-job.log 2>&1 &
        echo "✅ Spark job started in background"
        echo "⏳ Waiting 15 seconds for job to initialize..."
        sleep 15
    else
        # User declined - exit script
        echo "❌ Exiting. Please start the Spark job first with: ./run-spark-job.sh revenue_streaming"
        exit 1
    fi
else
    echo "✅ Spark revenue_streaming job is already running"
fi

echo ""
echo "📊 Spark Driver UI (Real-time Dashboard):"
echo "   👉 http://localhost:4040"
echo ""
echo "   Navigate to the 'Structured Streaming' tab to see:"
echo "   • Input Rate (events/second from Kafka)"
echo "   • Process Rate (records/second being processed)"
echo "   • Batch Duration (time to process each micro-batch)"
echo "   • Number of rows processed"
echo ""

# Ask how many orders to generate
# Default is 5 if user just presses Enter
read -p "How many orders do you want to generate? (default: 5) " NUM_ORDERS
NUM_ORDERS=${NUM_ORDERS:-5}  # Use 5 if NUM_ORDERS is empty

echo ""
echo "🛒 Generating $NUM_ORDERS orders..."
echo "   Each order will:"
echo "   1. Create a cart with random products"
echo "   2. Initiate checkout (cart.checkout_initiated event)"
echo "   3. Create an order (order.created event)"
echo "   4. Process payment (payment.processed event - 80% success rate)"
echo "   5. Confirm or cancel order (order.confirmed/cancelled event)"
echo "   6. Trigger Spark analytics to aggregate revenue"
echo ""

sleep 2

# Initialize counters to track order outcomes
SUCCESS_COUNT=0  # Number of successfully paid orders
FAILED_COUNT=0   # Number of cancelled orders (payment failed)

# Main order generation loop
# Creates orders sequentially with delays to demonstrate real-time streaming
for i in $(seq 1 $NUM_ORDERS); do
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Creating Order $i of $NUM_ORDERS..."
    
    # Run the test workflow script which creates a complete order
    # Capture all output (stdout and stderr) for parsing
    OUTPUT=$(./test-workflow.sh 2>&1)
    
    # Check if order was successfully created by looking for the order ID
    if echo "$OUTPUT" | grep -q "Found Order ID:"; then
        # Extract the order ID from the output
        ORDER_ID=$(echo "$OUTPUT" | grep "Found Order ID:" | awk '{print $4}')
        
        # Wait for async payment processing to complete
        # The payment service processes payments asynchronously
        sleep 2
        
        # Query PostgreSQL directly to get the final order status
        # Status will be either "PAID" (success) or "CANCELLED" (payment failed)
        STATUS=$(docker exec postgres psql -U postgres -d kafka_ecom -t -c "SELECT status FROM orders WHERE order_id='$ORDER_ID';" | tr -d '[:space:]')
        
        echo "   Order ID: $ORDER_ID"
        echo "   Status: $STATUS"
        
        # Update counters based on final status
        if [ "$STATUS" = "PAID" ]; then
            ((SUCCESS_COUNT++))  # Increment success counter
            echo "   ✅ Payment successful - Revenue will be added to analytics"
        elif [ "$STATUS" = "CANCELLED" ]; then
            ((FAILED_COUNT++))  # Increment failure counter
            echo "   ❌ Payment failed - Order cancelled"
        else
            # Unexpected status (shouldn't normally happen)
            echo "   ⏳ Status: $STATUS (processing...)"
        fi
    else
        # Order creation failed - couldn't find order ID in output
        echo "   ⚠️  Order creation had an issue"
        ((FAILED_COUNT++))
    fi
    
    # Add delay between orders to avoid overwhelming the system
    # This also makes it easier to see real-time streaming in action
    if [ $i -lt $NUM_ORDERS ]; then
        echo ""
        echo "⏳ Waiting 3 seconds before next order..."
        sleep 3
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Order Generation Complete!"
echo ""
echo "📈 Results:"
echo "   • Total Orders: $NUM_ORDERS"
echo "   • Successful Payments: $SUCCESS_COUNT"
echo "   • Failed Payments: $FAILED_COUNT"
echo ""
echo "⏳ Waiting 10 seconds for Spark to process events..."
sleep 10

echo ""
echo "📊 Current Revenue Metrics:"
docker exec -it postgres psql -U postgres -d kafka_ecom -c \
  "SELECT 
    window_start,
    window_end, 
    total_revenue, 
    order_count, 
    avg_order_value 
  FROM revenue_metrics 
  ORDER BY window_start DESC 
  LIMIT 10;"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                   Next Steps                                     ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Monitor Real-Time Analytics:"
echo "   • Spark Driver UI: http://localhost:4040"
echo "     → Click 'Structured Streaming' tab"
echo "     → See real-time processing statistics"
echo ""
echo "🔍 View Other Dashboards:"
echo "   • Kafka UI: http://localhost:8080"
echo "   • Spark Master: http://localhost:9080"
echo "   • Spark Worker 1: http://localhost:8081"
echo "   • Spark Worker 2: http://localhost:8082"
echo ""
echo "💡 Generate More Orders:"
echo "   ./generate-orders.sh"
echo ""
echo "💡 View Revenue Data:"
echo "   docker exec -it postgres psql -U postgres -d kafka_ecom \\"
echo "     -c \"SELECT * FROM revenue_metrics ORDER BY window_start DESC LIMIT 10;\""
echo ""
echo "💡 Stop Spark Job:"
echo "   docker exec spark-worker-1 pkill -f revenue_streaming"
echo ""
