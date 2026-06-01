"""Logging setup for the trading bot.

All detail (requests, responses, errors) goes to a single rotating file handler
at ``logs/trading_bot.log``. The console is left to the CLI, which prints clean,
user-facing summaries with ``print`` -- so the log file stays a complete audit
trail without the terminal becoming noisy or showing each line twice.

Secrets are never written to the log -- ``redact`` strips the API secret and the
request signature before any params get logged.
"""

import logging
import os
from copy import deepcopy
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
LOG_FILE = "trading_bot.log"

# Param keys whose values must never end up in the log file.
_SENSITIVE_KEYS = {"signature", "secret", "api_secret", "apiSecret"}

_FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(log_dir=LOG_DIR):
    """Configure the 'tradingbot' logger to write to the rotating log file.

    Calling this more than once is safe -- existing handlers are cleared first so
    we don't end up logging every line twice.
    """
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("tradingbot")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, LOG_FILE),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))

    logger.addHandler(file_handler)
    return logger


def get_logger(name="tradingbot"):
    """Return a child logger so module names show up in the log."""
    return logging.getLogger(name)


def redact(params):
    """Return a copy of ``params`` with sensitive values masked.

    Use this before logging anything that might contain the signature or secret.
    """
    if not isinstance(params, dict):
        return params
    safe = deepcopy(params)
    for key in safe:
        if key in _SENSITIVE_KEYS:
            safe[key] = "***redacted***"
    return safe
