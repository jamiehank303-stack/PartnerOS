"""
core/logger.py

Centralized logging configuration for PartnerOS.

Provides a single `configure_logging()` entry point that sets up:
  1. A console (stream) handler for real-time visibility during development.
  2. A rotating file handler so logs persist to disk without growing
     unbounded.

Other modules should NOT call `logging.basicConfig()` themselves; instead
they should call `get_logger(__name__)` to obtain a properly namespaced
logger that inherits the handlers configured here. This keeps logging
configuration centralized (single responsibility) while allowing every
module to log under its own name for traceability.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.settings import Settings, get_settings

# Standard log line format: timestamp, level, logger name, message.
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Guard flag to ensure handlers are only attached once per process, even if
# `configure_logging()` is called multiple times (e.g. by tests or by
# multiple modules importing this file).
_LOGGING_CONFIGURED: bool = False


def configure_logging(settings: Settings | None = None) -> None:
    """
    Configure the root logger with a console handler and a rotating file
    handler, driven by application settings.

    Args:
        settings: Optional `Settings` instance. If not provided, the cached
            application settings are resolved via `get_settings()`. Accepting
            an explicit parameter keeps this function dependency-injectable
            and easy to unit test with custom settings.

    Idempotent: safe to call multiple times; handlers are only attached once.
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    resolved_settings = settings or get_settings()

    # Ensure the log directory exists before the file handler tries to open
    # a file inside it.
    log_dir: Path = resolved_settings.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / resolved_settings.LOG_FILE_NAME

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- Console handler --------------------------------------------------
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(resolved_settings.LOG_LEVEL)

    # --- Rotating file handler ----------------------------------------------
    file_handler = RotatingFileHandler(
        filename=str(log_file_path),
        maxBytes=resolved_settings.LOG_MAX_BYTES,
        backupCount=resolved_settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(resolved_settings.LOG_LEVEL)

    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_settings.LOG_LEVEL)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _LOGGING_CONFIGURED = True

    root_logger.info(
        "Logging configured | level=%s | file=%s",
        resolved_settings.LOG_LEVEL,
        log_file_path,
    )


def get_logger(name: str) -> logging.Logger:
    """
    Return a namespaced logger for the given module.

    Ensures `configure_logging()` has run at least once (using default
    settings) so that any module can safely call `get_logger(__name__)`
    without first worrying about initialization order.

    Args:
        name: Typically `__name__` of the calling module, so log lines are
            traceable to their origin.

    Returns:
        A standard library `logging.Logger` instance with the application's
        console + rotating file handlers attached (via the root logger).
    """
    if not _LOGGING_CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
