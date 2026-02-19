# API Documentation

## Base URLs

- **Cart Service**: `http://localhost:8001`
- **Order Service**: `http://localhost:8002`
- **Payment Service**: `http://localhost:8003`
- **Inventory Service**: `http://localhost:8004`
- **Notification Service**: `http://localhost:8005`

---

## Health Checks

All services expose a health endpoint:

```http
GET /health
```

**Response (200 OK)**:
```json
{
  "status": "ok",
  "service": "cart-service",
  "version": "1.0.0"
}
```

---

## Cart Service (Port 8001)

### Add Item to Cart

```http
POST /cart/{user_id}/items
Content-Type: application/json

{
  "product_id": "PROD-001",
  "quantity": 2,
  "price": 49.99
}
```

**Response (201 Created)**:
```json
{
  "message": "Item PROD-001 added to cart"
}
```

**Example**:
```bash
curl -X POST http://localhost:8001/cart/user123/items \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "PROD-001",
    "quantity": 2,
    "price": 49.99
  }'
```

---

### Get Cart

```http
GET /cart/{user_id}
```

**Response (200 OK)**:
```json
{
  "user_id": "user123",
  "items": [
    {
      "product_id": "PROD-001",
      "quantity": 2,
      "price": 49.99,
      "item_total": 99.98
    }
  ],
  "total_amount": 99.98,
  "item_count": 1
}
```

**Example**:
```bash
curl http://localhost:8001/cart/user123
```

---

### Remove Item from Cart

```http
DELETE /cart/{user_id}/items/{product_id}
```

**Response (200 OK)**:
```json
{
  "message": "Item PROD-001 removed from cart"
}
```

**Example**:
```bash
curl -X DELETE http://localhost:8001/cart/user123/items/PROD-001
```

---

### Checkout

```http
POST /cart/{user_id}/checkout
```

**Response (200 OK)**:
```json
{
  "message": "Checkout initiated",
  "cart": {
    "user_id": "user123",
    "items": [
      {
        "product_id": "PROD-001",
        "quantity": 2,
        "price": 49.99,
        "item_total": 99.98
      }
    ],
    "total_amount": 99.98,
    "item_count": 1
  }
}
```

**Events Published**:
- `cart.checkout_initiated` → Order Service creates order
- Order Service → `order.created` → Payment Service processes payment
- Payment Service → `payment.processed` or `payment.failed`
- Order Service → `order.confirmed` or `order.cancelled`
- Notification Service → sends email

**Example**:
```bash
curl -X POST http://localhost:8001/cart/user123/checkout
```

---

## Order Service (Port 8002)

### Get Order

```http
GET /orders/{order_id}
```

**Response (200 OK)**:
```json
{
  "order_id": "ORD-ABC123DEF",
  "user_id": "user123",
  "status": "PAID",
  "items": [
    {
      "product_id": "PROD-001",
      "quantity": 2,
      "price": 49.99
    }
  ],
  "total_amount": 99.98,
  "created_at": "2026-02-12T15:30:45.123456"
}
```

**Status Values**:
- `PENDING` - Order created, awaiting payment
- `CONFIRMED` - Payment received, order confirmed
- `PAID` - Payment processed successfully
- `FULFILLED` - Inventory reserved and shipped
- `CANCELLED` - Order cancelled due to payment failure or cancellation request

**Example**:
```bash
curl http://localhost:8002/orders/ORD-ABC123DEF
```

---

## Payment Service (Port 8003)

### Get Payment

```http
GET /payments/{payment_id}
```

**Response (200 OK)**:
```json
{
  "payment_id": "PAY-XYZ789ABC",
  "order_id": "ORD-ABC123DEF",
  "user_id": "user123",
  "amount": 99.98,
  "currency": "USD",
  "method": "card",
  "status": "SUCCESS",
  "reason": null,
  "created_at": "2026-02-12T15:30:50.654321"
}
```

**Status Values**:
- `SUCCESS` - Payment processed successfully
- `FAILED` - Payment failed (see `reason` field)

**Failure Reasons** (when status=FAILED):
- `insufficient_funds` - Card has insufficient funds
- `card_declined` - Card was declined by issuer
- `expired_card` - Card has expired

**Example**:
```bash
curl http://localhost:8003/payments/PAY-XYZ789ABC
```

---

## Inventory Service (Port 8004)

### List All Products

```http
GET /products
```

**Response (200 OK)**:
```json
[
  {
    "product_id": "PROD-001",
    "name": "Wireless Headphones",
    "price": 149.99,
    "stock": 45
  },
  {
    "product_id": "PROD-002",
    "name": "USB-C Cable",
    "price": 12.99,
    "stock": 234
  }
]
```

**Example**:
```bash
curl http://localhost:8004/products
```

---

### Get Product Details

```http
GET /products/{product_id}
```

**Response (200 OK)**:
```json
{
  "product_id": "PROD-001",
  "name": "Wireless Headphones",
  "description": "Premium noise-cancelling headphones",
  "price": 149.99,
  "stock": 45
}
```

**Example**:
```bash
curl http://localhost:8004/products/PROD-001
```

---

## Notification Service (Port 8005)

The Notification Service doesn't expose API endpoints. It runs as a consumer of Kafka events:

- **Subscribes to**: `order.confirmed`, `payment.failed`, `inventory.low`
- **Actions**: Sends emails via Mailhog

You can view sent emails at: `http://localhost:8025`

---

## Event Flow Examples

