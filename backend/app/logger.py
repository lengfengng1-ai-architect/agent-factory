"""Unified logging configuration for Agent Factory backend.

Usage:
    from app.logger import get_logger
    logger = get_logger(__name__)
    logger.info("message")
"""

import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Backend root = parent of app/ (i.e. backend/)
BACKEND_ROOT = Path(__file__).parent.parent.resolve()


def _get_log_dir() -> Path:
    # 1. Explicit env var (highest priority, used by desktop app --data-dir)
    env_dir = os.environ.get("AGENT_FACTORY_DATA_DIR")
    if env_dir:
        return Path(env_dir) / "logs"

    # 2. Desktop mode
    if os.environ.get("ENV") == "production":
        return Path.home() / ".agent-factory" / "logs"

    # 3. Web dev mode: fixed location under backend/data/logs/
    return BACKEND_ROOT / "data" / "logs"


LOG_DIR = _get_log_dir()
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / f"agent_factory_{datetime.now().strftime('%Y%m%d')}.log"

# Formatter
fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(fmt, datefmt)

# File handler - rotates by day implicitly via filename
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Root logger configuration
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Avoid duplicate handlers on reloads
if not any(isinstance(h, logging.FileHandler) for h in root_logger.handlers):
    root_logger.addHandler(file_handler)
if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


def truncate_for_log(value, max_len: int = 2000) -> str:
    """Truncate long strings for logging."""
    text = str(value)
    if len(text) > max_len:
        return text[:max_len] + f"...[{len(text) - max_len} more chars]"
    return text
