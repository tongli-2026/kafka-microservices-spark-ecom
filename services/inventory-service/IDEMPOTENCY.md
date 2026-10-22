# Inventory idempotency and transactional outbox

`inventory_orders` stores one durable row per `order_id`. Its primary key
serializes concurrent attempts to handle the same order. The row stores the
original items, terminal result (`RESERVED` or `DEPLETED`), stable result
event ID and correlation ID, and later `RELEASED` or `CANCELLED` state.
Redelivery with a different Kafka event ID does not repeat stock changes or
create another outbox row. Conflicting items raise an error.

The stock updates and `stock_reservations` inserts occur in a savepoint
inside the order transaction. If an item fails, the savepoint rolls back all
item changes while the outer transaction commits `DEPLETED`. A payment
failure cancellation locks the order row, releases stock only from
`RESERVED`, deletes active reservations, and commits `RELEASED`. Repeated
cancellation cannot release twice. Earlier cancellation commits `CANCELLED`
and prevents a late `order.created` from reserving stock.

## Outbox workflow

`inventory_outbox_events` has one row per order, enforced by unique
`order_id`; its `event_id` is also unique. Success commits stock changes,
reservations, `RESERVED` status, result ID, and the complete
`inventory.reserved` JSON in one transaction. Shortage commits `DEPLETED`
and the complete `inventory.depleted` JSON in the same outer transaction.
The `order.created` handler never directly sends those two event types.

After database initialization and backfill, a background worker claims a
pending row in a short transaction with `FOR UPDATE SKIP LOCKED`. The claim
has a 60-second lease; Kafka network I/O happens after the transaction
ends. The shared producer waits for that message's delivery callback. Only
a confirmed delivery is marked `published=True`. Failures retain the row,
record `last_error` and increment `attempts`; abandoned claims become
eligible after the lease expires. Multiple workers can claim different rows
without creating more logical results.

Delivery is **at least once**. A crash after the inventory commit leaves a
pending row for the restarted publisher. Kafka unavailability leaves it
pending for retry. A crash after Kafka confirms delivery but before the
`published` update may resend the identical stored event ID and payload.
Order Service's persistent processed-event tracking suppresses duplicate
state transitions. `inventory.low` remains a best-effort alert outside the
outbox: a failed alert is logged without retrying the reservation, and a
crash can lose the alert. Notification Service email delivery may duplicate
on replay because it lacks durable deduplication.

## Existing database rollout and shutdown

Stop **all old Inventory Service instances** and wait for them to exit
before starting any new instance. This prevents mixed direct publishing
and outbox publishing. The old consumer commits offsets only after its
handler finishes; interrupted inputs can be redelivered to the new code.
Keep Order, Payment, Kafka, and PostgreSQL running during this handover.

Start **one** new Inventory Service instance first. `init_db()` uses
`Base.metadata.create_all()` to add the new outbox table; it does not alter
or drop existing tables. It backfills legacy active reservations into
`inventory_orders`, then queues existing `RESERVED`/`DEPLETED` results
that have a stored result ID and correlation ID. Both backfills finish
before publisher and consumer threads start. Unique constraints prevent
multiple logical outbox rows. Backfill is safe to repeat. After startup
succeeds, scale out additional new instances.

Startup sample-product seeding now checks existing product names before
inserting, so restarting the service does not add another sample catalog.
It does not remove duplicates already created by older versions.

Existing results might already have been published by the old service. A
queued result can therefore be sent again during migration with the **same**
event ID. The original timestamp was not stored before this outbox change
and is reconstructed for these older rows. Order Service deduplicates by
result ID; other consumers without durable deduplication may repeat side
effects. Check them before a production rollout. Legacy rows lacking an
original result ID or correlation ID cannot safely be queued. Existing
`RELEASED` rows are not requeued because payment failure has already
advanced those orders. Orders released before the idempotency upgrade have
no remaining Inventory Service record and cannot be reconstructed from its
tables alone.

On shutdown, stop the publisher thread before flushing the producer. A
pending row or unfinished claim remains in PostgreSQL; another new
instance or the restarted worker retries it after the lease expires. A
forced shutdown during publication may cause duplicate Kafka delivery.

## Verification

The SQLite suite and `postgres_integration.py` suite exercise transaction
rollback, duplicate delivery, publisher recovery, and concurrent requests.
Set `INVENTORY_TEST_POSTGRES_URL` to a test database URL; each integration
test creates and drops its own schema. After rebuilding Inventory Service,
run `python scripts/test-inventory-kafka-smoke.py` and
`python scripts/test-payment-kafka-smoke.py` for live Compose checks. They
verify published outbox records and the downstream Saga result. The tests
leave audit orders in the database; successful payment consumes one stock
unit. Simultaneous order creation and payment-failure cancellation remains
a separate race worth testing with multiple processes.
