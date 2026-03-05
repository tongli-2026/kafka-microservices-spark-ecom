#!/bin/bash

################################################################################
# Direct Kafka CLI Commands for Idempotency Testing
# Copy-paste these commands directly into your terminal
################################################################################

# ==============================================================================
# SETUP
# ==============================================================================

# Verify Kafka broker is running
docker exec kafka-broker-1 kafka-topics.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --list

# Expected output: List of topics (order-created, payment-processed, etc.)


# ==============================================================================
# LIST TOPICS
# ==============================================================================

# View all Kafka topics
docker exec kafka-broker-1 kafka-topics.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --list

# Example output:
# __consumer_offsets
# order-created
# payment-processed
# inventory-reserved


# ==============================================================================
# MONITOR TOPICS IN REAL-TIME
# ==============================================================================

# Watch payment-processed topic (shows new messages as they arrive)
docker exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --from-beginning \
  --property print.timestamp=true

# Watch order-created topic
docker exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic order-created \
  --from-beginning \
  --property print.timestamp=true

# Watch with more details (offset, partition, key)
docker exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --from-beginning \
  --property print.timestamp=true \
  --property print.offset=true \
  --property print.partition=true \
  --property print.key=true


# ==============================================================================
# PUBLISH DUPLICATE PAYMENT EVENT
# ==============================================================================

# Create a payment event
PAYMENT_EVENT='{
  "order_id": "test-order-'$(date +%s)'",
  "amount": 99.99,
  "currency": "USD",
  "status": "PAID",
  "transaction_id": "txn-'$(date +%s%N)'",
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "idempotency_key": "idem-order-'$(date +%s)'"
}'

# Publish first time
echo "$PAYMENT_EVENT" | docker exec -i kafka-broker-1 \
  kafka-console-producer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed

# Publish SAME event again (duplicate)
echo "$PAYMENT_EVENT" | docker exec -i kafka-broker-1 \
  kafka-console-producer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed

# Result: Kafka now has 2 identical messages
# Question: Did system process both or deduplicate?


# ==============================================================================
# PUBLISH DUPLICATE ORDER EVENT
# ==============================================================================

# Create an order event
ORDER_EVENT='{
  "order_id": "order-'$(date +%s%N | cut -c1-13)'",
  "user_id": "user-test-'$(date +%s)'",
  "total_amount": 99.99,
  "currency": "USD",
  "status": "PENDING",
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "idempotency_key": "idem-order-'$(date +%s)'"
}'

# Publish first time
echo "$ORDER_EVENT" | docker exec -i kafka-broker-1 \
  kafka-console-producer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic order-created

# Publish SAME event again (duplicate)
echo "$ORDER_EVENT" | docker exec -i kafka-broker-1 \
  kafka-console-producer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic order-created


# ==============================================================================
# VIEW MESSAGE COUNT IN TOPIC
# ==============================================================================

# Count total messages in payment-processed topic
docker exec kafka-broker-1 kafka-run-class.sh \
  kafka.tools.GetOffsetShell \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed

# Output format:
# payment-processed:0:100  (partition 0 has 100 messages)
# payment-processed:1:95   (partition 1 has 95 messages)


# ==============================================================================
# VIEW LAST N MESSAGES FROM TOPIC
# ==============================================================================

# View last 5 messages from payment-processed
docker exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --from-beginning \
  --max-messages 5

# View last 10 messages
docker exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --from-beginning \
  --max-messages 10


# ==============================================================================
# CHECK CONSUMER GROUP LAG
# ==============================================================================

# View consumer group status
docker exec kafka-broker-1 kafka-consumer-groups.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --group order-service-group \
  --describe

# Output:
# TOPIC          PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
# order-created  0          42              42              0     ← LAG=0 (all consumed)
# payment-proc   0          50              52              2     ← LAG=2 (2 unprocessed)


# ==============================================================================
# VIEW TOPIC METADATA
# ==============================================================================

# Get detailed topic info
docker exec kafka-broker-1 kafka-topics.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --describe

# Output shows:
# - Partitions
# - Replication factor
# - Leader broker
# - ISR (In-Sync Replicas)


# ==============================================================================
# RESET CONSUMER GROUP OFFSET
# ==============================================================================

# Reset to beginning (replay all messages)
docker exec kafka-broker-1 kafka-consumer-groups.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --group order-service-group \
  --topic payment-processed \
  --reset-offsets \
  --to-earliest \
  --execute

# Reset to latest (skip all unprocessed)
docker exec kafka-broker-1 kafka-consumer-groups.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --group order-service-group \
  --topic payment-processed \
  --reset-offsets \
  --to-latest \
  --execute


# ==============================================================================
# PRACTICAL TEST WORKFLOW
# ==============================================================================

# Terminal 1: Monitor payment topic (watch for duplicates)
docker exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --from-beginning \
  --property print.timestamp=true

