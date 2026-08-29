"""Console and file logging.

The console stays readable: one line per step, no timestamps.  The log file
keeps timestamps and levels, and is part of the deliverable as the run record.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "q50depth"


def configure(log_path: Path | None, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console)

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
        )
        logger.addHandler(file_handler)

    return logger


def get() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
