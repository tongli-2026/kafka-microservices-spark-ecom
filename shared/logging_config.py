import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs JSON logs with correlation context."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
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
