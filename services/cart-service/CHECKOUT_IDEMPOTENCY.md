# Checkout business idempotency

## API contract

`POST /cart/{user_id}/checkout` still accepts no body or `{}`. It now also accepts
an optional `Idempotency-Key` header (1–255 characters) and an optional expected
snapshot:

```json
{"items": [{"product_id": "PROD-123", "quantity": 2, "price": 10.0}]}
```

The response retains `message` and `cart` and adds `checkout_id`. HTTP 200 means
the checkout and its outgoing event have committed to PostgreSQL. Kafka delivery
is asynchronous and may be retried. Redis cleanup normally finishes before the
response; if unavailable, the durable cleanup marker is retried in the background.

Choose a new key for each intended checkout; retain it until the response is
known. Keys are globally unique in this application and retained without TTL.
The same key/user returns the saved response, even after restart, HTTP response
loss, or new items being added to the next cart. It never checks out that next
cart. Reuse by another user or with a different explicitly supplied `items`
snapshot returns HTTP 409. An initial expected snapshot that differs from Redis
also returns 409 without accepting the checkout. Item ordering is ignored when
comparing snapshots. Unknown request body fields are rejected with HTTP 422.

The live cart is mutable state, not a request payload. On a keyed retry with no
`items` field, the key selects the original immutable snapshot, regardless of the
current live cart. A client that wants snapshot conflict detection should send
`items`; a client starting another checkout must send a new key.

Without a key, requests for an uncleaned checkout or an empty cart return the
user's latest saved response. A nonempty cart after cleanup starts a new checkout,
including when its products happen to be identical. With no identifier, an old
request retried after new items are added cannot be distinguished from a new
checkout. Clients needing that guarantee must send `Idempotency-Key`. An empty
cart with no prior checkout still returns HTTP 400.

## Persistence and recovery

`cart_checkouts` is both the checkout record and its outbox. The immutable
`checkout_id`, optional unique key, original response, and complete Kafka payload
are inserted in one PostgreSQL transaction. It also stores publication claims,
attempts, errors and a `cart_cleared` marker. No synchronous Kafka call occurs in
that transaction. Every publication attempt reuses the saved event ID and payload.

All Cart API reads/mutations and checkout snapshot creation take the same
PostgreSQL transaction advisory lock for that user. Keyed checkout requests also
take a key lock before the user lock. Hash collisions only serialize unrelated
operations. All locks are released on rollback or process death.

A committed checkout starts with `cart_cleared=false`. Before allowing a cart
mutation, the service clears the old Redis cart and commits the cleanup marker
in a **separate transaction**. It then reacquires the user lock to perform the
mutation. If deletion succeeds but marker commit fails, the next operation can
safely repeat deletion: no new mutation has been admitted. A delayed cleanup
worker sees the committed marker and does not delete the next cart. The outbox
worker scans cleanup markers even for already published records, so recovery
does not depend on a client retry.

Order receives optional `checkout_id` on `cart.checkout_initiated`. It locks that
business identity, checks for an existing order, validates the payload, and
commits one order, one `order.created` outbox record, and processed-event state.
A unique index on `orders.checkout_id` is an additional database guard. Replays
with distinct event IDs are recorded as processed without creating new orders.
Legacy events without `checkout_id` keep their event-ID deduplication behavior;
old orders keep NULL checkout IDs. No identity is invented for historical rows.

## Migration and rollout

Cart now requires PostgreSQL as well as Redis. Compose supplies `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST`, and `POSTGRES_PORT` and waits
for database health. Existing Python dependencies already include SQLAlchemy and
psycopg2. No new broker or queue service is required.

1. Deploy Order first. Startup runs the repeatable migration in
   `services/order-service/migrations.py`: add nullable `orders.checkout_id` and
   its unique index. Existing data is preserved; `create_all()` alone is not used
   to alter the old table.
2. Drain/stop old Cart instances, then deploy the new Cart version. Startup
   creates the new `cart_checkouts` table with `create_all()`.
3. Verify checkout backlog/cleanup errors and one order per checkout.

