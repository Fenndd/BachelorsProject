"""Lightweight TUI smoke tests: imports, static text, helpers.

No Textual App is launched. No subprocesses are spawned.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_SCREEN_MODULES = [
    "orchestrator.tui.screens.main_screen",
    "orchestrator.tui.screens.active_run_screen",
    "orchestrator.tui.screens.config_builder_screen",
    "orchestrator.tui.screens._confirm_paid_run",
    "orchestrator.tui.screens._quit_confirm",
]

_VIEW_MODULES = [
    "orchestrator.tui.views.dashboard_view",
    "orchestrator.tui.views.baseline_view",
    "orchestrator.tui.views.experiments_view",
    "orchestrator.tui.views.results_view",
    "orchestrator.tui.views.config_builder_view",
    "orchestrator.tui.views.system_view",
    "orchestrator.tui.views.help_view",
]

_OTHER_MODULES = [
    "orchestrator.tui.active_runs",
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


@pytest.mark.parametrize("module_name", _OTHER_MODULES)
def test_import_other_tui_modules(module_name: str) -> None:
    """Other TUI modules import without error."""
    mod = importlib.import_module(module_name)
    assert mod is not None


@pytest.mark.parametrize("module_name", _VIEW_MODULES)
def test_import_all_view_modules(module_name: str) -> None:
    """Every view module under orchestrator.tui.views imports without error."""
    mod = importlib.import_module(module_name)
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. Help view safety notes
# ---------------------------------------------------------------------------


def test_help_view_safety_notes_present() -> None:
    import orchestrator.tui.views.help_view as m

    src = _src(m)
    assert "read-only" in src, "HelpView should mention read-only results browsing"
    assert "never results/" in src or "never results/" in src.lower(), (
        "HelpView should clarify workspace cleanup never touches results/"
    )
    assert "not automatically modify" in src, (
        "HelpView should state it does not modify cpp/ automatically"
    )
    assert "API tokens" in src, (
        "HelpView should warn about API token usage"
    )


# ---------------------------------------------------------------------------
# 3. ResultsView instantiation
# ---------------------------------------------------------------------------


def test_results_view_placeholder_exists() -> None:
    from orchestrator.tui.views.results_view import ResultsView

    view = ResultsView()
    assert view.id == "view-results"


def test_results_view_has_placeholder_text() -> None:
    import orchestrator.tui.views.results_view as m

    src = _src(m)
    assert "Results" in src, "ResultsView should mention Results"
    assert "Read-only navigation" in src, "ResultsView should mention read-only navigation"


# ---------------------------------------------------------------------------
# 4. SystemView helpers (workspace, environment, doctor)
# ---------------------------------------------------------------------------


def test_system_view_format_bytes() -> None:
    from orchestrator.tui.views.system_view import _format_bytes

    assert _format_bytes(0) == "0 B"
    assert _format_bytes(1024) == "1.0 KiB"
    assert _format_bytes(1048576) == "1.0 MiB"
    assert _format_bytes(1073741824) == "1.0 GiB"
    assert _format_bytes(500) == "500 B"
    assert _format_bytes(2048) == "2.0 KiB"


def test_system_view_has_workspace_labels() -> None:
    import orchestrator.tui.views.system_view as m

    src = _src(m)
    assert "Workspace" in src, "SystemView should have Workspace section"
    assert "Clean Candidates" in src
    assert "Clean Experiments" in src
    assert "Clean All" in src
    assert "Cleanup only affects workspace/ and never deletes results/" in src


def test_system_view_secret_masking_static_text() -> None:
    import orchestrator.tui.views.system_view as m

    src = _src(m)
    assert (
        "Secrets are masked and are never displayed in full." in src
    ), "SystemView should state that secrets are masked"


def test_system_view_has_environment_labels() -> None:
    import orchestrator.tui.views.system_view as m

    src = _src(m)
    assert "Environment" in src
    assert "Refresh Environment" in src


def test_system_view_has_doctor_labels() -> None:
    import orchestrator.tui.views.system_view as m

    src = _src(m)
    assert "Doctor" in src, "SystemView should have Doctor section"
    assert "Full build/run checks will be added later." in src
    assert ".env.local" in src, "SystemView should mention .env.local"


# ---------------------------------------------------------------------------
# 5. DashboardView
# ---------------------------------------------------------------------------


def test_dashboard_view_has_project_info() -> None:
    import orchestrator.tui.views.dashboard_view as m

    src = _src(m)
    assert "Dashboard" in src
    assert "Interactive control layer for LLM optimization experiments" in src
    assert "Active runs are visible" in src
    assert "Go to Baseline" in src
    assert "Go to Experiments" in src
    assert "Go to Results" in src
    assert "action_show_view" in src


def test_results_view_displays_baseline_label_for_runs() -> None:
    import orchestrator.tui.views.results_view as m

    assert m._display_kind("run") == "baseline"
    assert m._display_kind("baseline") == "baseline"
    assert m._display_kind("candidate") == "candidate"
    assert m._display_kind("experiment") == "experiment"


def test_results_view_summary_displays_baseline_label_for_runs() -> None:
    from orchestrator.control import ResultArtifactMap, ResultItem
    import orchestrator.tui.views.results_view as m

    artifacts = ResultArtifactMap(
        directory=Path("results/runs/run_001"),
        summary_txt=None,
        metadata_json=None,
        status_json=None,
        metrics_json=None,
        experiment_status_json=None,
        experiment_config_snapshot_json=None,
        experiment_config_effective_json=None,
        closed_loop_summary_json=None,
        closed_loop_iterations_jsonl=None,
        final_optimized_source_dir=None,
        final_optimized_source_diff=None,
        report_dir=None,
        report_pdf=None,
        report_html=None,
        final_selection_dir=None,
        final_selection_report=None,
    )
    item = ResultItem(
        kind="baseline",
        name="run_001",
        path=Path("results/runs/run_001"),
        modified_time=0.0,
        status="success",
        started_at=None,
        finished_at=None,
        summary_text=None,
        final_speedup_vs_baseline=None,
        final_runtime_reduction_percent=None,
        final_best_iteration=None,
        accepted_improvements=None,
        artifacts=artifacts,
        read_errors=[],
    )

    assert "Kind: baseline" in m._format_item(item)
    assert "Kind: run" not in m._format_item(item)


def test_results_view_refresh_summaries_reloads_items(monkeypatch) -> None:
    from orchestrator.control import ResultArtifactMap, ResultItem
    import orchestrator.tui.views.results_view as m
    from orchestrator.tui.views.results_view import ResultsView

    item = ResultItem(
        kind="baseline",
        name="run_001",
        path=Path("results/runs/run_001"),
        modified_time=0.0,
        status="success",
        started_at=None,
        finished_at=None,
        summary_text=None,
        final_speedup_vs_baseline=None,
        final_runtime_reduction_percent=None,
        final_best_iteration=None,
        accepted_improvements=None,
        artifacts=ResultArtifactMap(Path("results/runs/run_001"), None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None),
        read_errors=[],
    )
    view = ResultsView()
    rebuilt: list[object] = []
    statuses: list[str] = []
    monkeypatch.setattr(view, "_selected_item", lambda: None)
    monkeypatch.setattr(view, "_rebuild_table", lambda selected_key=None: rebuilt.append(selected_key))
    monkeypatch.setattr(view, "_set_status", statuses.append)
    monkeypatch.setattr(m, "list_result_items", lambda: [item])

    view.refresh_summaries("updated")

    assert view._all_items == [item]
    assert rebuilt == [None]
    assert statuses == ["updated"]


def test_results_view_formats_details_by_kind(tmp_path: Path) -> None:
    from orchestrator.control import ResultArtifactMap, ResultItem
    import orchestrator.tui.views.results_view as m

    def artifacts(path: Path) -> ResultArtifactMap:
        return ResultArtifactMap(path, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None)

    baseline = ResultItem("baseline", "base", tmp_path / "base", 0, "success", None, None, None, None, None, None, None, artifacts(tmp_path / "base"), [])
    candidate_dir = tmp_path / "cand"
    candidate_dir.mkdir()
    (candidate_dir / "candidate.json").write_text('{"summary": "faster"}\n', encoding="utf-8")
    candidate = ResultItem("candidate", "cand", candidate_dir, 0, "success", None, None, None, None, None, None, None, artifacts(candidate_dir), [])
    experiment = ResultItem("experiment", "exp", tmp_path / "exp", 0, "completed", None, None, None, 1.2, 16.7, 2, 1, artifacts(tmp_path / "exp"), [])

    assert "Final selection speedup" not in m._format_item(baseline)
    assert "Candidate artifact path" in m._format_item(candidate)
    assert "Final selection speedup" in m._format_item(experiment)


def test_main_screen_uses_content_switcher() -> None:
    import orchestrator.tui.screens.main_screen as m

    src = _src(m)
    assert "ContentSwitcher" in src
    assert "content.current" in src
    assert "child.display" not in src


def test_main_screen_config_builder_is_embedded() -> None:
    import orchestrator.tui.screens.main_screen as m

    src = _src(m)
    assert "ConfigBuilderView" in src
    assert "__config-builder" not in src
    assert "push_screen(ConfigBuilderScreen" not in src


def test_views_package_exports_all_embedded_views() -> None:
    import orchestrator.tui.views as views

    assert set(views.__all__) == {
        "DashboardView",
        "BaselineView",
        "ExperimentsView",
        "ResultsView",
        "ConfigBuilderView",
        "SystemView",
        "HelpView",
    }


def test_baseline_view_does_not_render_fake_live_log() -> None:
    import orchestrator.tui.views.baseline_view as m

    src = _src(m)
    assert "baseline-log" not in src
    assert "Open it from the sidebar" in src


def test_quit_confirm_mentions_active_runs_not_only_experiments() -> None:
    import orchestrator.tui.screens._quit_confirm as m

    src = _src(m)
    assert "active run(s)" in src
    assert "active experiment run(s)" not in src
