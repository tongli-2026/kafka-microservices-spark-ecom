# Kafka Idempotency Testing Guide

## Quick Start

### Setup (One Time)
```bash
chmod +x kafka-idempotency-test.sh
docker-compose up -d  # Ensure Kafka is running
```

### Run Tests
```bash
# Interactive menu
./kafka-idempotency-test.sh

# Or run specific tests
./kafka-idempotency-test.sh dup-payment    # Test duplicate payment handling
./kafka-idempotency-test.sh dup-order      # Test duplicate order handling
./kafka-idempotency-test.sh list-topics    # List all Kafka topics
./kafka-idempotency-test.sh monitor-payments  # Watch payment events in real-time
```

---

## What Idempotency Means

**Idempotency** = Processing the same event twice produces the same result as processing it once.

### Problem It Solves
```
Network Retry Scenario:
├─ Service sends payment event to Kafka
├─ Network timeout occurs
├─ Service retries → sends same event again
├─ Kafka now has 2 identical messages
│
WITHOUT idempotency: Customer charged TWICE ✗
WITH idempotency: Customer charged ONCE ✓
```

---

## Two Testing Approaches

### Approach 1: REST API Snapshots (Built into test-scenarios.sh)

**Scenario 8** in `test-scenarios.sh` tests idempotency by:
1. Creating an order
2. Capturing order metadata at T1 (status, updated_at, total_price, version)
3. Waiting 5 seconds (simulating potential duplicate events)
4. Capturing order metadata at T2
5. Verifying all fields are identical (no spurious updates)
6. Verifying exactly 1 payment exists (no duplicate charges)

```bash
./test-scenarios.sh
# Scenario 8 runs automatically as part of the test suite
```

**Success Indicators:**
- ✓ Status unchanged
- ✓ updated_at timestamp unchanged (proves no spurious updates)
- ✓ total_price unchanged
- ✓ Payment count = 1 (no duplicate charges)

---

### Approach 2: Kafka Event Publishing (kafka-idempotency-test.sh)

This script simulates duplicate events by:
1. Creating a payment/order event with unique ID
2. Publishing to Kafka
3. Publishing the SAME event again (duplicate)
4. Waiting for processing
5. Checking if system created 1 or 2 records

```bash
./kafka-idempotency-test.sh dup-payment
```

**Success Indicator:**
```
✓ PASS: Only 1 payment found (idempotency working)
```

**Failure Indicator:**
```
✗ FAIL: Found 2 payments (duplicate charge!)
```

---

## Test Scenarios Explained

### Test 1: Duplicate Payment Event
```
Timeline:
T=0s   → Publish payment event to Kafka
T=1s   → Publish SAME event again (simulate network retry)
T=5s   → Check: How many payments exist?

Expected: 1 payment (system deduplicates)
Problem: 2 payments (system charged twice!)
```

### Test 2: Duplicate Order Event
```
Timeline:
T=0s   → Publish order event to Kafka
T=1s   → Publish SAME event again (duplicate)
T=5s   → Check: How many orders exist?

Expected: 1 order (system deduplicates)
Problem: 2 orders (duplicate creation!)
```

### Test 3: Monitor Payment Topic
```
Real-time monitoring of payment events
Shows message timestamps, offsets, and content
Useful for debugging event flow
```

### Test 4: Consumer Group Lag
```
Checks if all Kafka messages are being processed
LAG = 0 means all messages consumed
LAG > 0 means some messages are stuck
```

---

## System Architecture (Event Flow)

```
Cart Service → Order Service → Kafka: order-created
                                          ↓
                            Payment Service subscribes
                            (Should process only ONCE)
                                          ↓
                            Kafka: payment-processed
                                          ↓
                            Update Order Status to PAID
```

### Kafka Topics in Your System
```
order-created          - When order is first created
payment-processed      - When payment is attempted
inventory-reserved     - When stock is deducted
order-status-changed   - When order status changes (if exists)
```

To list all topics:
```bash
./kafka-idempotency-test.sh list-topics
```

---

## How to Interpret Results

### ✓ SUCCESS: Idempotency Working
```
▶ Publishing first payment event...
✓ First event published
▶ Publishing DUPLICATE payment event...
✓ Duplicate event published
▶ Verifying: checking order payment status...
✓ PASS: Only 1 payment found (idempotency working) ✓
```

**What it means:**
- System correctly handled duplicate events
- Only processed once despite receiving twice
- No duplicate charges

**Next step:** Nothing! Idempotency is working correctly.

---

### ✗ FAILURE: Idempotency Broken
```
✓ PASS: Found 2 payments (duplicate charge!) ✗
```

**What it means:**
- System processed the same event twice
- Customer was charged twice
- Idempotency keys are NOT being checked

**Next step:** Services need idempotency key implementation

---

## Fixing Failed Tests

If you see `FAIL: Found 2 payments`, your services don't check for duplicate events.

### Solution: Add Idempotency Key Checking

Add this pattern to your Payment Service:

```python
# Python example
class PaymentService:
    def process_payment(self, event):
        # Step 1: Check if already processed
        idempotency_key = event.get('idempotency_key')
        
        # Query database or cache
        if self.is_already_processed(idempotency_key):
            logger.info(f"Event already processed: {idempotency_key}")
            return self.get_cached_result(idempotency_key)
        
        # Step 2: Process new event
        payment = self._create_payment(event)
        
        # Step 3: Cache the result
        self.cache_result(idempotency_key, payment.id, ttl=86400)  # 24 hours
        
        return payment
```

