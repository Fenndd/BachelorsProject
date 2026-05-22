"""Lightweight TUI smoke tests: imports, static text, helpers.

No Textual App is launched. No subprocesses are spawned.
"""

from __future__ import annotations

import importlib
import inspect
import pytest

from types import SimpleNamespace

pytestmark = pytest.mark.unit


_SCREEN_MODULES = [
    "orchestrator.tui.screens.main_screen",
    "orchestrator.tui.screens.baseline_screen",
    "orchestrator.tui.screens.experiment_screen",
    "orchestrator.tui.screens.results_screen",
    "orchestrator.tui.screens.workspace_screen",
    "orchestrator.tui.screens.help_screen",
    "orchestrator.tui.screens.environment_screen",
    "orchestrator.tui.screens.doctor_screen",
    "orchestrator.tui.screens.placeholder_screen",
]


def _src(module) -> str:
    return inspect.getsource(module)


# ---------------------------------------------------------------------------
# 1. Import smoke test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module_name", _SCREEN_MODULES)
def test_import_all_screen_modules(module_name: str) -> None:
    """Every screen module under orchestrator.tui.screens imports without error."""
    mod = importlib.import_module(module_name)
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. HelpScreen safety notes
# ---------------------------------------------------------------------------


def test_help_screen_safety_notes_present() -> None:
    import orchestrator.tui.screens.help_screen as m

    src = _src(m)
    assert "read-only" in src, "HelpScreen should mention read-only results browsing"
    assert "never results/" in src or "never results/" in src.lower(), (
        "HelpScreen should clarify workspace cleanup never touches results/"
    )
    assert "not automatically modify" in src, (
        "HelpScreen should state it does not modify cpp/ automatically"
    )
    assert "API tokens" in src, (
        "HelpScreen should warn about API token usage"
    )


# ---------------------------------------------------------------------------
# 3. PlaceholderScreen
# ---------------------------------------------------------------------------


def test_placeholder_screen_instantiation() -> None:
    from orchestrator.tui.screens.placeholder_screen import PlaceholderScreen

    screen = PlaceholderScreen("Test Title", "Test message content")
    assert screen.placeholder_title == "Test Title"
    assert screen.message == "Test message content"


# ---------------------------------------------------------------------------
# 4. ResultsScreen empty state
# ---------------------------------------------------------------------------


def test_results_screen_handles_empty_state(monkeypatch) -> None:
    from orchestrator.tui.screens.results_screen import ResultsScreen, _format_item

    monkeypatch.setattr(
        "orchestrator.tui.screens.results_screen.list_result_items",
        lambda: [],
    )

    screen = ResultsScreen()
    assert screen.items == []
    assert _format_item(None) == "No saved results found."


def test_results_screen_compose_has_correct_labels() -> None:
    import orchestrator.tui.screens.results_screen as m

    src = _src(m)
    assert "Browse Results" in src, "ResultsScreen should have correct title"
    assert "Read-only navigation for saved run and experiment artifacts." in src
    assert "Refresh" in src
    assert "Open Dir" in src
    assert "Summary" in src
    assert "Final Source" in src
    assert "Final Diff" in src


# ---------------------------------------------------------------------------
# 5. WorkspaceScreen helpers
# ---------------------------------------------------------------------------


def test_workspace_format_bytes() -> None:
    from orchestrator.tui.screens.workspace_screen import _format_bytes

    assert _format_bytes(0) == "0 B"
    assert _format_bytes(1024) == "1.0 KiB"
    assert _format_bytes(1048576) == "1.0 MiB"
    assert _format_bytes(1073741824) == "1.0 GiB"
    assert _format_bytes(500) == "500 B"
    assert _format_bytes(2048) == "2.0 KiB"


def test_workspace_screen_compose_has_correct_labels() -> None:
    import orchestrator.tui.screens.workspace_screen as m

    src = _src(m)
    assert "Workspace" in src, "WorkspaceScreen should have correct title"
    assert "Inspect and clean temporary workspace data." in src
    assert "Clean Candidates" in src
    assert "Clean Experiments" in src
    assert "Clean All" in src
    assert "Cleanup only affects workspace/ and never deletes results/" in src


# ---------------------------------------------------------------------------
# 6. EnvironmentScreen secret masking
# ---------------------------------------------------------------------------


def test_environment_screen_secret_masking_static_text() -> None:
    import orchestrator.tui.screens.environment_screen as m

    src = _src(m)
    assert (
        "Secrets are masked and are never displayed in full." in src
    ), "EnvironmentScreen should state that secrets are masked"


def test_environment_screen_compose_has_correct_labels() -> None:
    import orchestrator.tui.screens.environment_screen as m

    src = _src(m)
    assert "Environment" in src
    assert "Local environment diagnostics for CLI/TUI launchers." in src
    assert "Refresh" in src


# ---------------------------------------------------------------------------
# 7. DoctorScreen static text
# ---------------------------------------------------------------------------


def test_doctor_screen_compose_has_correct_labels() -> None:
    import orchestrator.tui.screens.doctor_screen as m

    src = _src(m)
    assert "Doctor" in src, "DoctorScreen should have correct title"
    assert "Project structure and local environment diagnostics." in src
    assert "Full build/run checks will be added later." in src
    assert ".env.local" in src, "DoctorScreen should mention .env.local"
