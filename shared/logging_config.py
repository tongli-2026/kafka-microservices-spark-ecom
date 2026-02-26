"""
logging_config.py - Centralized JSON Logging Configuration

PURPOSE:
    Provides structured JSON logging for all microservices with timezone-aware timestamps,
    correlation tracking, and service-specific context injection.

KEY FEATURES:
    - JSON Format: All logs are formatted as JSON for easy parsing and aggregation
    - Timezone Aware: All timestamps use Los Angeles timezone (America/Los_Angeles) via ZoneInfo
    - Correlation Tracking: Supports correlation_id for distributed tracing across services
    - Service Context: Automatically adds service_name to all log entries
    - Event Tracking: Optional event_type field for event-driven diagnostics
    - Exception Handling: Full stack traces included in log entries

JSON LOG FIELDS:
    - timestamp: ISO 8601 format with Los Angeles timezone (e.g., "2026-02-23T22:48:51.001014-08:00")
    - level: Log level (INFO, ERROR, WARNING, DEBUG, CRITICAL)
    - logger: Module/class name where log originated (e.g., "__main__", "cart_repository")
    - message: The actual log message
    - service_name: Name of the microservice (injected automatically)
    - correlation_id: Optional tracing ID across service boundaries
    - event_type: Optional Kafka event type being processed
    - exception: Full stack trace (only for ERROR/CRITICAL logs)

USAGE EXAMPLES:

    1. Initialize logging in service startup:
        from logging_config import setup_logging
        setup_logging("cart-service", level="INFO")

    2. Log with correlation context:
        import logging
        logger = logging.getLogger(__name__)
        
        # Simple log (service_name added automatically)
        logger.info("Cart item added successfully")
        
        # Log with correlation_id for distributed tracing
        record = logging.LogRecord(
            name=__name__,
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Processing event",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "9a63a606-fbef-4a4b-a5a4-ef1f127bc304"
        record.event_type = "cart.item_added"
        logger.handle(record)

EXAMPLE JSON OUTPUT:
    {
        "timestamp": "2026-02-23T22:48:51.001014-08:00",
        "level": "INFO",
        "logger": "cart_repository",
        "message": "Added item laptop to cart for user user123",
        "service_name": "cart-service"
    }

    {
        "timestamp": "2026-02-23T22:54:47.583146-08:00",
        "level": "INFO",
        "logger": "kafka_client",
        "message": "Published event to cart.item_added",
        "service_name": "cart-service",
        "correlation_id": "9a63a606-fbef-4a4b-a5a4-ef1f127bc304",
        "event_type": "cart.item_added"
    }

DEPENDENCIES:
    - Python 3.9+: For ZoneInfo timezone support (replaces deprecated pytz)
    - json: Standard library for JSON serialization
    - logging: Standard library for logging framework
    - zoneinfo: Standard library for IANA timezone database

INTEGRATION POINTS:
    - Used by: All microservices (cart-service, order-service, payment-service, etc.)
    - Called at: Service startup in main.py lifespan context
    - Timezone: Synchronized with docker-compose.yml TZ=America/Los_Angeles

DESIGN NOTES:
    - JsonFormatter: Custom Formatter extending logging.Formatter for JSON output
    - ServiceFilter: Logging.Filter that injects service_name into all records
    - Centralized: Single configuration file imported by all services ensures consistency
    - Performance: JSON serialization happens per log entry (minimal overhead)
"""

import json
import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs JSON logs with correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(ZoneInfo("America/Los_Angeles")).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation_id if available in record
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id
        if hasattr(record, "service_name"):
            log_data["service_name"] = record.service_name
        if hasattr(record, "event_type"):
            log_data["event_type"] = record.event_type

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(service_name: str, level: str = "INFO") -> None:
    """Setup JSON logging for a service."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(handler)

    # Add service name to all logs
    class ServiceFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.service_name = service_name
            return True

    logger.addFilter(ServiceFilter())