### Successful Purchase (Happy Path)

```
1. User: POST /cart/user1/items {product_id, quantity, price}
   Event: cart.item_added
   
2. User: POST /cart/user1/checkout
   Event: cart.checkout_initiated
   
3. Order Service consumes cart.checkout_initiated
   → Creates Order (PENDING)
   Event: order.created
   
4. Payment Service consumes order.created
   → Processes payment (80% success rate)
   Event: payment.processed ✅
   
5. Order Service consumes payment.processed
   → Updates Order to PAID
   Event: order.confirmed
   
6. Inventory Service consumes order.created
   → Reserves stock (optimistic lock, 3 retries)
   Event: inventory.reserved
   
7. Order Service consumes inventory.reserved
   → Updates Order to FULFILLED
   
8. Notification Service consumes order.confirmed
   → Sends confirmation email to user
   
9. User: GET /orders/ORD-ABC123
   Response: status=FULFILLED
```

### Failed Payment Path

```
1. Payment Service detects failure (random 20%)
   Event: payment.failed
   
2. Order Service consumes payment.failed
   → Updates Order to CANCELLED
   Event: order.cancelled
   
3. Inventory Service consumes order.cancelled
   → Releases reserved stock
   
4. Notification Service consumes payment.failed
   → Sends failure email to user
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Cart is empty"
}
```

### 404 Not Found
```json
{
  "error": "Order not found"
}
```

---

## Correlation IDs

All events include a `correlation_id` field to trace the full request flow:

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "order.created",
  "correlation_id": "user123-checkout-2026-02-12",
  "timestamp": "2026-02-12T15:30:45.123456",
  "order_id": "ORD-ABC123DEF",
  "user_id": "user123",
  "items": [...],
  "total_amount": 99.98
}
```

View in Kafka UI to trace events through the system.

---

## Performance Notes

- **Cart Item Limit**: No limit, but Redis 24h TTL applies
- **Stock Reservation**: Optimistic locking with 3 retries
- **Payment Success Rate**: 80% (simulated)
- **Event Processing Retry**: 3 attempts before DLQ
- **Outbox Publishing**: 2-second poll intervals

---

## Testing with curl

### Full Purchase Flow

```bash
# 1. Add multiple items to cart
curl -X POST http://localhost:8001/cart/user1/items \
  -H "Content-Type: application/json" \
  -d '{"product_id":"PROD-001","quantity":2,"price":49.99}'

curl -X POST http://localhost:8001/cart/user1/items \
  -H "Content-Type: application/json" \
  -d '{"product_id":"PROD-002","quantity":1,"price":12.99}'

# 2. View cart
curl http://localhost:8001/cart/user1

# 3. Checkout
ORDER_RESPONSE=$(curl -X POST http://localhost:8001/cart/user1/checkout)
echo $ORDER_RESPONSE

# 4. Wait 5 seconds for events to process
sleep 5

# 5. Check order status
# Extract order_id from the response and use it
curl http://localhost:8002/orders/ORD-XXXXX

# 6. Check products list
curl http://localhost:8004/products

# 7. Check emails
open http://localhost:8025
```

---

## Kafka UI Monitoring

Access `http://localhost:8080` to:

- View all 14 topics
- Inspect partitions and replicas
- View messages in real-time
- Monitor consumer groups
- Check lag per consumer group

Key topics to monitor:
- `cart.item_added` - User browsing activity
- `order.created` - New orders
- `payment.processed` / `payment.failed` - Payment outcomes
- `inventory.reserved` - Stock deductions
- `dlq.events` - Failed messages (should stay empty if healthy)

---

## Database Queries

### List Recent Orders

```sql
SELECT order_id, user_id, status, total_amount, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 10;
```

### Check Inventory Levels

```sql
SELECT product_id, name, price, stock
FROM products
ORDER BY stock ASC;
```

### View Analytics

```sql
-- Revenue by minute
SELECT window_start, total_revenue, order_count, avg_order_value
FROM revenue_metrics
ORDER BY window_start DESC;

-- Fraud alerts
SELECT user_id, alert_type, order_count, max_order_amount, window_start
FROM fraud_alerts
ORDER BY window_start DESC;

-- Top selling products
SELECT product_id, units_sold, window_start, rank
FROM inventory_velocity
WHERE rank <= 10
ORDER BY units_sold DESC;
```

---

## Troubleshooting

### Order not progressing past PENDING

1. Check Payment Service logs:
   ```bash
   docker-compose logs payment-service | tail -50
   ```

2. Verify payment was created:
   ```bash
   curl http://localhost:8003/payments/PAY-XXXXX
   ```

3. Check for messages in dlq.events topic (Kafka UI)

### Cart not clearing after checkout

1. Verify Inventory Service is running:
   ```bash
   curl http://localhost:8004/health
   ```

2. Check Order Service logs for order.created event

3. Manually clear:
   ```bash
   docker-compose exec redis redis-cli
   > DEL cart:user1
   ```

### Emails not sending

1. Open Mailhog UI: `http://localhost:8025`
2. Check Notification Service logs:
   ```bash
   docker-compose logs notification-service | tail -50
   ```
3. Verify mailhog container is running:
   ```bash
   docker-compose ps mailhog
   ```

---

## API Rate Limits

No rate limits are enforced (development environment). For production:
- Implement Redis-based rate limiting per user_id
- Add authentication/authorization
- Use API keys instead of open endpoints

---

For more information, see **README.md** in the project root.
