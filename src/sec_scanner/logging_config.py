"""
Structured logging configuration with request ID support.
"""

import json
import logging
import os
from contextvars import ContextVar
from typing import Any

# Context variable for request ID (thread-safe for async)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """Get current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str | None) -> None:
    """Set request ID in context."""
    request_id_var.set(request_id)


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging.
    Includes request_id if available in context.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request ID if available
        req_id = get_request_id()
        if req_id:
            log_data["request_id"] = req_id

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from record
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        # Add any custom attributes (excluding standard logging attributes)
        exclude_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "thread",
            "threadName",
            "exc_info",
            "exc_text",
            "stack_info",
        }
        for key, value in record.__dict__.items():
            if key not in exclude_attrs and not key.startswith("_"):
                log_data[key] = value

        return json.dumps(log_data, ensure_ascii=False)


def setup_structured_logging(use_json: bool = True) -> None:
    """
    Setup structured logging.

    Args:
        use_json: If True, use JSON format. If False, use standard format.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler()
    handler.setLevel(level)

    # Set formatter
    if use_json:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    handler.setFormatter(formatter)

    root_logger.addHandler(handler)

    # Prevent propagation to avoid duplicate logs
    root_logger.propagate = False
