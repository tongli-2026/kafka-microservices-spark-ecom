"""
email_sender.py - Email Delivery Module for Notification Service

PURPOSE:
    Sends transactional emails via Mailpit SMTP server. Integrates with
    Notification Service to deliver order confirmations, payment updates,
    and shipment notifications to customers.

FUNCTIONALITY:
    - Connect to Mailpit SMTP (development/testing email gateway)
    - Format and send plain-text emails with subject and body
    - Handle SMTP connection errors gracefully with logging
    - No authentication required (Mailpit is open for testing)
    - Return success/failure status for retry logic

USAGE:
    sender = EmailSender(mailpit_host="mailpit", mailpit_port=1025)
    success = sender.send_email(
        to_email="customer@example.com",
        subject="Order Confirmation #ORD-12345",
        body="Thank you for your order..."
    )

CONFIGURATION:
    - MAILPIT_HOST: Default "mailpit" (Docker service name)
    - MAILPIT_PORT: Default 1025 (SMTP port)
    - FROM_EMAIL: Hardcoded as "noreply@kafka-ecom.local"

INTEGRATION:
    Called by notification_consumer() in main.py when processing:
    - order.confirmed → Order confirmation email
    - order.fulfilled → Shipment notification email
    - order.cancelled → Order cancellation email
    - inventory.depleted → Out-of-stock alert email
    - inventory.low → Low stock warning email
    - payment.failed → Payment failure notification email
    
    Mailpit provides web UI (http://mailpit:8025) for testing/verification.

ERROR HANDLING:
    - Logs all SMTP errors without raising exceptions
    - Returns False on failure, True on success
    - Allows notification service to continue processing other events
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class EmailSender:
    """Email sender using Mailpit SMTP."""

    def __init__(self, mailpit_host: str, mailpit_port: int):
        """Initialize email sender."""
        self.mailpit_host = mailpit_host
        self.mailpit_port = mailpit_port

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send email via Mailpit SMTP."""
        try:
            # Create email message
            msg = MIMEMultipart()
            msg["From"] = "noreply@kafka-ecom.local"
            msg["To"] = to_email
            msg["Subject"] = subject

            msg.attach(MIMEText(body, "plain"))

            # Connect to Mailpit SMTP (no authentication needed)
            with smtplib.SMTP(self.mailpit_host, self.mailpit_port) as server:
                server.send_message(msg)

            logger.info(f"Email sent to {to_email}: {subject}")
            return True

        # Handle SMTP errors gracefully
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {e}")
            return False
