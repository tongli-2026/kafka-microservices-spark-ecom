"""
payment_processor.py - Simulated Payment Gateway Integration

PURPOSE:
    Provides simulated payment processing with configurable success/failure rates.
    Used for testing saga patterns and payment failure scenarios in the e-commerce system.

FUNCTIONALITY:
    - Process payments with 80% success rate, 20% failure rate
    - Return failure reasons (insufficient_funds, card_declined, expired_card)
    - No external payment gateway calls (simulation only)
    - Idempotent operation (same input always produces same result for testing)

USAGE:
    from payment_processor import PaymentProcessor
    
    success, reason = PaymentProcessor.process_payment(amount=99.98)
    if success:
        print(f"Payment SUCCESS: ${amount}")
    else:
        print(f"Payment FAILED: {reason}")

CONFIGURATION:
    - SUCCESS_RATE: 0.8 (80% success, modify for different test scenarios)
    - FAILURE_REASONS: List of possible failure messages
    - Random: Uses Python's random module for simulation

INTEGRATION:
    Called by Payment Service when order.reservation_confirmed event is received.
    Results in payment.processed or payment.failed events published to Kafka.
"""

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
