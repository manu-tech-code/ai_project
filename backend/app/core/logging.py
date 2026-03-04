"""
Structured logging configuration for the ALM Backend.

- Production (ALM_ENV != development): JSON formatter for log aggregation.
- Development: Human-readable console formatter with colour-friendly output.

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("Job started", extra={"job_id": str(job_id)})
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings


class _JsonFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Each record includes: time (ISO8601 UTC), level, name, message, and any
    extra fields attached via ``logger.info(..., extra={...})``.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        log_entry: dict[str, Any] = {
            "time": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        # Include exception info if present.
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Carry through any extra fields the caller attached.
        # Skip standard LogRecord attributes to avoid noise.
        _std_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "message",
            "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in _std_attrs:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


class _ConsoleFormatter(logging.Formatter):
    """
    Human-readable formatter for local development.

    Format: LEVEL     name:lineno  message  [extra_fields]
    """

    _LEVEL_COLOURS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = self._LEVEL_COLOURS.get(record.levelname, "")
        reset = self._RESET

        timestamp = datetime.now(UTC).strftime("%H:%M:%S")
        level = f"{colour}{record.levelname:<8}{reset}"
        location = f"{record.name}:{record.lineno}"
        message = record.getMessage()

        line = f"{timestamp} {level} {location}  {message}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


def configure_logging() -> None:
    """
    Configure the root logger and uvicorn access/error loggers.

    Call once at application startup (inside the lifespan context manager).
    Subsequent calls are idempotent — handlers are only added if not present.
    """
    level_name = settings.LOG_LEVEL.upper()
    level = getattr(logging, level_name, logging.INFO)

    is_dev = settings.is_development()
    formatter: logging.Formatter = (
        _ConsoleFormatter() if is_dev else _JsonFormatter()
    )

    # Configure root logger.
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Align uvicorn loggers to the same formatter/level.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(uvicorn_logger_name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # Quiet noisy SQLAlchemy engine logs unless in debug mode.
    if not settings.debug:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Suppress aio_pika connection noise at INFO level.
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.

    configure_logging() should be called once at startup before using loggers.
    """
    return logging.getLogger(name)
