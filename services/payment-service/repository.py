import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from models import Payment

logger = logging.getLogger(__name__)


class PaymentRepository:
    """Repository for payment operations."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def create_payment(self, order_id: str, user_id: str, amount: float, currency: str, method: str, status: str, reason: str = None) -> Payment:
        """Create a payment record."""
        payment_id = f"PAY-{uuid4().hex[:12].upper()}"
        payment = Payment(
            payment_id=payment_id,
            order_id=order_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            method=method,
            status=status,
            reason=reason,
        )
        self.db.add(payment)
        self.db.flush()
        logger.info(f"Created payment {payment_id} for order {order_id} with status {status}")
        return payment

    def get_payment(self, payment_id: str) -> Payment:
        """Get payment by ID."""
        return self.db.query(Payment).filter(Payment.payment_id == payment_id).first()

    def get_payment_by_order(self, order_id: str) -> Payment:
        """Get payment by order ID."""
        return self.db.query(Payment).filter(Payment.order_id == order_id).first()
