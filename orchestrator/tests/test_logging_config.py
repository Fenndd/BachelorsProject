from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import logging
from io import StringIO

from orchestrator.logging_config import configure_logging, get_logger


class TestGetLogger:
    def test_returns_logger(self) -> None:
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_same_name_returns_same_logger(self) -> None:
        a = get_logger("test.same")
        b = get_logger("test.same")
        assert a is b


class TestConfigureLogging:
    def test_adds_stream_handler(self) -> None:
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        root.setLevel(logging.WARNING)

        configure_logging()
        assert any(
            isinstance(h, logging.StreamHandler) for h in root.handlers
        )

    def test_is_idempotent(self) -> None:
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        root.setLevel(logging.WARNING)

        import orchestrator.logging_config as lc

        lc._configured = False
        configure_logging()
        count = len(root.handlers)
        configure_logging()
        assert len(root.handlers) == count

    def test_emits_message(self) -> None:
        logger = get_logger("test.emitter")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("hello world")

        output = stream.getvalue()
        assert "INFO" in output
        assert "test.emitter" in output
        assert "hello world" in output

    def test_level_defaults_to_info(self) -> None:
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        root.setLevel(logging.WARNING)

        import orchestrator.logging_config as lc

        lc._configured = False
        configure_logging()
        assert root.level == logging.INFO
