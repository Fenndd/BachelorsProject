"""Lightweight string-presence tests for TUI view/screen source text.

These tests import module source via inspect and assert on string content --
no Textual App, no subprocess, no real experiments.
"""

from __future__ import annotations

import inspect
import pytest

pytestmark = pytest.mark.unit


def _src(module) -> str:
    return inspect.getsource(module)


def test_help_view_uses_py_launcher():
    import orchestrator.tui.views.help_view as m

    src = _src(m)
    assert "python -m orchestrator.cli.app" not in src, (
        "HelpView still contains 'python -m orchestrator.cli.app'; replace with 'py -m'"
    )
    assert "py -m orchestrator.cli.app --help" in src
    assert "py -m orchestrator.cli.app doctor" in src
    assert "py -m orchestrator.cli.app baseline run" in src
    assert "py -m orchestrator.cli.app experiment list" in src
    assert "py -m orchestrator.cli.app results list" in src
    assert "py -m orchestrator.cli.app workspace status" in src
    assert "py -m orchestrator.cli.app tui" in src


def test_help_view_has_debug_log_note():
    import orchestrator.tui.views.help_view as m

    src = _src(m)
    assert "tui_debug.log" in src, "HelpView should mention workspace/tui_debug.log"


def test_main_screen_subtitle_not_skeleton():
    import orchestrator.tui.screens.main_screen as m

    src = _src(m)
    assert "skeleton" not in src, "MainScreen subtitle still contains 'skeleton'"


def test_experiments_view_shows_solver_id():
    import orchestrator.tui.views.experiments_view as m

    src = _src(m)
    assert "solver_id" in src, "ExperimentsView should show solver_id in summaries"
    assert "Solver:" in src, "ExperimentsView _format_summary should include Solver: line"
