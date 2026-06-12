"""
utils/logger.py
===============
Centralised logging configuration for the entire bot.

Sets up a rotating file handler (logs/bot.log) and a coloured
console handler so that log output is readable at a glance.

Usage
-----
    from utils.logger import setup_logger
    logger = setup_logger("my_module")
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Max 5 MB per file, keep 3 backups
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3


# ---------------------------------------------------------------------------
# ANSI colour codes for the console handler
# ---------------------------------------------------------------------------

class _ColourFormatter(logging.Formatter):
    """Adds ANSI colour escapes to log level names in console output."""

    _LEVEL_COLOURS: dict[int, str] = {
        logging.DEBUG:    "\033[37m",    # white
        logging.INFO:     "\033[36m",    # cyan
        logging.WARNING:  "\033[33m",    # yellow
        logging.ERROR:    "\033[31m",    # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self._LEVEL_COLOURS.get(record.levelno, self._RESET)
        record.levelname = f"{colour}{record.levelname:<8}{self._RESET}"
        return super().format(record)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Return a named logger that writes to both the console and a rotating
    log file.  Calling this multiple times with the same *name* is safe —
    the root logger is only configured once.

    Parameters
    ----------
    name:
        The logger name (usually the module name, e.g. ``"moderation"``).
    level:
        Minimum log level.  Defaults to ``logging.INFO``.
    """
    # Ensure the log directory exists.
    os.makedirs(LOG_DIR, exist_ok=True)

    # Configure the root logger only once.
    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(logging.DEBUG)  # let handlers filter

        # --- Console handler (coloured) ---
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(
            _ColourFormatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
        )
        root.addHandler(console_handler)

        # --- Rotating file handler (plain text) ---
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)
        )
        root.addHandler(file_handler)

        # Silence noisy third-party loggers.
        logging.getLogger("discord").setLevel(logging.WARNING)
        logging.getLogger("discord.http").setLevel(logging.WARNING)
        logging.getLogger("aiosqlite").setLevel(logging.WARNING)

    return logging.getLogger(name)
