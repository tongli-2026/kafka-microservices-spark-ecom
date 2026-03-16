"""
payment-service/main.py - Payment Processing Microservice

PURPOSE:
    Processes payment transactions for e-commerce orders with simulated
    payment gateway integration. Implements Production-style inventory-first flow
    where payment is only processed AFTER inventory is successfully reserved.

PAYMENT FLOW (Inventory-First Pattern):
    1. Order Service creates order and reserves inventory with Inventory Service
    2. Inventory Service confirms reservation → publishes inventory.reserved
    3. Payment Service consumes order.reservation_confirmed event
    4. Payment Service processes payment (80% success, 20% failure)
    5. Publish payment.processed (success) or payment.failed (failure)
    6. Order Service proceeds to fulfillment or cancels based on payment result

KEY ADVANTAGE:
    Payment only charged after inventory is guaranteed. Prevents:
    - Customers charged for out-of-stock items (worst UX)
    - Refunds needed for failed orders
    - Inventory overselling

RESPONSIBILITIES:
    - Process payment transactions after inventory reservation confirmed
    - Simulate payment gateway (with realistic success/failure rates)
    - Record payment transaction history with full audit trail
    - Publish payment result events for saga completion
    - Provide payment history retrieval for customer orders

SIMULATION PARAMETERS:
    - Success Rate: 80% (realistic for payment processors)
    - Failure Rate: 20% (for testing saga compensation patterns)
    - Failure Reasons: insufficient_funds, card_declined, expired_card
    - Idempotency: Prevents duplicate payments for same order

API ENDPOINTS:
    GET /payments/{payment_id} - Retrieve payment details
    GET /health - Health check endpoint

KAFKA EVENTS:
    CONSUMED:
        - order.reservation_confirmed: Order created AND inventory reserved
                                        → Trigger payment processing
    
    PUBLISHED:
        - payment.processed: Payment succeeded (status: SUCCESS)
        - payment.failed: Payment failed (status: FAILED with reason)

DATABASE:
    PostgreSQL table: payments
    Columns:
        - id: Auto-increment primary key
        - payment_id: Unique identifier (PAY-XXXXX)
        - order_id: Associated order identifier
        - user_id: Customer identifier
        - amount: Transaction amount (USD)
        - currency: Currency code (USD)
        - method: Payment method (card, etc.)
        - status: SUCCESS or FAILED
        - reason: Failure reason (if status=FAILED)
        - created_at: Timestamp
        - updated_at: Timestamp

FLOW COMPARISON:
    ❌ WRONG (Stripe-style): Cart → Order → Payment → Inventory
       Risk: Charge first, check stock later → refunds needed

    ✅ CORRECT (Production-style): Cart → Order → Inventory → Payment
       Benefit: Guarantee stock before charging customer

USAGE:
    Runs on port 8003 in Docker container
    Depends on: Kafka, PostgreSQL, Order Service
    Access: http://localhost:8003/payments/{payment_id}
"""

import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI  # Web framework
from pydantic_settings import BaseSettings  # Configuration management
from sqlalchemy import create_engine  # Database ORM
from sqlalchemy.orm import sessionmaker  # Database session management
from fastapi.responses import Response  # For metrics endpoint

# Import prometheus metrics
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from shared.metrics import (
    add_metrics_middleware,
    track_operation,
    payment_processing_total,
    payment_processing_duration_seconds,
    idempotency_cache_hits_total,
    idempotency_cache_misses_total,
    track_payment_status,
    track_cache_hit,
    track_kafka_message,
)

# Import local schemas for input/output validation
from schemas import HealthResponse, PaymentSchema, PaymentListResponse  # Pydantic models
from fastapi import HTTPException  # HTTP exception handling

# Add shared library to path for common utilities
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Import shared Kafka and event utilities
from kafka_client import BaseKafkaConsumer, BaseKafkaProducer  # Kafka clients
from logging_config import setup_logging  # Centralized logging
from topic_initializer import create_topics  # Kafka topic creation
from events import PaymentProcessedEvent, PaymentFailedEvent  # Event schemas

# Setup logging
setup_logging("payment-service")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "kafka_ecom")
    payment_service_port: int = int(os.getenv("PAYMENT_SERVICE_PORT", "8003"))


settings = Settings()

