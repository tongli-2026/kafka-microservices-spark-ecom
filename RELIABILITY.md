# Payment, notification, and Order Saga reliability

The scenario-to-test mapping, exact run commands, environment needs, and latest
observed results are in [Reliability Test Matrix](RELIABILITY_TEST_MATRIX.md).

## What changed

- Cart checkout now has a durable business identity and Order deduplicates by
  that identity across event IDs. See
  [Checkout business idempotency](services/cart-service/CHECKOUT_IDEMPOTENCY.md)
  for the API contract, cleanup protocol, rollout and verification.

- Payment handlers take a PostgreSQL transaction advisory lock derived from
  `order_id` before consulting `payments` or invoking the payment processor.
  One committed payment, `PaymentResult`, and `payment_outbox_events` row share
  a transaction. A background publisher claims pending rows with a short lease,
  publishes the stored payload, then marks them published. Delivery is at least
  once, with the original result event ID on every attempt.
- Notification processing stores one `notification_deliveries` row per source
  event ID, notification type, and email channel. An `INSERT ... ON CONFLICT`
  followed by `SELECT ... FOR UPDATE` serializes concurrent senders. The row
  lock stays held through the bounded SMTP call. `SENT` is committed only after
  SMTP accepts the message; a failed call commits `FAILED` and raises a
  `RetryableProcessingError`. A crash releases the lock and rolls back the
  unfinished attempt, allowing Kafka redelivery to retry it.
- Order handlers lock the order row, check the processed event ID, and enforce
  the allowed state transition before changing status or writing an outbox
  event. Missing orders and events that arrive before a required earlier state
  raise `RetryableProcessingError`; terminal or stale transitions are recorded
  as handled without another business event. The shared consumer keeps offsets
  uncommitted for retryable failures instead of moving them to the DLQ. Payment
  processor errors and Payment/Order database errors use the same retry path.
- Order's outbox publisher claims one row in a short PostgreSQL transaction
  using `FOR UPDATE SKIP LOCKED` and a lease token. Concurrent service instances
  cannot publish the same live claim. The fulfillment worker locks eligible
  `PAID` orders and stores one `order.fulfilled` event per order in the outbox;
  a partial unique index on `order_id` enforces that limit in PostgreSQL. Kafka
  retries reuse the event ID stored in the outbox payload.

## Schema and rollout

`payment_outbox_events` and `notification_deliveries` are new PostgreSQL
tables. Each service creates its missing table at startup with SQLAlchemy
`create_all`; existing tables and event schemas are unchanged. Deploy the new
Payment and Notification images before expecting these behaviors. Payment
startup backfills rows that already have a `PaymentResult`, preserving their
event IDs. This may republish an already delivered result; downstream durable
idempotency is therefore required. Older `payments` rows with no
`PaymentResult` cannot safely reconstruct their original event ID and are left
for manual reconciliation.

The Notification Service now requires PostgreSQL access. Its Compose service
waits for PostgreSQL health and receives the same database settings as Order,
Inventory, and Payment.

Order startup adds the outbox claim columns and the partial unique fulfillment
index to an existing `outbox_events` table. New databases get the same schema
from SQLAlchemy metadata. The index creation requires any preexisting duplicate
`order.fulfilled` outbox rows to be reconciled first; the old fulfillment job
published directly to Kafka, so it did not normally create such rows.

## Guarantees and limits

- The PostgreSQL lock prevents two **live** handlers of the same order from
  independently invoking the simulated payment processor. A real payment
  provider must receive a stable order-level idempotency key: if a process dies
  after the provider charges but before the local transaction commits, the
  local lock and rows cannot prove whether the charge happened. This is not
  exactly-once payment execution.
- Payment outbox publication is at least once. A crash after Kafka accepts an
  event but before the outbox row is marked published causes a resend with the
  same event ID. The outbox does not make PostgreSQL and Kafka one transaction.
- Notification sends are serialized while the row lock is held. If SMTP accepts
  a message and the process dies before `SENT` commits, a retry can send it
  again. SMTP does not provide an atomic commit with PostgreSQL; absolute
  exactly-once email delivery is not claimed.
- A permanently missing Order row or permanently stalled prior Saga step now
  keeps its Kafka offset uncommitted and requires operational investigation.
  Invalid terminal transitions are ignored with a warning and a processed
  event record. A late success after cancellation may still indicate an
  external charge that needs reconciliation or refund.
- Order outbox publication is still at least once. A crash after Kafka accepts
  an event but before the claim is marked published can resend the stored event
  with the same event ID. A publisher stalled past the lease can also overlap a
  new publisher. Downstream consumers must remain idempotent by event ID.
- During rollout, an old direct `order.fulfilled` message may already be in
  Kafka while its order is still `PAID`. The new worker has no durable record of
  that old message, so it can enqueue a new event for that order. Reconcile
  affected orders before running both versions of the fulfillment worker.
- `notification.send` remains best-effort tracking. Its publish failure cannot
  undo an accepted email. Generic non-retryable handler errors retain the
  existing finite retry and DLQ behavior.

## Interview summary

| Failure | Before | After |
| --- | --- | --- |
| Concurrent payment deliveries | Both could invoke the payment operation before one insert lost the unique-key race. | The second waits on a PostgreSQL transaction advisory lock, then reads and reuses the committed outcome. An outbox retries result publication independently of input redelivery. |
| Email redelivery or SMTP failure | A redelivery could send twice; SMTP failure returned normally and the offset could be committed. | A database row lock serializes sends, `SENT` prevents repeats, and failed sends raise a retryable error without acknowledging the Kafka offset. SMTP acceptance followed by a crash remains ambiguous. |
| Late Saga event | A distinct event ID could change `CANCELLED` to `PAID` or `FULFILLED` to `CANCELLED`. | Every transition checks the locked current state; rejected transitions do not create a new business outbox event. |
