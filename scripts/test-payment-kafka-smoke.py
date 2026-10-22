"""Smoke-test Cart -> Order -> Inventory -> Payment on the running Compose stack.

Creates one real order. Successful simulated payment consumes one stock unit;
failed payment must release the reservation and restore that stock unit.
The created order and payment remain in PostgreSQL as test data.
"""

import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg2


CART_URL = os.getenv("CART_URL", "http://127.0.0.1:8001")
ORDER_URL = os.getenv("ORDER_URL", "http://127.0.0.1:8002")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://127.0.0.1:8004")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://127.0.0.1:8003")
POSTGRES_DSN = os.getenv(
    "PAYMENT_SMOKE_POSTGRES_DSN",
    "dbname=kafka_ecom user=postgres password=postgres host=127.0.0.1 port=5432",
)


def request_json(url, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            return json.load(response)
    except HTTPError as error:
        raise AssertionError(f"{url}: HTTP {error.code}: {error.read().decode()}") from error


def read_state(order_id, product_id):
    with psycopg2.connect(POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM payments WHERE order_id = %s", (order_id,))
            payment = cursor.fetchone()
            cursor.execute("SELECT event_id FROM payment_results WHERE order_id = %s", (order_id,))
            result = cursor.fetchone()
            cursor.execute("SELECT status FROM inventory_orders WHERE order_id = %s", (order_id,))
            inventory = cursor.fetchone()
            cursor.execute(
                "SELECT event_type, published FROM inventory_outbox_events WHERE order_id = %s",
                (order_id,),
            )
            outbox = cursor.fetchone()
            cursor.execute("SELECT stock FROM products WHERE product_id = %s", (product_id,))
            stock = cursor.fetchone()[0]
    return payment, result, inventory, outbox, stock


def main():
    for url in (CART_URL, ORDER_URL, INVENTORY_URL, PAYMENT_URL):
        assert request_json(f"{url}/health")["status"] == "ok", url

    products = request_json(f"{INVENTORY_URL}/products")["products"]
    product = next((item for item in products if item["stock"] >= 1), None)
    assert product is not None, "No product with stock is available for the smoke test"
    product_id = product["product_id"]
    user_id = f"payment-smoke-{uuid4().hex[:12]}"

    with psycopg2.connect(POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT stock FROM products WHERE product_id = %s", (product_id,))
            stock_before = cursor.fetchone()[0]

    request_json(f"{CART_URL}/cart/{user_id}/items", {
        "product_id": product_id, "quantity": 1, "price": product["price"],
    })
    request_json(f"{CART_URL}/cart/{user_id}/checkout", {})

    deadline = time.monotonic() + 60
    order_id = None
    last_state = None
    while time.monotonic() < deadline:
        orders = request_json(f"{ORDER_URL}/orders/user/{user_id}")["orders"]
        if orders:
            order_id = orders[0]["order_id"]
            order_status = orders[0]["status"]
            payment, result, inventory, outbox, stock_after = read_state(order_id, product_id)
            last_state = (order_status, payment, result, inventory, outbox, stock_after)
            if payment and result and inventory and outbox and result[0] and outbox == ("inventory.reserved", True):
                if payment[0] == "SUCCESS" and order_status in ("PAID", "FULFILLED"):
                    assert inventory[0] == "RESERVED", inventory
                    assert stock_after == stock_before - 1, (stock_before, stock_after)
                    break
                if payment[0] == "FAILED" and order_status == "CANCELLED" and inventory[0] == "RELEASED":
                    assert stock_after == stock_before, (stock_before, stock_after)
                    break
        time.sleep(1)
    else:
        raise AssertionError(f"Payment flow timed out for {order_id or user_id}: {last_state}")

    print(json.dumps({
        "order_id": order_id,
        "order_status": order_status,
        "payment_status": payment[0],
        "payment_result_event_id": result[0],
        "inventory_status": inventory[0],
        "inventory_outbox_published": outbox[1],
        "product_id": product_id,
        "stock_before": stock_before,
        "stock_after": stock_after,
    }, indent=2))


if __name__ == "__main__":
    main()
