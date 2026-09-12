"""
Logging configuration setup.
"""
import logging
import logging.handlers
import sys
from pathlib import Path

from src.core.config import Settings


def setup_logging(settings: Settings) -> None:
    """Configure logging based on settings."""
    log_config = settings.logging

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_config.level))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        fmt=log_config.format,
        datefmt=log_config.date_format,
    )

    # Console handler
    if log_config.console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_config.level))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_config.file_enabled:
        log_path = Path(log_config.file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=log_config.file_max_bytes,
            backupCount=log_config.file_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, log_config.level))
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("ccxt").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("tenacity").setLevel(logging.INFO)

    logging.info(f"Logging configured: level={log_config.level}, file={log_config.file_enabled}")