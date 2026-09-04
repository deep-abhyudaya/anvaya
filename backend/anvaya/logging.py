"""Structured logging configuration for ANVAYA."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "info", *, human: bool = False) -> None:
    """Configure structlog for structured output.

    Server logs are emitted as JSON by default. Set ``human=True`` for CLI
    output so events are rendered in a readable console format.
    """
    _level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=_level,
    )

    sql_level = logging.DEBUG if _level == logging.DEBUG else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sql_level)
    logging.getLogger("sqlalchemy.pool").setLevel(sql_level)

    if human or level == "debug":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_level),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "anvaya") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
