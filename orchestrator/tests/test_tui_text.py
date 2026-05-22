"""Lightweight string-presence tests for TUI screen source text.

These tests import module source via inspect and assert on string content —
no Textual App, no subprocess, no real experiments.
"""

from __future__ import annotations

import inspect
import pytest

pytestmark = pytest.mark.unit


def _src(module) -> str:
    return inspect.getsource(module)


def test_help_screen_uses_py_launcher():
    import orchestrator.tui.screens.help_screen as m

    src = _src(m)
    assert "python -m orchestrator.cli.app" not in src, (
        "HelpScreen still contains 'python -m orchestrator.cli.app'; replace with 'py -m'"
    )
    assert "py -m orchestrator.cli.app --help" in src
    assert "py -m orchestrator.cli.app doctor" in src
    assert "py -m orchestrator.cli.app baseline run" in src
    assert "py -m orchestrator.cli.app experiment list" in src
    assert "py -m orchestrator.cli.app results list" in src
    assert "py -m orchestrator.cli.app workspace status" in src
    assert "py -m orchestrator.cli.app tui" in src


def test_help_screen_has_debug_log_note():
    import orchestrator.tui.screens.help_screen as m

    src = _src(m)
    assert "tui_debug.log" in src, "HelpScreen should mention workspace/tui_debug.log"


def test_main_screen_subtitle_updated():
    import orchestrator.tui.screens.main_screen as m

    src = _src(m)
    assert "skeleton" not in src, "MainScreen subtitle still contains 'skeleton'"
    assert "Interactive control layer for LLM optimization experiments" in src


def test_experiment_screen_preflight_failed_messages():
    import orchestrator.tui.screens.experiment_screen as m

    src = _src(m)
    assert "No subprocess was started." in src
    assert "Experiment subprocess was not started." in src
    assert "Preflight failed." in src


def test_experiment_screen_initial_log_text():
    import orchestrator.tui.screens.experiment_screen as m

    src = _src(m)
    assert "Starting experiment launcher..." in src
    assert "Running preflight checks before subprocess execution..." in src
    assert "Starting experiment subprocess..." not in src, (
        "Old misleading log line 'Starting experiment subprocess...' should be removed"
    )
    assert "Waiting for output..." not in src, (
        "Old misleading log line 'Waiting for output...' should be removed"
    )
