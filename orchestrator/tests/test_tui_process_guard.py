from __future__ import annotations

import asyncio

import pytest
from types import SimpleNamespace

pytestmark = pytest.mark.unit

from orchestrator.tui import debug_log
from orchestrator.tui.app import OptimizerTuiApp
from orchestrator.tui.active_runs import ActiveRunsManager, ActiveRun, ActiveRunStatus


# ---------------------------------------------------------------------------
# App process guard
# ---------------------------------------------------------------------------


def test_optimizer_tui_process_guard_clamps_at_zero() -> None:
    app = OptimizerTuiApp()

    assert app.active_processes == 0
    assert not app.has_active_processes()

    app.register_process()
    app.register_process()
    assert app.active_processes == 2
    assert app.has_active_processes()

    app.unregister_process()
    app.unregister_process()
    app.unregister_process()
    assert app.active_processes == 0
    assert not app.has_active_processes()


def test_optimizer_tui_quit_exits_with_no_active_runs(monkeypatch) -> None:
    app = OptimizerTuiApp()
    exits: list[bool] = []

    monkeypatch.setattr(OptimizerTuiApp, "exit", lambda self: exits.append(True))
    monkeypatch.setattr(
        app.active_runs_manager,
        "active_count",
        lambda: 0,
    )

    asyncio.run(app.action_quit())

    assert exits == [True]


def test_optimizer_tui_quit_shows_modal_when_runs_active(monkeypatch) -> None:
    app = OptimizerTuiApp()
    pushed_screens: list[object] = []
    exits: list[bool] = []

    monkeypatch.setattr(OptimizerTuiApp, "exit", lambda self: exits.append(True))
    monkeypatch.setattr(
        OptimizerTuiApp,
        "push_screen",
        lambda self, screen, callback=None: pushed_screens.append(screen),
    )
    monkeypatch.setattr(
        app.active_runs_manager,
        "active_count",
        lambda: 2,
    )

    asyncio.run(app.action_quit())

    assert not exits
    assert len(pushed_screens) == 1
    assert getattr(pushed_screens[0], "_count", 0) == 2
    assert getattr(pushed_screens[0], "_active_run_count", 0) == 2


def test_optimizer_tui_quit_shows_modal_when_legacy_process_active(monkeypatch) -> None:
    app = OptimizerTuiApp()
    pushed_screens: list[object] = []
    exits: list[bool] = []

    app.register_process()
    monkeypatch.setattr(OptimizerTuiApp, "exit", lambda self: exits.append(True))
    monkeypatch.setattr(
        OptimizerTuiApp,
        "push_screen",
        lambda self, screen, callback=None: pushed_screens.append(screen),
    )
    monkeypatch.setattr(app.active_runs_manager, "active_count", lambda: 0)

    asyncio.run(app.action_quit())

    assert not exits
    assert len(pushed_screens) == 1
    assert getattr(pushed_screens[0], "_legacy_count", 0) == 1


def test_optimizer_tui_quit_confirm_cancels_and_exits_after_runs_stop(monkeypatch) -> None:
    app = OptimizerTuiApp()
    cancelled: list[bool] = []
    exits: list[bool] = []
    stopped: list[bool] = []

    monkeypatch.setattr(app.active_runs_manager, "cancel_all", lambda: cancelled.append(True))
    monkeypatch.setattr(app.active_runs_manager, "active_count", lambda: 0)
    monkeypatch.setattr(OptimizerTuiApp, "exit", lambda self: exits.append(True))
    monkeypatch.setattr(app, "set_interval", lambda *_args, **_kwargs: SimpleNamespace(stop=lambda: stopped.append(True)))

    app._on_quit_confirm(True)

    assert cancelled == [True]
    assert exits == [True]
    assert stopped == [True]


# ---------------------------------------------------------------------------
# Debug log
# ---------------------------------------------------------------------------


