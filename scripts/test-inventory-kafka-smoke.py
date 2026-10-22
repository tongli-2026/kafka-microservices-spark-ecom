"""Smoke-test a failed multi-item order against the running Compose stack.

Creates one cancelled test order through Cart -> Order -> Inventory -> Order.
The first item is a real product; the second deliberately does not exist.
The order remains in the database as an audit record, but stock is unchanged.
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
POSTGRES_DSN = os.getenv(
    "INVENTORY_SMOKE_POSTGRES_DSN",
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


def main():
    for url in (CART_URL, ORDER_URL, INVENTORY_URL):
        assert request_json(f"{url}/health")["status"] == "ok", url

    products = request_json(f"{INVENTORY_URL}/products")["products"]
    first = next(product for product in products if product["stock"] >= 1)
    product_id = first["product_id"]
    missing_id = f"SMOKE-MISSING-{uuid4().hex[:12]}"
    user_id = f"inventory-smoke-{uuid4().hex[:12]}"

    with psycopg2.connect(POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT stock, version FROM products WHERE product_id = %s", (product_id,))
            before = cursor.fetchone()

    request_json(f"{CART_URL}/cart/{user_id}/items", {
        "product_id": product_id, "quantity": 1, "price": first["price"],
    })
    request_json(f"{CART_URL}/cart/{user_id}/items", {
        "product_id": missing_id, "quantity": 1, "price": 1.0,
    })
    checkout = request_json(f"{CART_URL}/cart/{user_id}/checkout", {})
    assert [item["product_id"] for item in checkout["cart"]["items"]] == [product_id, missing_id]

    deadline = time.monotonic() + 60
    order_id = None
    while time.monotonic() < deadline:
        orders = request_json(f"{ORDER_URL}/orders/user/{user_id}")["orders"]
        if orders:
            order_id = orders[0]["order_id"]
            if orders[0]["status"] == "CANCELLED":
                break
        time.sleep(1)
    else:
        raise AssertionError(f"Order {order_id or user_id} did not reach CANCELLED within 60 seconds")

    with psycopg2.connect(POSTGRES_DSN) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT stock, version FROM products WHERE product_id = %s", (product_id,))
            after = cursor.fetchone()
            cursor.execute("SELECT count(*) FROM stock_reservations WHERE order_id = %s", (order_id,))
            reservations = cursor.fetchone()[0]
            cursor.execute(
                "SELECT status, failed_product_id, result_event_id FROM inventory_orders WHERE order_id = %s",
                (order_id,),
            )
            inventory_order = cursor.fetchone()
            cursor.execute("SELECT count(*) FROM payments WHERE order_id = %s", (order_id,))
            payments = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM outbox_events WHERE order_id = %s AND event_type = 'order.reservation_confirmed'",
                (order_id,),
            )
            payment_requests = cursor.fetchone()[0]

    assert after == before, f"Stock/version changed: {before} -> {after}"
    assert reservations == 0, f"Found {reservations} partial reservation(s)"
    assert inventory_order is not None, "Missing durable inventory order state"
    assert inventory_order[0] == "DEPLETED" and inventory_order[1] == missing_id
    assert inventory_order[2], "Missing stable result event ID"
    assert payments == 0 and payment_requests == 0, "Payment was requested for a depleted order"
    print(json.dumps({
        "order_id": order_id,
        "order_status": "CANCELLED",
        "inventory_status": inventory_order[0],
        "first_product": product_id,
        "stock_before_after": [before, after],
        "reservations": reservations,
        "payments": payments,
        "payment_requests": payment_requests,
    }, indent=2))


if __name__ == "__main__":
    main()
