"""
Shared metrics module for all microservices.

Provides:
- Generic request/response metrics via middleware
- Service-specific metric decorators
- Prometheus client setup
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
import logging
import time
from functools import wraps
from typing import Callable, Optional
import asyncio

logger = logging.getLogger(__name__)

# ============================================================================
# SHARED METRICS (ALL SERVICES)
# ============================================================================

# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status'],
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['service', 'endpoint', 'method'],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Error metrics
service_errors_total = Counter(
    'service_errors_total',
    'Total service errors',
    ['service', 'error_type', 'endpoint'],
)

# Database metrics
db_connection_pool_active = Gauge(
    'db_connection_pool_active',
    'Active database connections',
    ['service'],
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query duration in seconds',
    ['service', 'query_type'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

# ============================================================================
# PAYMENT SERVICE SPECIFIC METRICS
# ============================================================================

payment_processing_total = Counter(
    'payment_processing_total',
    'Total payment processing attempts',
    ['service', 'status'],  # status: success, failed, pending
)

payment_processing_duration_seconds = Histogram(
    'payment_processing_duration_seconds',
    'Payment processing duration in seconds',
    ['service'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
)

payment_validation_errors_total = Counter(
    'payment_validation_errors_total',
    'Total payment validation errors',
    ['service', 'error_reason'],  # e.g., invalid_card, insufficient_funds
)

idempotency_cache_hits_total = Counter(
    'idempotency_cache_hits_total',
    'Idempotency cache hits',
    ['service'],
)

idempotency_cache_misses_total = Counter(
    'idempotency_cache_misses_total',
    'Idempotency cache misses',
    ['service'],
)

# ============================================================================
# ORDER SERVICE SPECIFIC METRICS
# ============================================================================

order_processing_total = Counter(
    'order_processing_total',
    'Total orders created',
    ['service', 'status'],  # status: created, confirmed, cancelled
)

saga_steps_total = Counter(
    'saga_orchestration_steps_total',
    'Total saga orchestration steps executed',
    ['service', 'step', 'status'],
    # step: payment, inventory, notification
    # status: success, failed, compensated
)

saga_compensation_total = Counter(
    'saga_compensation_total',
    'Total saga compensation (rollback) events',
    ['service', 'step'],
)

pending_orders_gauge = Gauge(
    'pending_orders_total',
    'Number of pending orders',
    ['service'],
)

processed_events_deduplicated_total = Counter(
    'processed_events_deduplicated_total',
    'Events deduplicated via processed_events table',
    ['service'],
)

outbox_events_pending_gauge = Gauge(
    'outbox_events_pending_total',
    'Number of pending outbox events',
    ['service'],
)

# ============================================================================
# INVENTORY SERVICE SPECIFIC METRICS
# ============================================================================

inventory_reservation_total = Counter(
    'inventory_reservation_total',
    'Total inventory reservations',
    ['service', 'product_id', 'status'],  # status: success, failed
)

inventory_reservation_duration_seconds = Histogram(
    'inventory_reservation_duration_seconds',
    'Inventory reservation duration',
    ['service', 'product_id'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
)

stock_level_gauge = Gauge(
    'inventory_stock_level',
    'Current stock level',
    ['service', 'product_id', 'warehouse'],
)

inventory_allocation_errors_total = Counter(
    'inventory_allocation_errors_total',
    'Inventory allocation errors',
    ['service', 'product_id', 'error_reason'],
)

# ============================================================================
# NOTIFICATION SERVICE SPECIFIC METRICS
# ============================================================================

notification_sent_total = Counter(
    'notification_sent_total',
    'Total notifications sent',
    ['service', 'type', 'status'],  # type: email, sms; status: sent, failed
)

notification_processing_duration_seconds = Histogram(
    'notification_processing_duration_seconds',
    'Notification processing duration',
    ['service', 'type'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0),
)

notification_deduplication_hits_total = Counter(
    'notification_deduplication_hits_total',
    'Notification deduplication cache hits',
    ['service'],
)

# ============================================================================
# CART SERVICE SPECIFIC METRICS
# ============================================================================

cart_operations_total = Counter(
    'cart_operations_total',
    'Total cart operations',
    ['service', 'operation'],  # operation: add_item, remove_item, checkout, view
)

redis_cache_hits_total = Counter(
    'redis_cache_hits_total',
    'Redis cache hits',
    ['service'],
)

redis_cache_misses_total = Counter(
    'redis_cache_misses_total',
    'Redis cache misses',
    ['service'],
)

redis_connection_errors_total = Counter(
    'redis_connection_errors_total',
    'Redis connection errors',
    ['service'],
)

# ============================================================================
# KAFKA METRICS
# ============================================================================

kafka_message_published_total = Counter(
    'kafka_message_published_total',
    'Total Kafka messages published',
    ['service', 'topic', 'status'],  # status: success, failed
)

kafka_message_consumed_total = Counter(
    'kafka_message_consumed_total',
    'Total Kafka messages consumed',
    ['service', 'topic'],
)

kafka_produce_errors_total = Counter(
    'kafka_produce_errors_total',
    'Total Kafka produce errors',
    ['service', 'topic', 'error_type'],
)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def normalize_endpoint(path: str) -> str:
    """
    Normalize endpoint path by removing dynamic parts (IDs, user IDs, etc).
    
    Examples:
        /cart/user_001/items → /cart/{user_id}/items
        /order/12345 → /order/{order_id}
        /payment/txn_abc123/status → /payment/{payment_id}/status
        /products/prod_001 → /products/{product_id}
    
    This prevents explosion of metric cardinality from individual user IDs, order IDs, etc.
    """
    import re
    
    # Replace user IDs like user_001, user_123
    path = re.sub(r'/user_\d+', '/{user_id}', path)
    
    # Replace numeric IDs (order IDs, payment IDs, etc)
    # But preserve path structure: /order/12345 → /order/{id}, not /order
    path = re.sub(r'/(\d+)(?=/|$)', '/{id}', path)
    
    # Replace transaction/reference IDs like txn_abc123, ref_xyz
    path = re.sub(r'/(txn_|ref_|order_|payment_|invoice_)[a-zA-Z0-9_]+', '/{reference_id}', path)
    
    return path


def add_metrics_middleware(app, service_name: str):
    """
    Add metrics middleware to FastAPI app.
    Automatically tracks HTTP request metrics with normalized endpoint paths.
    
    Endpoint paths are normalized to remove user IDs and other dynamic parts
    to prevent metric cardinality explosion. For example:
        /cart/user_001/items → /cart/{user_id}/items
        /order/12345 → /order/{id}
    
    This ensures metrics are aggregated by endpoint type, not individual users.
    
    Usage:
        app = FastAPI()
        add_metrics_middleware(app, "payment-service")
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    
    class MetricsMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            # Skip metrics endpoint itself to avoid recursion
            if request.url.path == "/metrics":
                return await call_next(request)
            
            # Normalize endpoint path to prevent cardinality explosion
            normalized_endpoint = normalize_endpoint(request.url.path)
            
            start_time = time.time()
            try:
                response = await call_next(request)
                duration = time.time() - start_time
                
                # Record metrics with normalized endpoint
                http_requests_total.labels(
                    service=service_name,
                    method=request.method,
                    endpoint=normalized_endpoint,
                    status=response.status_code,
                ).inc()
                
                http_request_duration_seconds.labels(
                    service=service_name,
                    endpoint=normalized_endpoint,
                    method=request.method,
                ).observe(duration)
                
                return response
            except Exception as e:
                duration = time.time() - start_time
                service_errors_total.labels(
                    service=service_name,
                    error_type=type(e).__name__,
                    endpoint=normalized_endpoint,
                ).inc()
                raise
    
    app.add_middleware(MetricsMiddleware)


