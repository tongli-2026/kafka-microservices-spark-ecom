"""
notification-service/main.py - Email Notification Microservice

PURPOSE:
    Sends email notifications to users and administrators based on
    e-commerce events. Integrates with Mailpit (SMTP server).

NOTIFICATION TYPES:
    - Order confirmations (to users)
    - Order fulfillment/shipment with tracking numbers (to users)
    - Order cancellations (to users)
    - Payment receipts (to users)
    - Low stock alerts (to admins)
    - Out of stock alerts (to admins)
    - Fraud alerts (to admins)

RESPONSIBILITIES:
    - Listen to various Kafka events
    - Generate appropriate email content
    - Send emails via SMTP (Mailpit)
    - Log all notification attempts
    - Handle email delivery failures

API ENDPOINTS:
    GET /health - Health check

KAFKA EVENTS CONSUMED:
    - order.confirmed: Send order confirmation email
    - order.fulfilled: Send shipment email with tracking number
    - order.cancelled: Send cancellation email
    - payment.processed: Send payment receipt
    - inventory.low: Alert admins about low stock
    - inventory.depleted: Alert admins about depleted stock

EMAIL SERVER:
    - Mailpit SMTP server (development/testing)
    - Host: mailhog (Docker container)
    - Port: 1025
    - Web UI: http://localhost:8025

EMAIL TEMPLATES:
    - Order confirmed: Order ID, items, total, delivery estimate
    - Order cancelled: Order ID, reason, refund info
    - Payment receipt: Payment ID, amount, method
    - Inventory alerts: Product ID, name, current stock level

USAGE:
    Runs on port 8005 in Docker container
    Check sent emails: http://localhost:8025 (Mailpit UI)
"""

import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI  # Web framework
from pydantic_settings import BaseSettings  # Configuration management

# Add shared library to path for common utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Import shared Kafka and event utilities
from kafka_client import BaseKafkaConsumer  # Kafka message consumer
from logging_config import setup_logging  # Centralized logging
from topic_initializer import create_topics  # Kafka topic creation

# Setup logging
setup_logging("notification-service")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    mailhog_host: str = os.getenv("MAILHOG_HOST", "localhost")
    mailhog_port: int = int(os.getenv("MAILHOG_PORT", "1025"))
    admin_email: str = os.getenv("ADMIN_EMAIL", "admin@kafka-ecom.local")
    notification_service_port: int = int(os.getenv("NOTIFICATION_SERVICE_PORT", "8005"))


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle."""
    logger.info("Starting Notification Service...")

    # Initialize Kafka topics
    try:
        create_topics(settings.kafka_bootstrap_servers)
        logger.info("Kafka topics initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka topics: {e}")
        raise

    # Start consumer thread for notification events
    def notification_consumer():
        """Consume notification-related Kafka events."""
        from email_sender import EmailSender

        consumer = BaseKafkaConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="notification-service-group",
            topics=["order.confirmed", "order.fulfilled", "order.cancelled", "inventory.depleted", "payment.failed", "inventory.low"],
        )

        email_sender = EmailSender(settings.mailhog_host, settings.mailhog_port)

        def handle_event(event):
            """Handle incoming event."""
            if event.event_type == "order.confirmed":
                # Send order confirmation email
                subject = f"Order Confirmed #{event.order_id}"
                body = f"""
Dear Customer,

Your order has been confirmed!

Order ID: {event.order_id}
User ID: {event.user_id}

Thank you for your purchase!

Best regards,
Kafka E-Commerce Team
"""
                email_sender.send_email(f"{event.user_id}@example.com", subject, body)

            elif event.event_type == "payment.failed":
                # Send payment failure email
                subject = f"Payment Failed for Order #{event.order_id}"
                body = f"""
Dear Customer,

Unfortunately, your payment for order {event.order_id} failed.

Reason: {event.reason}

Please try again or contact our support team.

Best regards,
Kafka E-Commerce Team
"""
                email_sender.send_email(f"{event.user_id}@example.com", subject, body)

            elif event.event_type == "order.fulfilled":
                # Send order fulfillment/shipment email with tracking number
                subject = f"Your Order is On the Way! Order #{event.order_id}"
                tracking_number = getattr(event, 'tracking_number', 'N/A')
                body = f"""
Dear Customer,

Great news! Your order has been shipped and is on the way to you!

Order ID: {event.order_id}
Tracking Number: {tracking_number}
Estimated Delivery: 3-5 business days

You can track your package using the tracking number above.

Thank you for shopping with us!

Best regards,
Kafka E-Commerce Team
"""
                email_sender.send_email(f"{event.user_id}@example.com", subject, body)

            elif event.event_type == "order.cancelled":
                # Send order cancellation email
                subject = f"Order Cancelled #{event.order_id}"
                reason = getattr(event, 'reason', 'Unknown reason')
                body = f"""
Dear Customer,

Your order has been cancelled.

Order ID: {event.order_id}
Reason: {reason}

If you have any questions, please contact our support team.

Best regards,
Kafka E-Commerce Team
"""
                email_sender.send_email(f"{event.user_id}@example.com", subject, body)

            elif event.event_type == "inventory.depleted":
                # Send out-of-stock alert to admin
                subject = f"Out of Stock Alert: Product #{event.product_id}"
                product_id = getattr(event, 'product_id', 'Unknown')
                body = f"""
ADMIN ALERT - OUT OF STOCK

Product ID: {product_id}
Status: Depleted or Insufficient stock

Orders may have been cancelled due to unavailability.
Please restock or re-evaluate this product immediately.

Kafka E-Commerce Team
"""
                email_sender.send_email(settings.admin_email, subject, body)

            elif event.event_type == "inventory.low":
                # Send low stock alert to admin
                subject = f"Low Stock Alert: Product #{event.product_id}"
                body = f"""
ADMIN ALERT

Product ID: {event.product_id}
Current Stock: {event.current_stock}
Threshold: {event.threshold}

Please restock or re-evaluate this product.

Kafka E-Commerce Team
"""
                email_sender.send_email(settings.admin_email, subject, body)

        try:
            consumer.consume(handle_event)
        except Exception as e:
            logger.error(f"Error in notification consumer: {e}")

    consumer_thread = threading.Thread(target=notification_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Notification consumer thread started")

    yield

    logger.info("Shutting down Notification Service...")


app = FastAPI(title="Notification Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "notification-service",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.notification_service_port)
