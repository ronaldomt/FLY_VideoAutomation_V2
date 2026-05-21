"""Structured logging configuration.

JSON logs to `~/.fly-video-automation/logs/YYYY-MM-DD.log` (rotating) plus stderr.
Every log line should include `session_id` and `behavior` when in a behavior context.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import structlog

LOG_DIR = Path.home() / ".fly-video-automation" / "logs"


def configure_logging(level: str = "INFO") -> None:
    """Wire structlog → stdlib logging → JSON file + stderr."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{date.today().isoformat()}.log"

    logging.basicConfig(
        level=level.upper(),
        format="%(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    logger = structlog.get_logger(name) if name else structlog.get_logger()
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger
