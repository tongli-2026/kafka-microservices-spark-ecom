# API Documentation

## Table of Contents
1. [Quick Reference](#quick-reference)
2. [Base URLs](#base-urls)
3. [Schema Types](#schema-types)
4. [Health Checks](#health-checks)
5. [Cart Service](#cart-service)
6. [Order Service](#order-service)
7. [Payment Service](#payment-service)
8. [Inventory Service](#inventory-service)
9. [Event Flow Examples](#event-flow-examples)
10. [Testing Guide](#testing-guide)

---

## Quick Reference

### All 14 Endpoints Summary

| Service | Endpoint | Method | Request | Response | Status |
|---------|----------|--------|---------|----------|--------|
| **Cart** | `/health` | GET | - | `HealthResponse` | ✅ |
| | `/cart/{user_id}/items` | POST | `CartItemRequest` | `MessageResponse` | ✅ |
| | `/cart/{user_id}/items/{product_id}` | DELETE | - | `MessageResponse` | ✅ |
| | `/cart/{user_id}/items/{product_id}` | PUT | `UpdateQuantityRequest` | `MessageResponse` | ✅ |
| | `/cart/{user_id}` | GET | - | `CartResponse` | ✅ |
| | `/cart/{user_id}/checkout` | POST | - | `CheckoutResponse` | ✅ |
| **Order** | `/health` | GET | - | `HealthResponse` | ✅ |
| | `/orders/{order_id}` | GET | - | `OrderResponse` | ✅ |
| | `/orders/user/{user_id}` | GET | - | `UserOrdersResponse` | ✅ |
| **Inventory** | `/health` | GET | - | `HealthResponse` | ✅ |
| | `/products` | GET | - | `ProductsListResponse` | ✅ |
| | `/products/{product_id}` | GET | - | `ProductSchema` | ✅ |
| **Payment** | `/health` | GET | - | `HealthResponse` | ✅ |
| | `/payments/{payment_id}` | GET | - | `PaymentSchema` | ✅ |

### Quick Test Commands

```bash
# Health checks
curl http://localhost:8001/health | jq .  # Cart
curl http://localhost:8002/health | jq .  # Order
curl http://localhost:8004/health | jq .  # Inventory
curl http://localhost:8003/health | jq .  # Payment

# Add item to cart
curl -X POST http://localhost:8001/cart/user001/items \
  -H "Content-Type: application/json" \
  -d '{"product_id":"mouse","quantity":2,"price":29.99}'

# Get cart
curl http://localhost:8001/cart/user001

# List products
curl http://localhost:8004/products

# Get order
curl http://localhost:8002/orders/ORD-12345
```

### Swagger Documentation
- Cart: http://localhost:8001/docs
- Order: http://localhost:8002/docs
- Inventory: http://localhost:8004/docs
- Payment: http://localhost:8003/docs

---

## Base URLs

- **Cart Service**: `http://localhost:8001`
- **Order Service**: `http://localhost:8002`
- **Payment Service**: `http://localhost:8003`
- **Inventory Service**: `http://localhost:8004`
- **Notification Service**: `http://localhost:8005`

---

## Schema Types

### Request Schemas
- **CartItemRequest**: `{product_id, quantity, price}`
- **UpdateQuantityRequest**: `{quantity}`
- **CreateOrderRequest**: `{user_id, items, total_amount}`

### Response Schemas
| Schema | Fields | Used In |
|--------|--------|---------|
| **HealthResponse** | status, service, version | All `/health` endpoints |
| **MessageResponse** | message | Cart add/remove/update |
| **CartResponse** | user_id, items[], total_amount, item_count | GET /cart/{user_id} |
| **CheckoutResponse** | message, cart | POST /cart/{user_id}/checkout |
| **OrderResponse** | order_id, user_id, status, items[], total_amount, created_at, updated_at | GET /orders/{order_id} |
| **UserOrdersResponse** | user_id, orders[], total_orders | GET /orders/user/{user_id} |
| **ProductSchema** | product_id, name, description, price, stock | GET /products/{product_id} |
| **ProductsListResponse** | products[], total_products | GET /products |
| **PaymentSchema** | payment_id, order_id, user_id, amount, currency, method, status, reason, created_at | GET /payments/{payment_id} |

### Field Validation
- **CartItemRequest**: product_id (required), quantity (required, > 0), price (required, > 0)
- **UpdateQuantityRequest**: quantity (required, >= 0, zero = remove item)
- **ProductSchema**: All fields required except description (optional)
- **PaymentSchema**: All fields except reason (optional) and created_at (optional)

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

## Schema Documentation

### Overview
All 14 API endpoints use Pydantic-based response models for:
- ✅ Type safety and validation
- ✅ Automatic OpenAPI documentation
- ✅ Swagger UI generation
- ✅ Request/response validation

### Request Schemas

**`CartItemRequest`**
```python
product_id: int          # Required
quantity: int            # Required
```

**`PaymentRequest`**
```python
order_id: int           # Required
amount: float           # Required
payment_method: str     # Required
```

**`AddProductRequest`**
```python
name: str               # Required
price: float            # Required
quantity: int           # Required
description: str | None # Optional
```

### Response Schemas

**`HealthResponse`** (4 endpoints)
```python
status: str             # "healthy" or "unhealthy"
timestamp: datetime     # Current server time
service: str            # Service name
```

**`MessageResponse`** (Cart: 3 endpoints)
```python
message: str            # Operation result message
success: bool           # True if operation succeeded
```

**`CheckoutResponse`** (Cart: 1 endpoint)
```python
order_id: int           # Created order ID
message: str            # Status message
success: bool           # True if checkout succeeded
```

**`CartResponse`** (Cart: 1 endpoint)
```python
user_id: int            # User identifier
items: list[CartItem]   # Products in cart
total_price: float      # Sum of all items
item_count: int         # Number of items
```

**`OrderResponse`** (Order: 1 endpoint)
```python
order_id: int           # Unique order identifier
user_id: int            # Customer ID
total_amount: float     # Order total
status: str             # Order status (pending, paid, etc.)
items: list[dict]       # Ordered items
created_at: datetime    # Order creation time (Optional)
updated_at: datetime    # Last update time (Optional)
```

**`UserOrdersResponse`** (Order: 1 endpoint)
```python
user_id: int            # Customer ID
orders: list[OrderResponse]  # All orders by user
order_count: int        # Total number of orders
```

**`ProductSchema`** (Inventory: 1 endpoint)
```python
product_id: int         # Unique identifier
name: str               # Product name
price: float            # Unit price
quantity_available: int # Stock quantity
description: str | None # Product description (Optional)
```

**`ProductsListResponse`** (Inventory: 1 endpoint)
```python
products: list[ProductSchema]  # All products
total_count: int        # Number of products
page: int               # Current page (if paginated)
```

**`PaymentSchema`** (Payment: 1 endpoint)
```python
payment_id: int         # Unique identifier
order_id: int           # Associated order
amount: float           # Payment amount
status: str             # Payment status (pending, completed, failed)
payment_method: str     # How payment was made
created_at: datetime    # Payment timestamp (Optional)
```

**`ErrorResponse`** (All services)
```python
detail: str             # Error message
status_code: int        # HTTP status
timestamp: datetime     # When error occurred
```

### Endpoint Implementation Pattern

All endpoints follow this pattern:

```python
from fastapi import HTTPException
from .schemas import ResponseSchema, ErrorResponse

@app.get("/endpoint/{id}", response_model=ResponseSchema)
async def endpoint_name(id: int) -> ResponseSchema:
    """
    Endpoint description.
    
    Returns:
        ResponseSchema: The response with validated fields
        
    Raises:
        HTTPException: 404 if not found, 500 on error
    """
    try:
        result = repository.get_by_id(id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return ResponseSchema(**result.dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### Service-by-Service Schema Summary

#### Cart Service (`services/cart-service/schemas.py`)
**New Schemas**: MessageResponse, CheckoutResponse
**Updated Endpoints**: 6 total
- POST /cart/{user_id}/items → MessageResponse
- DELETE /cart/{user_id}/items/{product_id} → MessageResponse
- PUT /cart/{user_id}/items/{product_id} → MessageResponse
- GET /cart/{user_id} → CartResponse
- POST /cart/{user_id}/checkout → CheckoutResponse
- GET /health → HealthResponse

#### Order Service (`services/order-service/schemas.py`)
**New Schemas**: UserOrdersResponse, ErrorResponse
**Enhanced Schemas**: OrderResponse (added created_at, updated_at)
**Updated Endpoints**: 3 total
- GET /orders/{order_id} → OrderResponse
- GET /orders/user/{user_id} → UserOrdersResponse
- GET /health → HealthResponse

#### Inventory Service (`services/inventory-service/schemas.py`)
**New Schemas**: ProductsListResponse, ErrorResponse
**Enhanced Schemas**: ProductSchema (added description)
**Updated Endpoints**: 3 total
- GET /products → ProductsListResponse
- GET /products/{product_id} → ProductSchema
- GET /health → HealthResponse

#### Payment Service (`services/payment-service/schemas.py`)
**New Schemas**: PaymentListResponse, ErrorResponse
**Enhanced Schemas**: PaymentSchema (added created_at)
**Updated Endpoints**: 2 total
- GET /payments/{payment_id} → PaymentSchema
- GET /health → HealthResponse

### Type Safety & Validation

FastAPI automatically validates all responses using Pydantic:

```python
# ✅ VALID - All fields present and correct types
{"status": "healthy", "timestamp": "2024-01-01T12:00:00", "service": "cart"}

# ❌ INVALID - Wrong type
{"status": "healthy", "timestamp": 12345, "service": "cart"}  # timestamp not datetime

# ❌ INVALID - Missing required field
{"status": "healthy", "service": "cart"}  # timestamp missing
```

### OpenAPI/Swagger Integration

All endpoints automatically generate OpenAPI documentation:

**Access Swagger UI:**
- Cart: http://localhost:8001/docs
- Order: http://localhost:8002/docs
- Inventory: http://localhost:8003/docs
- Payment: http://localhost:8004/docs

**Access OpenAPI JSON:**
- Cart: http://localhost:8001/openapi.json
- Order: http://localhost:8002/openapi.json
- Inventory: http://localhost:8003/openapi.json
- Payment: http://localhost:8004/openapi.json

---

For more information, see **README.md** in the project root.
