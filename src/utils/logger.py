"""
Logging setup using Loguru.

Provides structured logging with:
- Console output (colorized, INFO level)
- File output (DEBUG level, rotation, retention)
- Optional Telegram alert on CRITICAL
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(log_level: str = "INFO", log_dir: str = "logs") -> None:
    """Configure loguru logger for the application."""
    # Remove default handler
    logger.remove()

    # Console handler — colorized, concise
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File handler — detailed, rotated
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    logger.add(
        str(log_path / "fxbot_{time:YYYY-MM-DD}.log"),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,  # Thread-safe
    )

    # Error-only file for quick troubleshooting
    logger.add(
        str(log_path / "errors.log"),
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}\n{exception}",
        rotation="5 MB",
        retention="60 days",
        compression="zip",
        enqueue=True,
    )

    logger.info("Logger initialized | level={} | dir={}", log_level, log_dir)