def test_write_tui_debug_appends_timestamped_message(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        debug_log,
        "get_project_paths",
        lambda: SimpleNamespace(workspace=tmp_path / "workspace"),
    )

    debug_log.write_tui_debug("hello tui")

    text = (tmp_path / "workspace" / "tui_debug.log").read_text(encoding="utf-8")
    assert "hello tui" in text
    assert "T" in text.split(" hello tui")[0]


def test_write_tui_debug_does_not_raise(monkeypatch) -> None:
    def fail_paths():
        raise RuntimeError("no paths")

    monkeypatch.setattr(debug_log, "get_project_paths", fail_paths)

    debug_log.write_tui_debug("ignored")


# ---------------------------------------------------------------------------
# BaselineView -- manager-based, no legacy queue/watchdog state
# ---------------------------------------------------------------------------


def test_baseline_view_has_no_legacy_state() -> None:
    from orchestrator.tui.views.baseline_view import BaselineView

    view = BaselineView()

    assert not hasattr(view, "_state")
    assert not hasattr(view, "_process_registered")
    assert not hasattr(view, "_log_queue")
    assert not hasattr(view, "_result_queue")
    assert not hasattr(view, "_drain_timer")
    assert not hasattr(view, "_watchdog_timer")


def test_baseline_view_start_calls_manager_start_baseline(monkeypatch) -> None:
    from orchestrator.tui.views.baseline_view import BaselineView
    from orchestrator.tui.screens.active_run_screen import ActiveRunScreen

    view = BaselineView()
    started_runs: list[str] = []
    pushed_screens: list[object] = []
    start_button_queries: list[str] = []

    def fake_query(widget_id, *args, **kwargs):
        if "start-baseline" in str(widget_id):
            start_button_queries.append(str(widget_id))
        if "baseline-status" in str(widget_id):
            return SimpleNamespace(update=lambda t: None)
        return SimpleNamespace(update=lambda t: None)

    mock_manager = SimpleNamespace(
        start_baseline=lambda: started_runs.append("run_001") or "run_001",
    )
    monkeypatch.setattr(
        BaselineView,
        "app",
        SimpleNamespace(
            active_runs_manager=mock_manager,
            push_screen=lambda s: pushed_screens.append(s),
        ),
    )
    monkeypatch.setattr(view, "query_one", fake_query)

    view._start_baseline()

    assert started_runs == ["run_001"]
    assert len(pushed_screens) == 1
    assert isinstance(pushed_screens[0], ActiveRunScreen)
    assert start_button_queries == []


def test_baseline_view_does_not_call_register_process(monkeypatch) -> None:
    from orchestrator.tui.views.baseline_view import BaselineView

    view = BaselineView()
    register_calls: list[int] = []
    unregister_calls: list[int] = []

    def fake_query(widget_id, *args, **kwargs):
        if "baseline-status" in str(widget_id):
            return SimpleNamespace(update=lambda t: None)
        return SimpleNamespace(update=lambda t: None)

    mock_manager = SimpleNamespace(start_baseline=lambda: "run_001")
    monkeypatch.setattr(
        BaselineView,
        "app",
        SimpleNamespace(
            active_runs_manager=mock_manager,
            push_screen=lambda s: None,
            register_process=lambda: register_calls.append(1),
            unregister_process=lambda: unregister_calls.append(1),
        ),
    )
    monkeypatch.setattr(view, "query_one", fake_query)

    view._start_baseline()

    assert register_calls == []
    assert unregister_calls == []


# ---------------------------------------------------------------------------
# ExperimentsView -- manager-based, no queues or timers
# ---------------------------------------------------------------------------


def test_experiments_view_has_no_legacy_state() -> None:
    from orchestrator.tui.views.experiments_view import ExperimentsView

    view = ExperimentsView()

    assert not hasattr(view, "_state")
    assert not hasattr(view, "_process_registered")
    assert not hasattr(view, "_log_queue")
    assert not hasattr(view, "_result_queue")
    assert not hasattr(view, "_drain_timer")
    assert not hasattr(view, "_watchdog_timer")


