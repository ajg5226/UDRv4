"""Structured logging configuration for ATLAS."""

import logging
import sys
from typing import Any, Optional

import structlog
from structlog.types import Processor

from atlas.core.config import get_settings


def add_atlas_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add ATLAS-specific context to log events."""
    event_dict["service"] = "atlas"
    event_dict["version"] = "1.0.0"
    return event_dict


def setup_logging(
    level: Optional[str] = None,
    format_type: Optional[str] = None,
) -> None:
    """
    Configure structured logging for ATLAS.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Output format ("json" or "text")
    """
    settings = get_settings()
    
    level = level or settings.logging.level
    format_type = format_type or settings.logging.format

    # Shared processors for all outputs
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        add_atlas_context,
    ]

    if format_type == "json":
        # JSON format for production/cloud
        processors: list[Processor] = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Human-readable format for development
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding temporary log context."""

    def __init__(self, **kwargs: Any) -> None:
        self.context = kwargs
        self._token: Optional[Any] = None

    def __enter__(self) -> "LogContext":
        self._token = structlog.contextvars.bind_contextvars(**self.context)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._token:
            structlog.contextvars.unbind_contextvars(*self.context.keys())


def bind_context(**kwargs: Any) -> None:
    """Bind context variables for subsequent log calls."""
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """Unbind context variables."""
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all context variables."""
    structlog.contextvars.clear_contextvars()
