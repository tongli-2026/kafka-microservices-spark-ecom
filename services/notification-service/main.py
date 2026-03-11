"""
notification-service/main.py - Email Notification Microservice

PURPOSE:
    Sends email notifications to users and administrators based on
    e-commerce events. Integrates with Mailhog (SMTP server).

NOTIFICATION TYPES:
    - Order confirmations (to users)
    - Order fulfillment/shipment with tracking numbers (to users)
    - Order cancellations with reason (to users)
      * Payment failed cancellation
      * Out of stock cancellation
    - Low stock alerts (to admins)
    - Out of stock alerts (to admins)

RESPONSIBILITIES:
    - Listen to various Kafka events
    - Generate appropriate email content
    - Send emails via SMTP (Mailhog)
    - Log all notification attempts
    - Handle email delivery failures

API ENDPOINTS:
    GET /health - Health check

KAFKA EVENTS CONSUMED:
    - order.confirmed: Send order confirmation email to user
    - order.fulfilled: Send shipment notification with tracking number to user
    - order.cancelled: Send cancellation notification to user (with specific reason)
    - inventory.depleted: Send out-of-stock alert to admins
    - inventory.low: Send low stock warning to admins

EMAIL SERVER:
    - Mailhog SMTP server (development/testing)
    - Host: mailhog (Docker container)
    - Port: 1025
    - Web UI: http://localhost:8025

EMAIL TEMPLATES:
    - Order confirmed: Order ID, user ID, confirmation message
    - Order fulfilled: Order ID, tracking number, estimated delivery date
    - Order cancelled (payment failed): Order ID, clear explanation that user not charged, retry option
    - Order cancelled (out of stock): Order ID, clear explanation that user not charged, suggestion to browse
    - Order cancelled (generic): Order ID, cancellation reason
    - Inventory low: Product ID, current stock level, threshold
    - Inventory depleted: Product ID, out-of-stock status

USAGE:
    Runs on port 8005 in Docker container
    Check sent emails: http://localhost:8025 (Mailhog UI)
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
from kafka_client import BaseKafkaConsumer, BaseKafkaProducer  # Kafka message consumer and producer
from logging_config import setup_logging  # Centralized logging
from topic_initializer import create_topics  # Kafka topic creation
from events import NotificationSendEvent  # Event definition for publishing notification.send

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
            topics=["order.confirmed", "order.fulfilled", "order.cancelled", "inventory.low", "inventory.depleted"],
        )

        # Initialize Kafka producer for publishing notification.send events (email request tracking)
        producer = BaseKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)

        email_sender = EmailSender(settings.mailhog_host, settings.mailhog_port)

        def handle_event(event):
            """Handle incoming events."""
            logger.info(f"Processing event: type={event.event_type}, order_id={getattr(event, 'order_id', 'N/A')}, event_id={event.event_id}")
            
            email_sent = False
            recipient_email = None
            
            if event.event_type == "order.confirmed":
                # Send order confirmation email to user
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
                recipient_email = f"{event.user_id}@example.com"
                email_sent = email_sender.send_email(recipient_email, subject, body)

            elif event.event_type == "order.fulfilled":
                # Send order fulfillment/shipment email with tracking number to user
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
                recipient_email = f"{event.user_id}@example.com"
                email_sent = email_sender.send_email(recipient_email, subject, body)

            elif event.event_type == "order.cancelled":
                # Send order cancellation email to user with clear explanation based on cancellation source
                reason = getattr(event, 'reason', 'Unknown reason')
                cancellation_source = getattr(event, 'cancellation_source', 'unknown')
                
                if cancellation_source == "payment_failed":
                    # Payment processing failed - order cancelled WITHOUT charging customer
                    subject = f"Order Cancelled - Payment Failed #{event.order_id}"
                    body = f"""
Dear Customer,

Your payment for order {event.order_id} could not be processed.

Reason: {reason}

Your order has been cancelled and you will NOT be charged.

If you would like to retry your purchase, please visit our store.

Best regards,
Kafka E-Commerce Team
"""
                elif cancellation_source == "inventory_depleted":
                    # Item went out of stock - order cancelled WITHOUT charging customer
                    subject = f"Order Cancelled - Out of Stock #{event.order_id}"
                    body = f"""
Dear Customer,

Unfortunately, the items in your order are no longer available.

Reason: {reason}

Your order has been cancelled and you will NOT be charged.

We apologize for the inconvenience. Please visit our store to find similar items.

Best regards,
Kafka E-Commerce Team
"""
                else:
                    # Generic cancellation
                    subject = f"Order Cancelled #{event.order_id}"
                    body = f"""
Dear Customer,

Your order has been cancelled.

Order ID: {event.order_id}
Reason: {reason}

If you have any questions, please contact our support team.

Best regards,
Kafka E-Commerce Team
"""
                
                logger.info(f"Sending order cancellation email for order_id={event.order_id}, user_id={event.user_id}, reason={cancellation_source}")
                recipient_email = f"{event.user_id}@example.com"
                email_sent = email_sender.send_email(recipient_email, subject, body)
                logger.info(f"Successfully sent order cancellation email for order_id={event.order_id}")

            elif event.event_type == "inventory.low":
                # Send low stock alert to admin
                subject = f"Low Stock Alert: Product #{event.product_id}"
                body = f"""
ADMIN ALERT - LOW STOCK

Product ID: {event.product_id}
Current Stock: {event.current_stock}
Threshold: {event.threshold}

Please restock or re-evaluate this product.

Kafka E-Commerce Team
"""
                recipient_email = settings.admin_email
                email_sent = email_sender.send_email(recipient_email, subject, body)

            elif event.event_type == "inventory.depleted":
                # Send out-of-stock or insufficient stock alert to admin
                subject = f"Out of Stock or Insufficient Stock Alert: Product #{event.product_id}"
                product_id = getattr(event, 'product_id', 'Unknown')
                body = f"""
ADMIN ALERT - OUT OF STOCK or INSUFFICIENT STOCK

Product ID: {product_id}
Status: Depleted or Insufficient stock

Orders may have been cancelled due to unavailability.
Please restock or re-evaluate this product immediately.

Kafka E-Commerce Team
"""
                recipient_email = settings.admin_email
                email_sent = email_sender.send_email(recipient_email, subject, body)

            # Publish notification.send event to Kafka to track all notification processing
            # Always publish for every event received, regardless of success/failure
            # This provides visibility into when the notification service processes events
            try:
                # Ensure we have a recipient email, fallback to unknown if not set
                final_recipient = recipient_email if recipient_email else "unknown@example.com"
                
                notification_event = NotificationSendEvent(
                    event_id=event.event_id,
                    correlation_id=event.correlation_id,
                    user_id=getattr(event, 'user_id', 'unknown'),
                    recipient_email=final_recipient,
                    notification_type=event.event_type,
                    data={"email_sent": email_sent, "success": email_sent, "processed": True}
                )
                producer.send("notification.send", notification_event)
                logger.info(f"Published notification.send event: type={event.event_type}, recipient={final_recipient}, success={email_sent}")
            except Exception as e:
                logger.warning(f"Failed to publish notification.send event: {e}")

        # Start consuming events
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


# API endpoint for health check
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
