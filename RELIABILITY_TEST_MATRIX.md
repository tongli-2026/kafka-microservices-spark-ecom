# Reliability Test Matrix

Last verified: 2026-10-22. Results below are observations from the current
`main` checkout. A passing suite means its listed cases passed; it does not
prove that every possible crash timing was exercised. Failure-injection tests
intentionally log exceptions while still passing.

## Run commands

Run from the repository root with the project's `.venv` installed. The `P*`
commands need a local PostgreSQL test database at the URL shown. `P-C` also
needs Redis at `redis://127.0.0.1:6379/0` (override with
`CART_TEST_REDIS_URL`). Integration suites create and drop isolated PostgreSQL
schemas. The `E*` commands need the full Docker Compose application, including
PostgreSQL, Redis, Kafka, and the relevant services. They create audit rows and
may change product stock.

| ID | Command |
| --- | --- |
| U-C | `.venv/bin/python -m unittest discover -s services/cart-service -p test_checkout.py -q` |
| U-I | `.venv/bin/python -m unittest discover -s services/inventory-service -p test_inventory_transactions.py -q` |
| U-P | `.venv/bin/python -m unittest discover -s services/payment-service -p test_payment_handler.py -q` |
| U-N | `.venv/bin/python -m unittest discover -s services/notification-service -p test_delivery.py -q` |
| U-O | `.venv/bin/python -m unittest discover -s services/order-service -p 'test_*.py' -q` |
| U-K | `.venv/bin/python -m unittest discover -s shared -p test_kafka_client.py -q` |
| P-C | `CART_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom .venv/bin/python -m unittest discover -s services/cart-service -p postgres_integration.py -q` |
| P-I | `INVENTORY_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom .venv/bin/python -m unittest discover -s services/inventory-service -p postgres_integration.py -q` |
| P-P | `PAYMENT_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom .venv/bin/python -m unittest discover -s services/payment-service -p postgres_integration.py -q` |
| P-N | `NOTIFICATION_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom .venv/bin/python -m unittest discover -s services/notification-service -p postgres_integration.py -q` |
| P-O | `ORDER_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/kafka_ecom .venv/bin/python -m unittest discover -s services/order-service -p postgres_integration.py -q` |
| E-C | `.venv/bin/python scripts/test-checkout-kafka-smoke.py` |
| E-I | `.venv/bin/python scripts/test-inventory-kafka-smoke.py` |
| E-P | `.venv/bin/python scripts/test-payment-kafka-smoke.py` |

`U*` and `P*` use mocked Kafka producers; they do not require a running Kafka
cluster. `U*` tests use SQLite or fake Redis as appropriate. `P*` tests do not
test Kafka delivery itself. All `E*` tests require actual Kafka. A `P*` result
cannot be inferred from the corresponding `U*` result.

## Failure scenarios and evidence