Old Cart instances and direct Redis writers do not participate in the user lock
protocol. Do not mix them with new Cart writers during rollout. Existing
unprocessed old checkout events have no business identity and cannot retroactively
be correlated with a new HTTP retry.

## Trade-offs and remaining limits

- PostgreSQL availability is now required for Cart operations. Redis calls have
  bounded socket timeouts; Kafka calls are outside the database transaction.
- Delivery remains at least once: Kafka acknowledgment followed by process death
  can resend the original event. Order's business identity prevents a second order.
- PostgreSQL and Redis are not one transaction. The cleanup protocol relies on
  all writers using Cart's user lock and committing cleanup before new writes.
  Redis loss/restore, direct writes or mixed-version writers require reconciliation.
- Key/checkout records must not be independently deleted while retries can occur.
  This change introduces no automatic retention/pruning policy.
- Existing add/remove item tracking events remain synchronous/best effort;
  their Redis mutation and Kafka publication are not made atomic by this change.
- This stage does not modify the three existing outbox publishers or shared
  consumer retry behavior. Those are stages 2 and 3.

## Verification

```sh
.venv/bin/python -m unittest discover -s services/cart-service -p 'test_*.py' -q
.venv/bin/python -m unittest discover -s services/order-service -p 'test_*.py' -q
CART_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom .venv/bin/python -m unittest discover -s services/cart-service -p postgres_integration.py -q
ORDER_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom .venv/bin/python -m unittest discover -s services/order-service -p postgres_integration.py -q
.venv/bin/python scripts/test-checkout-kafka-smoke.py
.venv/bin/python scripts/test-inventory-kafka-smoke.py
.venv/bin/python scripts/test-payment-kafka-smoke.py
```

Cart integration tests use real PostgreSQL and Redis (`CART_TEST_REDIS_URL`,
default `redis://127.0.0.1:6379/0`) with isolated schemas and disposable user keys.
Unit tests use SQLite and an in-memory Redis substitute, with Kafka producers
mocked. Crash-window tests raise at specific boundaries; they do not simulate
host power loss. The checkout smoke test uses real HTTP, PostgreSQL and Kafka,
including two concurrent HTTP calls and a distinct-event-ID Kafka redelivery.
Smoke tests leave audit orders and may consume one stock unit on successful payment.

### Results from this implementation run

- Cart unit tests: 12 passed.
- Cart PostgreSQL + Redis integration tests: 17 passed.
- Order unit tests: 16 passed; PostgreSQL integration tests: 21 passed.
- Inventory regression: 29 passed, 1 skipped (the SQLite suite cannot exercise
  `FOR UPDATE SKIP LOCKED`). Payment regression: 9 passed. Shared Kafka consumer
  and producer regression: 11 passed.
- Real checkout smoke: concurrent same-key requests and a distinct-event-ID
  Kafka replay produced one order, one payment/result, and one reservation;
  order `ORD-30E9FAC093C8` reached `FULFILLED`.
- After rebuilding/recreating Cart, replaying that saved key returned the same
  response and preserved the next cart's items; the order count remained one.
- Real insufficient-stock smoke: `ORD-58234AA9F55D` reached `CANCELLED`, with
  unchanged stock/version, zero reservations and no payment requests.
- Real headerless payment smoke: `ORD-93BD90EB4744` reached `FULFILLED`, with one
  fulfillment outbox record and sent confirmation/shipment notifications.
- Payment-failure compensation passed automated regression; this live smoke's
  simulated payment succeeded, so it did not exercise live failure compensation.
- `compileall` and `git diff --check` passed. Failure-injection logs are expected
  in the successful test suites. No host power-loss or full Kafka-outage test was
  performed in this stage.

## Interview explanation

An event ID alone could not identify a retried checkout: each HTTP retry generated
a new event. I introduced a durable checkout identity and saved the response and
event in one PostgreSQL transaction, then enforced that identity in Order. I also
serialized Redis cart writes with a durable cleanup marker so a delayed cleanup
could not delete newly added products. This provides one logical order per
checkout while accepting at-least-once Kafka delivery. The trade-off is making
Cart depend on PostgreSQL and retaining checkout identities for safe retries.
