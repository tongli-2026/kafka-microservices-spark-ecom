"""Publish the event saved with a checkout; recover unfinished Redis cleanup."""

import json
import logging
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select

from models import Checkout

logger = logging.getLogger(__name__)


class CheckoutPublisher:
    def __init__(self, session_factory, producer, checkout_service, poll_interval=2, lease_seconds=60):
        self.session_factory = session_factory
        self.producer = producer
        self.checkout_service = checkout_service
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self._stop = threading.Event()
        self._thread = None

    def _claim(self):
        with self.session_factory.begin() as db:
            row = db.query(Checkout).filter(
                Checkout.published.is_(False),
                or_(Checkout.claimed_until.is_(None), Checkout.claimed_until <= func.now()),
            ).order_by(Checkout.created_at).with_for_update(skip_locked=True).first()
            if row is None:
                return None
            token = str(uuid4())
            row.claim_token = token
            row.claimed_until = db.execute(select(func.now())).scalar_one() + timedelta(seconds=self.lease_seconds)
            row.attempts += 1
            return row.checkout_id, token, row.event_data

    def publish_once(self):
        claimed = self._claim()
        if claimed is None:
            return False
        checkout_id, token, event_data = claimed
        try:
            self.producer.publish("cart.checkout_initiated", json.loads(event_data))
            with self.session_factory.begin() as db:
                db.query(Checkout).filter_by(checkout_id=checkout_id, claim_token=token, published=False).update({
                    Checkout.published: True, Checkout.published_at: func.now(),
                    Checkout.claim_token: None, Checkout.claimed_until: None, Checkout.last_error: None,
                }, synchronize_session=False)
        except Exception as error:
            logger.exception("Checkout publication failed for %s", checkout_id)
            with self.session_factory.begin() as db:
                now = db.execute(select(func.now())).scalar_one()
                db.query(Checkout).filter_by(checkout_id=checkout_id, claim_token=token, published=False).update({
                    Checkout.claim_token: None,
                    Checkout.claimed_until: now + timedelta(seconds=self.poll_interval) if self.poll_interval else None,
                    Checkout.last_error: str(error)[:4000],
                }, synchronize_session=False)
        return True

    def cleanup_once(self):
        with self.session_factory() as db:
            row = db.query(Checkout.user_id).filter_by(cart_cleared=False).order_by(Checkout.created_at).first()
        if row is not None:
            self.checkout_service.cleanup(row.user_id)

    def _run(self):
        while not self._stop.is_set():
            try:
                self.publish_once()
            except Exception:
                logger.exception("Checkout outbox polling failed")
            try:
                self.cleanup_once()
            except Exception:
                logger.exception("Checkout cart cleanup will retry")
            self._stop.wait(self.poll_interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="cart-checkout-outbox", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=40)