def track_operation(
    operation_name: str,
    service_name: str,
    duration_metric: Optional[Histogram] = None,
    status_counter: Optional[Counter] = None,
):
    """
    Decorator to track operation timing and status.

    Usage:
        @track_operation(
            operation_name="payment_processing",
            service_name="payment-service",
            duration_metric=payment_processing_duration_seconds,
            status_counter=payment_processing_total,
        )
        async def process_payment(order_id: str, amount: float):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                if status_counter:
                    status_counter.labels(service=service_name, status="success").inc()
                return result
            except Exception as e:
                if status_counter:
                    status_counter.labels(service=service_name, status="failed").inc()
                logger.error(f"Error in {operation_name}: {e}")
                raise
            finally:
                duration = time.time() - start_time
                if duration_metric:
                    duration_metric.labels(service=service_name).observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                if status_counter:
                    status_counter.labels(service=service_name, status="success").inc()
                return result
            except Exception as e:
                if status_counter:
                    status_counter.labels(service=service_name, status="failed").inc()
                logger.error(f"Error in {operation_name}: {e}")
                raise
            finally:
                duration = time.time() - start_time
                if duration_metric:
                    duration_metric.labels(service=service_name).observe(duration)

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# METRICS ENDPOINT
# ============================================================================


def get_metrics_response():
    """
    Return Prometheus metrics in text format.

    Usage in FastAPI:
        from shared.metrics import get_metrics_response
        from fastapi.responses import Response
        
        @app.get("/metrics")
        async def metrics():
            content, content_type = get_metrics_response()
            return Response(content=content, media_type=content_type)
    """
    return (generate_latest(), CONTENT_TYPE_LATEST)
