# Kafka offset handling

`BaseKafkaConsumer` disables automatic offset commits and stores no offset
before processing. It commits the current message synchronously only after
the handler returns, or after a malformed/permanently failing message has
been confirmed in `dlq.events`. A failed commit or DLQ publication causes
the consumer to rejoin its group from the last committed offset. A Kafka
result publication failure remains uncommitted and is retried; it is not
treated as a permanent business failure.

Order Service opens a new SQLAlchemy session for each delivery attempt and
rolls it back on failure, so a retry does not reuse a failed transaction.

`BaseKafkaProducer.publish()` now checks its delivery callback and flush
result. Returning from `publish()` means Kafka acknowledged this message.
The handler and offset commit are still separate operations, so a crash
between them can replay the message. Business handlers must remain
idempotent.

Payment records are committed before result publication. New payments also
write `payment_results` in the same transaction to retain their result event
ID and correlation ID. A redelivery can republish that same result without
processing the payment again. The new table is created by `create_all()`;
existing `payments` rows are untouched. Pre-upgrade payments have no known
result event ID and are therefore not republished on duplicate input.

Notification email delivery is still at least once. A crash after sending
an email but before committing its input offset can send it again; a durable
notification deduplication record would be needed to prevent that. Inventory
now persists `inventory.reserved` and `inventory.depleted` in its own outbox
with the inventory result, then publishes them in a background worker. See
`services/inventory-service/IDEMPOTENCY.md` for deployment and recovery.

Run the shared and payment unit suites without Kafka:

```
.venv/bin/python -m unittest discover -s shared -p 'test_*.py' -q
.venv/bin/python -m unittest discover -s services/order-service -p 'test_*.py' -q
.venv/bin/python -m unittest discover -s services/payment-service -p 'test_*.py' -q
.venv/bin/python -m unittest discover -s services/inventory-service -p 'test_*.py' -q
```

The PostgreSQL suites use a separate schema per test. They require the
Compose database, but no Kafka broker:

```
PAYMENT_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom \
  .venv/bin/python -m unittest discover -s services/payment-service -p postgres_integration.py -q
INVENTORY_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom \
  .venv/bin/python -m unittest discover -s services/inventory-service -p postgres_integration.py -q
```

For a running Compose stack, rebuild the changed services and exercise both
live saga paths:

```
docker compose up -d --build cart-service order-service payment-service inventory-service notification-service
.venv/bin/python scripts/test-inventory-kafka-smoke.py
.venv/bin/python scripts/test-payment-kafka-smoke.py
```

The inventory smoke test creates a cancelled order with unchanged stock. The
payment smoke test creates one real order and accepts either outcome of the
simulated payment: successful payment keeps one stock unit reserved; failed
payment releases it. Both scripts leave order audit records in the database.
The payment test consumes one stock unit if payment succeeds. Unit tests cover
the offset and delivery failure branches without faulting a live broker.
