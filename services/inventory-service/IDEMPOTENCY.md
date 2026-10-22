# Inventory order idempotency

`inventory_orders` stores one durable row per `order_id`. Its primary key
serializes concurrent attempts to handle the same order. The row stores the
original item list, a terminal result (`RESERVED` or `DEPLETED`), the result
event ID and correlation ID, and later `RELEASED` or `CANCELLED` state. A
redelivery with different Kafka event ID but the same order ID reuses that
result event ID. Conflicting product IDs or quantities raise an error.

The stock updates and `stock_reservations` inserts occur in a savepoint inside
the order transaction. If an item fails, the savepoint rolls back all stock
changes while the outer transaction commits `DEPLETED`. A payment-failure
cancellation locks the order row, releases stock only from `RESERVED`, deletes
the active reservation records, and commits `RELEASED`. Repeated cancellation
therefore cannot release twice. An earlier cancellation with no order row
commits `CANCELLED`, preventing a late `order.created` from reserving stock.

## Existing database rollout

`init_db()` creates the new table with `Base.metadata.create_all()`; no
existing table or column is changed. Before starting its consumer, it
backfills `RESERVED` rows from active `stock_reservations` in one transaction.
Stop older Inventory Service consumers before deploying the new version so
they cannot write reservations while this backfill runs. Start one new
instance first to create the table and finish the backfill, then scale out.
The backfill is safe to repeat and leaves existing product and reservation
rows untouched.

Old reservations do not contain the original Kafka result event ID or
correlation ID. Backfilled rows therefore suppress duplicate stock changes
but cannot safely replay an old result event. Orders released before the
upgrade have no remaining Inventory Service record and cannot be reconstructed
from its tables alone; import those historical order IDs from a trusted order
history if replay protection for them is required.

## Remaining delivery limits

The result ID is committed before Kafka publication, so a later
`order.created` redelivery can republish the same result without changing
stock. A crash after commit and before publish still requires a redelivery;
there is no background sender. A transactional outbox would durably queue the
result in the same transaction and close that delivery gap. `inventory.low`
alerts are not persisted for replay.

The SQLite suite and the optional `postgres_integration.py` suite exercise
transaction rollback, duplicate delivery, and concurrent requests. Run the
PostgreSQL suite with `INVENTORY_TEST_POSTGRES_URL` set to a test database URL;
each test creates and drops its own schema. For a live Compose check, run
`python scripts/test-inventory-kafka-smoke.py`. It creates a cancelled test
order through Cart, Order, and Inventory, then verifies unchanged stock,
no reservations, and no payment request. Simultaneous order creation and
payment-failure cancellation remain a separate race worth exercising in a
dedicated multi-process test.
