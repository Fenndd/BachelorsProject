from __future__ import annotations

import logging
import sys

_configured = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger for the given name."""
    return logging.getLogger(name)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a simple StreamHandler (idempotent)."""
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(levelname)-8s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)
