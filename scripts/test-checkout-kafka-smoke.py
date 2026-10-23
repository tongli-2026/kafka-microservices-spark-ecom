"""Exercise concurrent HTTP checkout and distinct-ID Kafka redelivery on Compose.

Creates an audit order and leaves one new item in its user's cart to verify that
an old checkout retry cannot clear it. Successful payment consumes one stock unit.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
from kafka_client import BaseKafkaProducer

CART_URL = os.getenv("CART_URL", "http://127.0.0.1:8001")
ORDER_URL = os.getenv("ORDER_URL", "http://127.0.0.1:8002")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://127.0.0.1:8004")
DSN = os.getenv("CHECKOUT_SMOKE_POSTGRES_DSN", "dbname=kafka_ecom user=postgres password=postgres host=127.0.0.1 port=5432")


def request_json(url, payload=None, key=None, expected_status=200):
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["Idempotency-Key"] = key
    request = Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            assert response.status == expected_status, response.status
            return json.load(response)
    except HTTPError as error:
        body = json.load(error)
        assert error.code == expected_status, (error.code, body)
        return body


def main():
    products = request_json(f"{INVENTORY_URL}/products")["products"]
    product = next(item for item in products if item["stock"] > 0)
    item = {"product_id": product["product_id"], "quantity": 1, "price": product["price"]}
    user = f"checkout-smoke-{uuid4().hex[:12]}"
    key = str(uuid4())
    url = f"{CART_URL}/cart/{user}/checkout"
    request_json(f"{CART_URL}/cart/{user}/items", item, expected_status=201)
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(request_json, url, {"items": [item]}, key) for _ in range(2)]
        responses = [result.result(timeout=30) for result in requests]
    assert responses[0] == responses[1], responses
    response = responses[0]
    assert request_json(url, {}, key) == response  # Lost-response retry.
    request_json(url, {"items": [{**item, "quantity": 2}]}, key, expected_status=409)
    request_json(f"{CART_URL}/cart/other-{user}/checkout", {}, key, expected_status=409)

    # The old key continues to identify the old request, while the next cart survives.
    request_json(f"{CART_URL}/cart/{user}/items", item, expected_status=201)
    assert request_json(url, {}, key) == response
    assert request_json(f"{CART_URL}/cart/{user}")["items"][0]["quantity"] == 1

    with psycopg2.connect(DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT event_data FROM cart_checkouts WHERE checkout_id = %s", (response["checkout_id"],))
            replay = json.loads(cursor.fetchone()[0])
    replay["event_id"] = str(uuid4())
    producer = BaseKafkaProducer(os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094,localhost:9095,localhost:9096"))
    producer.publish("cart.checkout_initiated", replay)

    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        with psycopg2.connect(DSN) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT order_id, status FROM orders WHERE checkout_id = %s", (response["checkout_id"],))
                orders = cursor.fetchall()
                assert len(orders) <= 1, orders
                if orders and orders[0][1] in ("FULFILLED", "CANCELLED"):
                    order_id, status = orders[0]
                    cursor.execute("SELECT count(*) FROM processed_events WHERE event_id = %s", (replay["event_id"],))
                    replay_processed = cursor.fetchone()[0] == 1
                    cursor.execute("SELECT status FROM inventory_orders WHERE order_id = %s", (order_id,))
                    inventory = cursor.fetchone()
                    cursor.execute("SELECT count(*) FROM payments WHERE order_id = %s", (order_id,))
                    payments = cursor.fetchone()[0]
                    cursor.execute("SELECT count(*) FROM payment_results WHERE order_id = %s", (order_id,))
                    results = cursor.fetchone()[0]
                    cursor.execute("SELECT count(*) FROM stock_reservations WHERE order_id = %s", (order_id,))
                    reservations = cursor.fetchone()[0]
                    cursor.execute("SELECT published, cart_cleared FROM cart_checkouts WHERE checkout_id = %s", (response["checkout_id"],))
                    checkout_state = cursor.fetchone()
                    if (replay_processed and checkout_state == (True, True)
                            and inventory == (("RESERVED",) if status == "FULFILLED" else ("RELEASED",))):
                        assert payments == results == 1, (payments, results)
                        assert reservations == (1 if status == "FULFILLED" else 0), reservations
                        print(json.dumps({"user_id": user, "idempotency_key": key,
                                          "checkout_id": response["checkout_id"], "order_id": order_id,
                                          "order_status": status, "order_count": len(orders),
                                          "payment_count": payments, "payment_result_count": results,
                                          "reservation_count": reservations,
                                          "distinct_event_id_replay_processed": replay_processed}, indent=2))
                        return
        time.sleep(1)
    raise AssertionError(f"Checkout did not complete within 120s: {response['checkout_id']}")


if __name__ == "__main__":
    main()
