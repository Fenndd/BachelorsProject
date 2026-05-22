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
    root = logging.getLogger()
    has_stream_handler = any(
        isinstance(handler, logging.StreamHandler) for handler in root.handlers
    )
    if _configured and has_stream_handler:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(levelname)-8s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)
    _configured = True