# Terminal 2: Run the test sequence below

# 1. Create unique order ID
ORDER_ID="test-order-$(date +%s)"
echo "Testing with ORDER_ID: $ORDER_ID"

# 2. Create payment event
PAYMENT_EVENT='{
  "order_id": "'$ORDER_ID'",
  "amount": 99.99,
  "status": "PAID",
  "transaction_id": "txn-'$(date +%s%N)'",
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "idempotency_key": "idem-'$ORDER_ID'"
}'

# 3. Publish first event
echo "Publishing first event..."
echo "$PAYMENT_EVENT" | docker exec -i kafka-broker-1 \
  kafka-console-producer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed
sleep 2

# 4. Publish DUPLICATE event
echo "Publishing duplicate event..."
echo "$PAYMENT_EVENT" | docker exec -i kafka-broker-1 \
  kafka-console-producer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed
sleep 2

# 5. Check: How many times did it appear in Terminal 1?
# If appears 2 times → Kafka received both (expected)
# If appears 1 time → Someone deduplicated (unexpected at Kafka level)

# 6. Check Order Service API
echo "Checking order status..."
curl -s "http://localhost:8002/orders/$ORDER_ID" | jq '.payments | length'

# Result:
# 1 = System deduplicated (idempotent) ✓
# 2 = System processed both (NOT idempotent) ✗
# 0 = Order not found yet


# ==============================================================================
# INSPECT MESSAGE CONTENT
# ==============================================================================

# View message with full details
docker exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --from-beginning \
  --max-messages 1 \
  --formatter kafka.tools.DefaultMessageFormatter

# View with JSON formatting
docker exec kafka-broker-1 kafka-console-consumer.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --from-beginning \
  --max-messages 1 | jq .


# ==============================================================================
# PERFORMANCE METRICS
# ==============================================================================

# Check Kafka broker metrics
docker exec kafka-broker-1 kafka-consumer-perf-test.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --messages 100 \
  --threads 1

# Shows:
# - Messages per second
# - Bytes per second
# - Average latency


# ==============================================================================
# CLEANUP & RESET
# ==============================================================================

# Delete all messages from topic (careful!)
docker exec kafka-broker-1 kafka-topics.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --topic payment-processed \
  --delete

# Recreate topic
docker exec kafka-broker-1 kafka-topics.sh \
  --bootstrap-server kafka-broker-1:9092 \
  --create \
  --topic payment-processed \
  --partitions 3 \
  --replication-factor 3


# ==============================================================================
# USEFUL ALIASES (Add to ~/.zshrc or ~/.bashrc)
# ==============================================================================

# alias kafka-list-topics='docker exec kafka-broker-1 kafka-topics.sh --bootstrap-server kafka-broker-1:9092 --list'
# 
# alias kafka-monitor-payments='docker exec kafka-broker-1 kafka-console-consumer.sh --bootstrap-server kafka-broker-1:9092 --topic payment-processed --from-beginning --property print.timestamp=true'
# 
# alias kafka-monitor-orders='docker exec kafka-broker-1 kafka-console-consumer.sh --bootstrap-server kafka-broker-1:9092 --topic order-created --from-beginning --property print.timestamp=true'
#
# alias kafka-consumer-lag='docker exec kafka-broker-1 kafka-consumer-groups.sh --bootstrap-server kafka-broker-1:9092 --group order-service-group --describe'


# ==============================================================================
# BASH SCRIPT: Automated Duplicate Payment Test
# ==============================================================================

# Save as: test-duplicate-payment.sh
# chmod +x test-duplicate-payment.sh
# ./test-duplicate-payment.sh

# #!/bin/bash
# set -e
#
# ORDER_ID="test-order-$(date +%s)"
# PAYMENT_EVENT='{
#   "order_id": "'$ORDER_ID'",
#   "amount": 99.99,
#   "status": "PAID",
#   "idempotency_key": "idem-'$ORDER_ID'"
# }'
#
# echo "Order ID: $ORDER_ID"
# echo "Publishing first event..."
# echo "$PAYMENT_EVENT" | docker exec -i kafka-broker-1 kafka-console-producer.sh \
#   --bootstrap-server kafka-broker-1:9092 --topic payment-processed
#
# sleep 1
#
# echo "Publishing duplicate event..."
# echo "$PAYMENT_EVENT" | docker exec -i kafka-broker-1 kafka-console-producer.sh \
#   --bootstrap-server kafka-broker-1:9092 --topic payment-processed
#
# sleep 5
#
# echo "Checking result..."
# PAYMENT_COUNT=$(curl -s "http://localhost:8002/orders/$ORDER_ID" | jq '.payments | length // 0')
#
# if [ "$PAYMENT_COUNT" -eq 1 ]; then
#   echo "✓ PASS: Only 1 payment (idempotent)"
# else
#   echo "✗ FAIL: Found $PAYMENT_COUNT payments (NOT idempotent)"
# fi