def test_experiments_view_start_before_ready_is_blocked(monkeypatch) -> None:
    from orchestrator.tui.views.experiments_view import ExperimentsView

    view = ExperimentsView()
    statuses: list[str] = []

    monkeypatch.setattr(view, "_set_status_message", statuses.append)

    view._start_experiment(dry_run=True)

    assert "View initializing" in statuses[0]


def test_experiments_view_dry_run_calls_manager_start_experiment(monkeypatch) -> None:
    from pathlib import Path
    from orchestrator.tui.views.experiments_view import ExperimentsView
    from orchestrator.tui.screens.active_run_screen import ActiveRunScreen

    view = ExperimentsView()
    expected_path = Path("/fake/config.json")
    start_calls: list[tuple] = []
    pushed_screens: list[object] = []
    mock_manager = SimpleNamespace(
        start_experiment=lambda config_path, dry_run: start_calls.append((config_path, dry_run)) or "run_001",
    )
    monkeypatch.setattr(view, "_can_start", True)
    monkeypatch.setattr(view, "_selected_summary", lambda: SimpleNamespace(path=expected_path))
    monkeypatch.setattr(view, "query_one", lambda *a, **kw: SimpleNamespace(update=lambda t: None))
    monkeypatch.setattr(
        ExperimentsView,
        "app",
        SimpleNamespace(
            active_runs_manager=mock_manager,
            push_screen=lambda s: pushed_screens.append(s),
        ),
    )

    view._start_experiment(dry_run=True)

    assert start_calls == [(expected_path, True)]
    assert len(pushed_screens) == 1
    assert isinstance(pushed_screens[0], ActiveRunScreen)


def test_experiments_view_real_run_shows_confirm_modal(monkeypatch) -> None:
    from pathlib import Path
    from orchestrator.tui.views.experiments_view import ExperimentsView
    from orchestrator.tui.screens._confirm_paid_run import ConfirmPaidRunScreen

    view = ExperimentsView()
    pushed_screens: list[object] = []
    fake_path = Path("/fake/config.json")

    view._can_start = True
    monkeypatch.setattr(view, "_selected_summary", lambda: SimpleNamespace(path=fake_path))
    monkeypatch.setattr(
        ExperimentsView,
        "app",
        SimpleNamespace(push_screen=lambda s, callback=None: pushed_screens.append(s)),
    )

    view._request_real_run()

    assert len(pushed_screens) == 1
    assert isinstance(pushed_screens[0], ConfirmPaidRunScreen)


def test_experiments_view_on_list_view_highlighted_updates_summary(monkeypatch) -> None:
    from orchestrator.tui.views.experiments_view import ExperimentsView

    view = ExperimentsView()
    updates: list[str] = []
    summary_widget = SimpleNamespace(update=updates.append)

    monkeypatch.setattr(view, "_selected_summary", lambda: None)
    monkeypatch.setattr(view, "query_one", lambda *args, **kwargs: summary_widget)

    view.on_list_view_highlighted(SimpleNamespace())

    assert len(updates) == 1


# ---------------------------------------------------------------------------
# ActiveRunScreen -- escape pops without cancelling
# ---------------------------------------------------------------------------


def test_active_run_screen_escape_action_pops_without_cancelling(monkeypatch) -> None:
    from orchestrator.tui.screens.active_run_screen import ActiveRunScreen

    screen = ActiveRunScreen("run_001")
    popped: list[bool] = []
    cancelled: list[str] = []
    monkeypatch.setattr(
        ActiveRunScreen,
        "app",
        SimpleNamespace(
            pop_screen=lambda: popped.append(True),
            active_runs_manager=SimpleNamespace(cancel=lambda run_id: cancelled.append(run_id)),
        ),
    )

    screen.action_request_back()

    assert popped == [True]
    assert cancelled == []