```java
// Java example (Spring Boot)
@Service
public class PaymentService {
    
    @KafkaListener(topics = "payment-processed")
    public void handlePayment(PaymentEvent event) {
        String key = event.getIdempotencyKey();
        
        // Check cache (Redis or DB)
        if (idempotencyStore.exists(key)) {
            log.info("Skipping duplicate: {}", key);
            return;
        }
        
        // Process payment
        Payment payment = createPayment(event);
        
        // Store idempotency key
        idempotencyStore.set(key, payment.getId(), Duration.ofHours(24));
    }
}
```

### Idempotency Key Characteristics
- **Unique:** One per request (order_id + operation)
- **Consistent:** Same for retries of same request
- **Immutable:** Never changes
- **Stored:** In cache or database with TTL (24 hours typical)

---

## All Available Commands

```bash
# Setup
chmod +x kafka-idempotency-test.sh

# Interactive menu
./kafka-idempotency-test.sh

# List topics
./kafka-idempotency-test.sh list-topics

# Monitor topics
./kafka-idempotency-test.sh monitor-payments
./kafka-idempotency-test.sh monitor-orders

# Run tests
./kafka-idempotency-test.sh dup-payment      # Test duplicate payment
./kafka-idempotency-test.sh dup-order        # Test duplicate order

# Diagnostics
./kafka-idempotency-test.sh consumer-lag [group-name]
./kafka-idempotency-test.sh topic-metadata [topic-name]
./kafka-idempotency-test.sh message-timeline [topic-name]

# Main test suite (includes Scenario 8)
./test-scenarios.sh
```

---

## Visual Monitoring

Open Kafka UI in your browser:
```
http://localhost:8080
```

Navigate to **Topics** tab and:
1. Click on a topic (e.g., "payment-processed")
2. View all messages in real-time
3. Watch message count increase when you run tests
4. Click individual messages to see their content

---

## Complete Testing Workflow

### Day 1: Quick Validation
```bash
# Run main test suite
./test-scenarios.sh

# Scenario 8 validates idempotency
# If all pass: ✓ No idempotency issues detected
```

### Day 2: Deep Testing (If Needed)
```bash
# List available topics
./kafka-idempotency-test.sh list-topics

# Test duplicate handling
./kafka-idempotency-test.sh dup-payment

# If test FAILS:
# - Services don't check idempotency keys
# - Need implementation fix (see above)
```

### Day 3: Verify Fixes
```bash
# After implementing idempotency checks, re-run:
./kafka-idempotency-test.sh dup-payment

# Should now show: ✓ PASS: Only 1 payment found
```

---

## Key Concepts

| Concept | Meaning | Example |
|---------|---------|---------|
| **Idempotency Key** | Unique ID for request | `idem-order-123-payment` |
| **Duplicate Event** | Same event received twice | Same message on Kafka twice |
| **Consumer Lag** | Unprocessed messages | Should be 0 (all processed) |
| **Offset** | Message position in topic | Message #42 in partition |
| **Partition** | Topic subdivision | Payment topic has 3 partitions |
| **Consumer Group** | Service subscribing to topic | `payment-service-group` |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect to Kafka broker" | Run `docker-compose up -d` |
| "Topic not found" | Run test-scenarios.sh first to generate events |
| "Consumer group not found" | Service hasn't consumed messages yet |
| "2 payments found (FAIL)" | Add idempotency key checking to Payment Service |
| "No messages found" | Check topic name: `./kafka-idempotency-test.sh list-topics` |

---

## Expected Test Results

### ✓ Healthy System
```
Scenario 8 (REST API):
✓ Status unchanged
✓ updated_at unchanged
✓ total_price unchanged  
✓ Payment count = 1
✓ PASS: Idempotency verified

Kafka Test:
✓ PASS: Only 1 payment found (idempotency working)
✓ PASS: Only 1 order created (idempotency working)
```

### ✗ Unhealthy System
```
✗ FAIL: Found 2 payments (duplicate charge!)
✗ FAIL: updated_at changed (spurious update)
✗ Kafka broker not responding
```

---

## Files You Have

1. **test-scenarios.sh** (1310 lines)
   - 10 test scenarios
   - Scenario 8 validates idempotency via REST API
   - Run: `./test-scenarios.sh`

2. **kafka-idempotency-test.sh** (executable)
   - 8 different Kafka-based tests
   - Interactive menu or CLI mode
   - Run: `./kafka-idempotency-test.sh`

3. **This file (KAFKA_IDEMPOTENCY_TEST.md)**
   - Complete reference guide
   - All commands and explanations

---

## Summary

**Idempotency** = No duplicate charges/orders despite event retries

**Two ways to test:**
1. **REST API** (Scenario 8) - Easiest, built-in
2. **Kafka Events** (kafka-idempotency-test.sh) - Comprehensive

**Success = Only 1 payment despite duplicate events**

**Failure = 2 payments (means fix needed)**

Start with: `./test-scenarios.sh` then `./kafka-idempotency-test.sh dup-payment`