# Database setup
DATABASE_URL = (
    f"postgresql://{settings.postgres_user}:{settings.postgres_password}@"
    f"{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Global instances
producer: BaseKafkaProducer = None


def init_db():
    """Initialize database tables."""
    from models import Base

    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle."""
    global producer

    logger.info("Starting Payment Service...")

    # Initialize database
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

    # Initialize Kafka topics
    try:
        create_topics(settings.kafka_bootstrap_servers)
        logger.info("Kafka topics initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka topics: {e}")
        raise

    # Initialize Kafka producer
    try:
        producer = BaseKafkaProducer(settings.kafka_bootstrap_servers, client_id="payment-producer")
        logger.info("Kafka producer initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Kafka producer: {e}")
        raise

    # Start consumer thread for order.reservation_confirmed events
    def payment_consumer():
        """Consume order.reservation_confirmed events and process payments."""
        from payment_processor import PaymentProcessor
        from repository import PaymentRepository

        consumer = BaseKafkaConsumer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="payment-service-group",
            topics=["order.reservation_confirmed"],
        )

        def handle_order_reservation_confirmed(event):
            """Handle order.reservation_confirmed event (Production-style: process payment only after inventory is reserved)."""
            logger.info(
                f"Processing payment for order {event.order_id} (inventory reserved)",
                extra={"event_type": event.event_type, "correlation_id": event.correlation_id},
            )

            db = SessionLocal()
            repo = PaymentRepository(db)

            # FIX: Check for existing payment (idempotency via unique constraint on order_id)
            # If payment already exists for this order, skip processing
            existing_payment = repo.get_payment_by_order(event.order_id)
            if existing_payment:
                logger.info(f"Payment already processed for order {event.order_id} - skipping duplicate")
                # Track idempotency cache hit
                track_cache_hit("idempotency", "payment-service", hit=True)
                db.close()
                return

            # Track idempotency cache miss
            track_cache_hit("idempotency", "payment-service", hit=False)

            # Process payment
            success, reason = PaymentProcessor.process_payment(event.total_amount)

            if success:
                # Create success payment record
                payment = repo.create_payment(
                    order_id=event.order_id,
                    user_id=event.user_id,
                    amount=event.total_amount,
                    currency="USD",
                    method="card",
                    status="SUCCESS",
                )

                # Track payment success
                track_payment_status("payment-service", "success")

                # Publish payment.processed event
                payment_event = PaymentProcessedEvent(
                    payment_id=payment.payment_id,
                    order_id=event.order_id,
                    user_id=event.user_id,
                    amount=event.total_amount,
                    currency="USD",
                    method="card",
                    correlation_id=event.correlation_id,
                )
                producer.publish("payment.processed", payment_event)
                # Track Kafka message publication
                track_kafka_message("payment-service", "payment.processed", published=True, success=True)

            else:
                # Create failed payment record
                payment = repo.create_payment(
                    order_id=event.order_id,
                    user_id=event.user_id,
                    amount=event.total_amount,
                    currency="USD",
                    method="card",
                    status="FAILED",
                    reason=reason,
                )

                # Track payment failure
                track_payment_status("payment-service", "failed")

                # Publish payment.failed event
                payment_event = PaymentFailedEvent(
                    order_id=event.order_id,
                    user_id=event.user_id,
                    reason=reason,
                    correlation_id=event.correlation_id,
                )
                producer.publish("payment.failed", payment_event)
                # Track Kafka message publication
                track_kafka_message("payment-service", "payment.failed", published=True, success=True)

            db.commit()
            db.close()

        try:
            consumer.consume(handle_order_reservation_confirmed)
        except Exception as e:
            logger.error(f"Error in payment consumer: {e}")

    # Start consumer thread
    consumer_thread = threading.Thread(target=payment_consumer, daemon=True)
    consumer_thread.start()
    logger.info("Payment consumer thread started")

    yield

    logger.info("Shutting down Payment Service...")
    if producer:
        producer.flush()


app = FastAPI(title="Payment Service", version="1.0.0", lifespan=lifespan)

# Add metrics middleware for automatic request tracking
add_metrics_middleware(app, "payment-service")

# API Endpoints
# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        service="payment-service",
        version="1.0.0",
    )

# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

# Retrieve payment details endpoint
@app.get("/payments/{payment_id}", response_model=PaymentSchema)
async def get_payment(payment_id: str) -> PaymentSchema:
    """Get payment details."""
    from repository import PaymentRepository

    try:
        db = SessionLocal()
        repo = PaymentRepository(db)
        payment = repo.get_payment(payment_id)

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        return PaymentSchema(
            payment_id=payment.payment_id,
            order_id=payment.order_id,
            user_id=payment.user_id,
            amount=payment.amount,
            currency=payment.currency,
            method=payment.method,
            status=payment.status,
            reason=payment.reason,
            created_at=payment.created_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting payment: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.payment_service_port)
