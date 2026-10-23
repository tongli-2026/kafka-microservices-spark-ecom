"""Persist checkout before delivery and serialize cart cleanup with mutations."""

import hashlib
import logging
from uuid import uuid4

from sqlalchemy import text

from events import CartCheckoutInitiatedEvent
from models import Checkout

logger = logging.getLogger(__name__)


class CheckoutConflict(ValueError):
    pass


class EmptyCart(ValueError):
    pass


def _lock(db, identity):
    # All Cart instances must use these locks, including ordinary cart writes.
    # SQLite tests are sequential; PostgreSQL tests exercise actual concurrency.
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def _items_key(items):
    return sorted((item["product_id"], item["quantity"], item["price"]) for item in items)


class CheckoutService:
    def __init__(self, session_factory, cart_repository):
        self.session_factory = session_factory
        self.cart = cart_repository

    def _pending(self, db, user_id):
        return db.query(Checkout).filter_by(user_id=user_id, cart_cleared=False).all()

    def _clear_pending(self, rows, user_id):
        # A mutation cannot pass the user lock until this marker is committed.
        # If Redis succeeds but the DB commit fails, repeating DEL is safe.
        self.cart.clear_cart(user_id)
        for row in rows:
            row.cart_cleared = True

    def cart_operation(self, user_id, operation):
        """Finish committed cleanup in its own transaction before changing Redis.

        The separate commit is essential: otherwise a crash after adding a new
        item could roll back the cleanup marker and a later DEL would erase it.
        """
        while True:
            with self.session_factory.begin() as db:
                _lock(db, f"cart-user:{user_id}")
                pending = self._pending(db, user_id)
                if pending:
                    self._clear_pending(pending, user_id)
                    continue  # Commit cleanup before allowing any mutation.
                return operation(self.cart)

    def cleanup(self, user_id):
        # This may also be called by a delayed publisher. With no pending marker
        # it does nothing, so it cannot delete the next generation of cart items.
        with self.session_factory.begin() as db:
            _lock(db, f"cart-user:{user_id}")
            pending = self._pending(db, user_id)
            if pending:
                self._clear_pending(pending, user_id)

    @staticmethod
    def _check_request(row, user_id, expected_items):
        if row.user_id != user_id:
            raise CheckoutConflict("Idempotency-Key belongs to another user")
        if expected_items is not None and _items_key(expected_items) != _items_key(row.response_data["cart"]["items"]):
            raise CheckoutConflict("Idempotency-Key was already used with a different cart snapshot")

    def submit(self, user_id, idempotency_key=None, expected_items=None):
        while True:
            with self.session_factory.begin() as db:
                # Fixed ordering: key first, then user. Mutation paths only lock user.
                if idempotency_key is not None:
                    _lock(db, f"checkout-key:{idempotency_key}")
                _lock(db, f"cart-user:{user_id}")
                existing = (db.query(Checkout).filter_by(idempotency_key=idempotency_key).one_or_none()
                            if idempotency_key is not None else None)
                if existing is not None:
                    self._check_request(existing, user_id, expected_items)
                    response = existing.response_data
                    break

                pending = self._pending(db, user_id)
                if pending:
                    if idempotency_key is None:
                        self._check_request(pending[0], user_id, expected_items)
                        response = pending[0].response_data
                        break
                    self._clear_pending(pending, user_id)
                    continue

                cart = self.cart.get_cart(user_id)
                if not cart["items"]:
                    # Legacy headerless clients can repeat the last checkout
                    # while the cart is empty. A newly populated cart starts a
                    # new operation; explicit keys remove that ambiguity.
                    previous = (db.query(Checkout).filter_by(user_id=user_id)
                                .order_by(Checkout.created_at.desc(), Checkout.checkout_id.desc()).first())
                    if idempotency_key is None and previous is not None:
                        self._check_request(previous, user_id, expected_items)
                        response = previous.response_data
                        break
                    raise EmptyCart("Cart is empty")
                if expected_items is not None and _items_key(expected_items) != _items_key(cart["items"]):
                    raise CheckoutConflict("Cart has changed since the supplied snapshot")

                checkout_id = str(uuid4())
                event = CartCheckoutInitiatedEvent(
                    checkout_id=checkout_id, user_id=user_id,
                    items=cart["items"], total_amount=cart["total_amount"],
                    correlation_id=str(uuid4()),
                )
                response = {"message": "Checkout initiated", "cart": cart, "checkout_id": checkout_id}
                db.add(Checkout(
                    checkout_id=checkout_id, idempotency_key=idempotency_key,
                    user_id=user_id, response_data=response, event_data=event.model_dump_json(),
                ))
                break

        # Success means the checkout/event are durable. Redis cleanup failure
        # cannot undo that outcome; the publisher and next cart operation retry it.
        try:
            self.cleanup(user_id)
        except Exception:
            logger.exception("Checkout is committed; cart cleanup will retry for %s", user_id)
        return response
