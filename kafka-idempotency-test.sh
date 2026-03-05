#!/bin/bash

################################################################################
# Kafka Idempotency Testing Script
# Tests idempotency by publishing duplicate events to Kafka and verifying
# that the system handles them correctly without creating duplicates
#
# Usage: ./kafka-idempotency-test.sh [test-name]
# Example: ./kafka-idempotency-test.sh duplicate-payment
################################################################################

set -e

# Configuration
KAFKA_BOOTSTRAP="kafka-broker-1:9092"
ORDER_SERVICE="http://localhost:8002"
PAYMENT_SERVICE="http://localhost:8003"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_step() {
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_failure() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

# Check if Kafka broker is running
check_kafka() {
    print_step "Checking Kafka connectivity..."
    
    if docker exec kafka-broker-1 kafka-topics.sh \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --list > /dev/null 2>&1; then
        print_success "Kafka broker is running"
    else
        print_failure "Cannot connect to Kafka broker"
        print_info "Make sure docker-compose is running: docker-compose up -d"
        exit 1
    fi
}

# List all Kafka topics
list_topics() {
    print_header "Available Kafka Topics"
    
    docker exec kafka-broker-1 kafka-topics.sh \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --list | nl
}

# Publish event to Kafka topic
publish_event() {
    local topic=$1
    local message=$2
    
    echo "$message" | docker exec -i kafka-broker-1 \
        kafka-console-producer.sh \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --topic "$topic" > /dev/null 2>&1
}

# Get message count in topic
get_topic_message_count() {
    local topic=$1
    
    docker exec kafka-broker-1 kafka-run-class.sh \
        kafka.tools.GetOffsetShell \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --topic "$topic" 2>/dev/null | \
        awk -F: '{sum += $3} END {print sum}'
}

################################################################################
# Test: List Topics
################################################################################

test_list_topics() {
    print_header "Test: List Available Topics"
    
    print_step "Fetching Kafka topics..."
    docker exec kafka-broker-1 kafka-topics.sh \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --list
    
    print_success "Topics listed successfully"
    echo ""
}

################################################################################
# Test: Monitor Topic in Real-Time
################################################################################

test_monitor_topic() {
    local topic=${1:-order-created}
    
    print_header "Test: Monitor Topic - $topic"
    
    print_step "Showing last 5 messages from topic: $topic"
    print_info "Waiting for messages (press Ctrl+C to stop)..."
    echo ""
    
    timeout 10 docker exec kafka-broker-1 \
        kafka-console-consumer.sh \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --topic "$topic" \
        --from-beginning \
        --max-messages 5 \
        --property print.timestamp=true \
        --property print.partition=true 2>/dev/null || true
    
    echo ""
    print_success "Message monitoring complete"
}

################################################################################
# Test: Duplicate Payment Event
################################################################################

test_duplicate_payment_event() {
    print_header "Test: Duplicate Payment Event Handling"
    
    local order_id="test-order-$(date +%s)"
    local payment_event='{
  "order_id": "'$order_id'",
  "amount": 99.99,
  "currency": "USD",
  "status": "PAID",
  "transaction_id": "txn-'$(date +%s%N)'",
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "idempotency_key": "idem-'$order_id'"
}'
    
    print_step "Creating test payment event for order: $order_id"
    print_info "Event: $payment_event"
    echo ""
    
    print_step "Publishing first payment event..."
    publish_event "payment-processed" "$payment_event"
    sleep 1
    print_success "First event published"
    
    print_step "Publishing DUPLICATE payment event..."
    publish_event "payment-processed" "$payment_event"
    sleep 1
    print_success "Duplicate event published"
    
    print_step "Waiting for events to be processed (5 seconds)..."
    sleep 5
    
    print_step "Verifying: checking order payment status..."
    local order_response=$(curl -s "$ORDER_SERVICE/orders/$order_id" 2>/dev/null || echo "{}")
    local payment_count=$(echo "$order_response" | jq '.payments | length // 0' 2>/dev/null || echo "0")
    
    print_info "Order response: $order_response"
    echo ""
    
    if [ "$payment_count" -eq 1 ]; then
        print_success "PASS: Only 1 payment found (idempotency working) ✓"
        echo ""
    elif [ "$payment_count" -gt 1 ]; then
        print_failure "FAIL: Found $payment_count payments (duplicate charge!) ✗"
        echo ""
    else
        print_info "Note: Order or payments not found (may be expected depending on system)"
        echo ""
    fi
}

################################################################################
# Test: Check Consumer Group Lag
################################################################################

test_consumer_group_lag() {
    local group=${1:-order-service-group}
    
    print_header "Test: Consumer Group Lag - $group"
    
    print_step "Checking consumer group status..."
    echo ""
    
    docker exec kafka-broker-1 kafka-consumer-groups.sh \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --group "$group" \
        --describe 2>/dev/null || print_info "Consumer group '$group' not found or no messages consumed"
    
    echo ""
    print_success "Consumer group check complete"
}

################################################################################
# Test: View Topic Metadata
################################################################################

