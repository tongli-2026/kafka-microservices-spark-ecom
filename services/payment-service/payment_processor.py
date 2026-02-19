import logging
import random
from uuid import uuid4

logger = logging.getLogger(__name__)


class PaymentProcessor:
    """Simulated payment processor with 80% success rate."""

    SUCCESS_RATE = 0.8
    FAILURE_REASONS = ["insufficient_funds", "card_declined", "expired_card"]

    @staticmethod
    def process_payment(amount: float) -> tuple:
        """
        Process payment with 80% success rate.
        Returns (success: bool, reason: str or None)
        """
        if random.random() > PaymentProcessor.SUCCESS_RATE:
            reason = random.choice(PaymentProcessor.FAILURE_REASONS)
            logger.info(f"Payment FAILED: {reason}")
            return False, reason
        else:
            logger.info(f"Payment SUCCESS: ${amount}")
            return True, None
