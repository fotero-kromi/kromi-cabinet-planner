"""Local rotating log for the Cabinet Planner (v34.55, audit reliability).

The app catches many errors on purpose so a run or an export never breaks on a
side feature (the database copy, the deck, the optimizer, an unreadable
override database). Those errors used to leave no trace. They are now written,
with their traceback, to a rotating log file on this computer:

* default: ``~/.kromi_cabinet_planner/logs/planner.log`` (1 MB x 5 files);
* ``KROMI_LOG_PATH`` points it elsewhere; ``off`` (or ``none``/``0``) switches
  logging off.

Logging never raises: if the file cannot be opened, the message is dropped.
The engine stays free of logging configuration; the page and the panels call
``log_exception`` where they catch an error.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

LOGGER_NAME = "kromi_planner"
_OFF = {"off", "none", "0", "false", "no"}
_MAX_BYTES = 1_000_000
_BACKUPS = 5


def log_path() -> Optional[str]:
    """The log file this process writes to, or None when logging is off."""
    env = os.getenv("KROMI_LOG_PATH")
    if env is not None:
        if env.strip().lower() in _OFF or not env.strip():
            return None
        return os.path.abspath(os.path.expanduser(env.strip()))
    return os.path.join(os.path.expanduser("~"), ".kromi_cabinet_planner", "logs",
                        "planner.log")


def get_logger() -> Optional[logging.Logger]:
    """The planner logger with a file handler for the current log path.

    The handler follows ``KROMI_LOG_PATH`` (tests point it at a temporary
    folder per test), so it is replaced when the path changes. Returns None
    when logging is off or the file cannot be opened.
    """
    path = log_path()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    current = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
    if current and path and getattr(current[0], "baseFilename", None) == path:
        return logger
    for handler in current:
        logger.removeHandler(handler)
        handler.close()
    if not path:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS,
                                      encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S"))
    logger.addHandler(handler)
    return logger


def log_exception(where: str, exc: Optional[BaseException] = None) -> None:
    """Record a caught error with its traceback. Never raises."""
    try:
        logger = get_logger()
        if logger is None:
            return
        if exc is not None:
            logger.error("%s: %s: %s", where, type(exc).__name__, exc,
                         exc_info=(type(exc), exc, exc.__traceback__))
        else:
            logger.error("%s", where, exc_info=True)
        for handler in logger.handlers:
            handler.flush()
    except Exception:  # logging must never break the app
        pass


def log_warning(message: str) -> None:
    """Record a notable condition without a traceback. Never raises."""
    try:
        logger = get_logger()
        if logger is not None:
            logger.warning("%s", message)
            for handler in logger.handlers:
                handler.flush()
    except Exception:
        pass