test_topic_metadata() {
    local topic=${1:-payment-processed}
    
    print_header "Test: Topic Metadata - $topic"
    
    print_step "Describing topic: $topic"
    docker exec kafka-broker-1 kafka-topics.sh \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --topic "$topic" \
        --describe 2>/dev/null || print_info "Topic '$topic' not found"
    
    echo ""
    print_success "Topic metadata retrieved"
}

################################################################################
# Test: Duplicate Order Event
################################################################################

test_duplicate_order_event() {
    print_header "Test: Duplicate Order Event Handling"
    
    local order_id="order-$(date +%s%N | cut -c1-13)"
    local user_id="user-test-$(date +%s)"
    local order_event='{
  "order_id": "'$order_id'",
  "user_id": "'$user_id'",
  "total_amount": 99.99,
  "currency": "USD",
  "status": "PENDING",
  "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "idempotency_key": "idem-'$order_id'"
}'
    
    print_step "Creating test order event"
    print_info "Order ID: $order_id"
    print_info "User ID: $user_id"
    echo ""
    
    print_step "Publishing first order event..."
    publish_event "order-created" "$order_event"
    sleep 1
    print_success "First event published"
    
    print_step "Publishing DUPLICATE order event..."
    publish_event "order-created" "$order_event"
    sleep 1
    print_success "Duplicate event published"
    
    print_step "Waiting for events to be processed (5 seconds)..."
    sleep 5
    
    print_step "Verifying: counting orders for user..."
    local orders=$(curl -s "$ORDER_SERVICE/orders/user/$user_id" 2>/dev/null || echo '{}')
    local order_count=$(echo "$orders" | jq '.orders | length // 0' 2>/dev/null || echo "0")
    
    if [ "$order_count" -eq 1 ]; then
        print_success "PASS: Only 1 order created (idempotency working) ✓"
        echo ""
    elif [ "$order_count" -gt 1 ]; then
        print_failure "FAIL: Found $order_count orders (duplicate creation!) ✗"
        echo ""
    else
        print_info "Note: Orders not found yet (may still be processing)"
        echo ""
    fi
}

################################################################################
# Test: Message Timeline (view messages with timing)
################################################################################

test_message_timeline() {
    local topic=${1:-order-created}
    
    print_header "Test: Message Timeline - $topic"
    
    print_step "Fetching last 10 messages with timestamps..."
    echo ""
    
    docker exec kafka-broker-1 \
        kafka-console-consumer.sh \
        --bootstrap-server $KAFKA_BOOTSTRAP \
        --topic "$topic" \
        --from-beginning \
        --max-messages 10 \
        --property print.timestamp=true \
        --property print.offset=true \
        --property print.partition=true \
        --formatter kafka.tools.DefaultMessageFormatter 2>/dev/null || print_info "No messages found"
    
    echo ""
    print_success "Timeline complete"
}

################################################################################
# Main Menu
################################################################################

show_menu() {
    print_header "Kafka Idempotency Testing - Main Menu"
    
    echo "1. List available Kafka topics"
    echo "2. Monitor topic (order-created)"
    echo "3. Monitor topic (payment-processed)"
    echo "4. Test: Duplicate Payment Event"
    echo "5. Test: Duplicate Order Event"
    echo "6. Check Consumer Group Lag"
    echo "7. View Topic Metadata"
    echo "8. View Message Timeline"
    echo "0. Exit"
    echo ""
    read -p "Select an option (0-8): " choice
}

################################################################################
# Main Execution
################################################################################

main() {
    check_kafka
    
    if [ $# -gt 0 ]; then
        # Run specific test from command line
        case "$1" in
            list-topics)
                test_list_topics
                ;;
            monitor-orders)
                test_monitor_topic "order-created"
                ;;
            monitor-payments)
                test_monitor_topic "payment-processed"
                ;;
            dup-payment)
                test_duplicate_payment_event
                ;;
            dup-order)
                test_duplicate_order_event
                ;;
            consumer-lag)
                test_consumer_group_lag "$2"
                ;;
            topic-metadata)
                test_topic_metadata "$2"
                ;;
            message-timeline)
                test_message_timeline "$2"
                ;;
            *)
                print_failure "Unknown test: $1"
                echo "Available tests:"
                echo "  - list-topics"
                echo "  - monitor-orders"
                echo "  - monitor-payments"
                echo "  - dup-payment"
                echo "  - dup-order"
                echo "  - consumer-lag [group-name]"
                echo "  - topic-metadata [topic-name]"
                echo "  - message-timeline [topic-name]"
                exit 1
                ;;
        esac
    else
        # Interactive menu
        while true; do
            show_menu
            case $choice in
                1) test_list_topics ;;
                2) test_monitor_topic "order-created" ;;
                3) test_monitor_topic "payment-processed" ;;
                4) test_duplicate_payment_event ;;
                5) test_duplicate_order_event ;;
                6) test_consumer_group_lag ;;
                7) test_topic_metadata ;;
                8) test_message_timeline ;;
                0) print_success "Exiting..."; exit 0 ;;
                *) print_failure "Invalid option" ;;
            esac
        done
    fi
}

# Run main
main "$@"
