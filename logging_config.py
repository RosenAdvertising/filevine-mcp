"""Cowork standard structured logging configuration.

Drop into any service-style project. Provides JSON logs to stderr with a
consistent schema across the fleet.

Usage:
    from logging_config import configure_logging
    log = configure_logging("daily-agent")
    log.info("startup", port=8080)
    log.error("api_call_failed", tool="list_matters", status=500, elapsed_ms=312)

Standard schema:
    {
      "timestamp": "2026-05-22T10:30:00.123Z",
      "level": "info",
      "service": "<service_name>",
      "event": "<event_key>",
      <any additional structured fields>
    }
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


def configure_logging(
    service_name: str,
    level: str | None = None,
    sink: Any = None,
) -> structlog.stdlib.BoundLogger:
    """Configure structured JSON logging.

    Args:
        service_name: short identifier shown on every log line (e.g. "daily-agent").
        level: minimum log level. Defaults to LOG_LEVEL env var, then INFO.
        sink: file-like object for log output. Defaults to sys.stderr (so stdout
            stays clean for protocols like MCP stdio).

    Returns:
        A structlog logger pre-bound with `service=service_name`.
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")
    if sink is None:
        sink = sys.stderr

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sink),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger().bind(service=service_name)
