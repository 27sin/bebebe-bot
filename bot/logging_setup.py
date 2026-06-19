from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from bot.config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "bot.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


def setup_logging(level: int = logging.INFO) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT)

    if not any(isinstance(handler, logging.StreamHandler) for handler in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)

    if not any(isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    return LOG_FILE
