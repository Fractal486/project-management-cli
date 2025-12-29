"""Central logging configuration for the Project Manager CLI."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import Config

_INITIALISED = False

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(config: Config, base_path: Optional[Path] = None, disable_console: bool = False) -> None:
    """Configure root logging handlers according to the supplied config.

    Parameters
    ----------
    config:
        Active configuration object (mutations to logging fields should be
        applied before calling this function).
    base_path:
        Optional base directory used to resolve relative log file paths.
    disable_console:
        If True, console logging will be disabled (useful for TUI applications).
    """

    global _INITIALISED
    if _INITIALISED:
        return

    logging.captureWarnings(True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(LOG_FORMAT)

    # Console handler (disabled for live TUI to avoid interfering with the UI)
    if not disable_console:
        console_handler = logging.StreamHandler()
        console_level = _parse_level(config.log_level_console, logging.INFO)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    # Rotating file handler
    if config.enable_file_logging:
        log_path = Path(config.log_file_path)
        if not log_path.is_absolute() and base_path:
            log_path = base_path / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=config.log_max_bytes,
            backupCount=config.log_backup_count,
            encoding="utf-8",
        )
        file_level = _parse_level(config.log_level_file, logging.DEBUG)
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _INITIALISED = True


def _parse_level(value: str, default: int) -> int:
    """Return a logging level constant for the given string."""
    try:
        return getattr(logging, value.upper())
    except AttributeError:
        return default
