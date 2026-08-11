"""Structured logging.

JSON lines in production so logs are greppable and machine-parseable; a human
console renderer in development. stdlib loggers (uvicorn, sqlalchemy) are
routed through the same processor chain so output is uniform.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from ..config.settings import Settings

# Keys whose values must never reach a log sink, whatever the caller passes.
# Defence in depth: the call sites are also expected not to log these.
_REDACTED_KEYS = frozenset(
    {
        "password",
        "mat_khau",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "secret_key",
        "jpeg",
        "frame",
        "image",
    }
)

_REDACTED = "[redacted]"


def _scrub_sensitive(
    _logger: Any, _name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Replace the value of any sensitive key, at any nesting depth of one."""
    for key in list(event_dict):
        if key.lower() in _REDACTED_KEYS:
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging(settings: Settings) -> None:
    """Install the structlog pipeline and hand stdlib logging over to it."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        _scrub_sensitive,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    # uvicorn installs its own handlers; strip them so lines are not doubled.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Typed accessor so call sites do not repeat the cast."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