| Failure scenario | Test file / case | Command | Actual result | PostgreSQL | Kafka | Redis |
| --- | --- | --- | --- | --- | --- | --- |
| HTTP response lost; same checkout key retried after service restart | `services/cart-service/test_checkout.py::test_response_lost_and_restart_returns_same_response`; `scripts/test-checkout-kafka-smoke.py` | U-C, P-C, E-C | U-C 12/12 and P-C 17/17 passed. E-C passed; separate real Cart container rebuild/retry returned the saved response, kept one order and preserved the next cart. | P-C/E-C | E-C | P-C/E-C |
| Concurrent requests use the same key, or different keys against one cart | `services/cart-service/postgres_integration.py::test_same_key_concurrent_requests_have_one_checkout`, `test_different_keys_cannot_checkout_one_cart_twice` | P-C, E-C | P-C 17/17 passed; E-C passed with two concurrent same-key HTTP requests and one order. | Yes | E-C | Yes |
| Keyless concurrent checkout and later new cart generation | `services/cart-service/postgres_integration.py::test_headerless_concurrent_requests_have_one_checkout`; `services/cart-service/test_checkout.py::test_headerless_retry_and_new_cart_generation` | P-C, U-C | Passed. A keyless retry after new items arrive is inherently ambiguous; see limitation below. | P-C | No | P-C |
| Same key reused by another user or with changed explicit snapshot | `services/cart-service/test_checkout.py::test_conflicting_user_and_snapshot_are_rejected`, `test_initial_snapshot_mismatch_does_not_checkout`; `scripts/test-checkout-kafka-smoke.py` | U-C, P-C, E-C | Passed; real HTTP conflict returned 409. | P-C/E-C | E-C | P-C/E-C |
| Checkout DB commit fails before event is durable | `services/cart-service/test_checkout.py::test_checkout_commit_failure_keeps_cart_and_no_event` | U-C, P-C | Passed; cart remains and no event is published. | P-C | No | P-C |
| Kafka publication fails, or acknowledgment precedes worker death | `services/cart-service/test_checkout.py::test_publication_failure_recovers_without_request_retry`, `test_ack_then_process_death_resends_same_event_after_lease_expiry` | U-C, P-C | Passed; outbox retries the original event ID. These are injected failure tests, not a real Kafka outage. | P-C | No | P-C |
| Kafka succeeds but process dies before Redis cleanup; later cart write occurs | `services/cart-service/test_checkout.py::test_kafka_ack_before_cleanup_and_request_retry`, `test_new_items_survive_delayed_cleanup_and_replayed_response`, `test_cleanup_commit_failure_cannot_erase_subsequent_write`; `services/cart-service/postgres_integration.py::test_new_cart_write_between_commit_and_cleanup_is_preserved` | U-C, P-C | Passed; delayed cleanup does not erase later items. | P-C | No | P-C |
| Redis cleanup temporarily fails after checkout commits | `services/cart-service/test_checkout.py::test_cleanup_outage_preserves_successful_response_and_recovers`, `test_background_cleanup_recovers_already_published_checkout` | U-C, P-C | Passed; saved response remains available and cleanup can retry. | P-C | No | P-C |
| Same checkout reaches Order with a different Kafka event ID | `services/order-service/test_checkout_identity.py::test_same_business_checkout_with_different_event_ids_creates_one_order`; `services/order-service/postgres_integration.py::test_concurrent_different_event_ids_create_one_order`; `scripts/test-checkout-kafka-smoke.py` | U-O, P-O, E-C | U-O 16/16, P-O 21/21 and E-C passed; one order/outbox result for the checkout. | P-O/E-C | E-C | E-C |
| Checkout identity migration encounters existing legacy orders | `services/order-service/postgres_integration.py::test_migration_preserves_legacy_rows_and_is_repeatable`; `services/order-service/test_checkout_identity.py::test_legacy_events_remain_idempotent_by_event_id` | P-O, U-O | Passed; migration is repeatable and legacy rows remain valid. | P-O | No | No |
| Multi-item reservation fails on a later item | `services/inventory-service/test_inventory_transactions.py::test_later_item_insufficient_rolls_back_all_items`; `scripts/test-inventory-kafka-smoke.py` | U-I, P-I, E-I | U-I 29 passed/1 skipped; P-I 30/30 passed. E-I passed: `CANCELLED`, unchanged stock/version, zero reservations and payment requests. | P-I/E-I | E-I | E-I |
| Concurrent stock reservation or stock release competes with reservation | `services/inventory-service/test_inventory_transactions.py::test_concurrent_stale_reader_retries_without_overselling`, `test_payment_release_does_not_overwrite_a_concurrent_reservation`, `test_two_orders_compete_for_limited_inventory` | U-I, P-I | Passed; P-I exercises real PostgreSQL locks and conditional updates. | P-I | No | No |
| Inventory result commit/publication failure or duplicate order event | `services/inventory-service/test_inventory_transactions.py::test_commit_failure_does_not_publish_success_and_closes_session`, `test_result_publish_failure_retries_stable_event_id`, `test_crash_after_ack_retries_same_payload_after_lease_expires`, `test_different_event_id_same_order_does_not_reserve_again` | U-I, P-I | Passed; no uncommitted success event, stable retry ID, one business reservation. | P-I | No | No |
| Payment failure compensates committed inventory | `services/inventory-service/test_inventory_transactions.py::test_payment_failure_releases_committed_reservations`; `services/order-service/test_saga_transitions.py::test_payment_failure_emits_one_compensation_event` | U-I, P-I, U-O, P-O | Passed in automated suites. The latest live payment smoke simulated success, so live failure compensation was not observed this run. | P-I/P-O | No | No |
| Same payment is delivered concurrently or payment result is retried | `services/payment-service/postgres_integration.py::test_concurrent_same_order_executes_processor_once`; `services/payment-service/test_payment_handler.py::test_publish_failure_recovers_without_input_redelivery`, `test_commit_failure_never_publishes_or_persists` | U-P, P-P | U-P 9/9 and P-P 10/10 passed; one processor invocation under the PostgreSQL lock. | P-P | No | No |
| Order receives a late success/failure or concurrent conflicting Saga events | `services/order-service/test_saga_transitions.py::test_late_payment_success_cannot_reactivate_cancelled_order`, `test_late_payment_failure_cannot_cancel_fulfilled_order`; `services/order-service/postgres_integration.py::test_conflicting_concurrent_payment_events_have_one_outcome` | U-O, P-O | Passed; terminal states are preserved and one transition wins. | P-O | No | No |
| Order outbox publishers compete, claim expires, or fulfillment repeats | `services/order-service/test_order_outbox_fulfillment.py::test_claim_lease_prevents_second_publisher_and_stale_mark`, `test_paid_order_is_queued_once_with_stable_payload`; `services/order-service/postgres_integration.py::test_two_publishers_do_not_send_same_claim_concurrently`, `test_two_workers_queue_one_fulfillment` | U-O, P-O | Passed; one active claim and one fulfillment outbox row. | P-O | No | No |
| Email is redelivered, SMTP fails, or sender dies mid-transaction | `services/notification-service/test_delivery.py::test_duplicate_after_success_does_not_resend`, `test_failure_persists_and_retry_succeeds`, `test_abandoned_transaction_is_retried`; `services/notification-service/postgres_integration.py::test_concurrent_consumers_send_once` | U-N, P-N | U-N 4/4 and P-N 4/4 passed with fake SMTP sender; no actual SMTP server was tested. | P-N | No | No |
| Kafka handler fails, DLQ publish fails, or producer acknowledgment is missing | `shared/test_kafka_client.py::test_manual_commit_only_after_handler_returns`, `test_dlq_failure_keeps_offset_uncommitted`, `test_retryable_business_failure_keeps_offset_uncommitted`, `test_timeout_without_callback_is_failure` | U-K | 11/11 passed with fake Kafka clients. | No | No | No |
| Normal checkout reaches payment and fulfillment | `scripts/test-payment-kafka-smoke.py`; `scripts/test-checkout-kafka-smoke.py` | E-P, E-C | Both passed on 2026-10-22; payment smoke reached `FULFILLED`, sent notifications and emitted one fulfillment event. | Yes | Yes | Yes |

## Coverage limits

- Cart and Inventory PostgreSQL suites initially hit the local command sandbox's
  `Operation not permitted` network restriction. Both were rerun with local
  database access and passed (17/17 and 30/30). That initial environment error
  was not an application test failure.
- Inventory's SQLite unit suite skips one `FOR UPDATE SKIP LOCKED` case; the
  PostgreSQL suite executes it.
- Live payment-failure compensation, host power loss, and a full broker outage
  were not exercised in the latest smoke run. The automated failure-injection
  cases above cover their code paths but do not prove infrastructure recovery.
- Outbox batching/backoff and durable deferred Kafka consumer recovery are
  planned reliability work. The current tests cover single-event leases,
  retries, and offset behavior; they are **not** evidence for those future
  features.

