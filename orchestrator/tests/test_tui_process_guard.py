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

    view = BaselineView()
    start_calls: list[str | None] = []
    pushed_screens: list[object] = []
    start_button_queries: list[str] = []
    statuses: list[str] = []

    def fake_query(widget_id, *args, **kwargs):
        if "start-baseline" in str(widget_id):
            start_button_queries.append(str(widget_id))
        if "baseline-solver" in str(widget_id):
            return SimpleNamespace(value="poselib_p3p")
        if "baseline-status" in str(widget_id):
            return SimpleNamespace(update=statuses.append)
        return SimpleNamespace(update=lambda t: None)

    mock_manager = SimpleNamespace(
        start_baseline=lambda solver_id=None: start_calls.append(solver_id) or "run_001",
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

    assert start_calls == ["poselib_p3p"]
    assert pushed_screens == []
    assert "Open it from the sidebar" in statuses[0]
    assert start_button_queries == []


def test_baseline_view_does_not_call_register_process(monkeypatch) -> None:
    from orchestrator.tui.views.baseline_view import BaselineView

    view = BaselineView()
    register_calls: list[int] = []
    unregister_calls: list[int] = []

    def fake_query(widget_id, *args, **kwargs):
        if "baseline-solver" in str(widget_id):
            return SimpleNamespace(value="poselib_p3p")
        if "baseline-status" in str(widget_id):
            return SimpleNamespace(update=lambda t: None)
        return SimpleNamespace(update=lambda t: None)

    mock_manager = SimpleNamespace(start_baseline=lambda solver_id=None: "run_001")
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
    assert pushed_screens == []


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


def test_experiments_view_on_select_changed_updates_summary(monkeypatch) -> None:
    from orchestrator.tui.views.experiments_view import ExperimentsView

    view = ExperimentsView()
    updates: list[str] = []
    summary_widget = SimpleNamespace(update=updates.append)

    monkeypatch.setattr(view, "_selected_summary", lambda: None)
    monkeypatch.setattr(view, "query_one", lambda *args, **kwargs: summary_widget)

    view.on_select_changed(SimpleNamespace(select=SimpleNamespace(id="experiment-config")))

    assert len(updates) == 1


def test_experiments_view_refresh_rebuilds_summaries(monkeypatch) -> None:
    from pathlib import Path
    import orchestrator.tui.views.experiments_view as experiments_view
    from orchestrator.control import ExperimentConfigSummary
    from orchestrator.tui.views.experiments_view import ExperimentsView

    def summary(path: str, name: str) -> ExperimentConfigSummary:
        return ExperimentConfigSummary(
            path=Path(path),
            name=name,
            description=None,
            target_file=None,
            solver_id="solver",
            variants_count=1,
            total_iterations=1,
            baseline_run_dir=None,
            reporting_enabled=True,
            providers=[],
            models=[],
            status="ok",
            message=None,
        )

    old_a = summary("/configs/a.json", "old a")
    old_b = summary("/configs/b.json", "old b")
    new_a = summary("/configs/a.json", "new a")
    new_b = summary("/configs/b.json", "new b")
    new_c = summary("/configs/c.json", "new c")

    view = ExperimentsView()
    view.summaries = [old_a, old_b]
    config_select = SimpleNamespace(
        value=str(old_b.path),
        options=[],
        set_options=lambda options: setattr(config_select, "options", options),
    )
    summary_updates: list[str] = []
    status_updates: list[str] = []

    def query_one(selector, *args, **kwargs):
        if selector == "#experiment-config":
            return config_select
        if selector == "#experiment-summary":
            return SimpleNamespace(update=summary_updates.append)
        if selector == "#experiment-status-text":
            return SimpleNamespace(update=status_updates.append)
        raise AssertionError(selector)

    monkeypatch.setattr(view, "query_one", query_one)
    monkeypatch.setattr(
        experiments_view,
        "list_experiment_config_summaries",
        lambda: [new_a, new_b, new_c],
    )

    view.refresh_summaries()

    assert view.summaries == [new_a, new_b, new_c]
    assert len(config_select.options) == 3
    assert config_select.value == str(new_b.path)
    assert "new b" in summary_updates[-1]
    assert status_updates == ["Config list refreshed."]


def test_experiments_view_selected_summary_uses_select_value(monkeypatch) -> None:
    from pathlib import Path
    from orchestrator.control import ExperimentConfigSummary
    from orchestrator.tui.views.experiments_view import ExperimentsView

    def summary(path: str, name: str) -> ExperimentConfigSummary:
        return ExperimentConfigSummary(
            path=Path(path),
            name=name,
            description=None,
            target_file=None,
            solver_id="solver",
            variants_count=1,
            total_iterations=1,
            baseline_run_dir=None,
            reporting_enabled=True,
            providers=[],
            models=[],
            status="ok",
            message=None,
        )

    first = summary("/configs/a.json", "a")
    second = summary("/configs/b.json", "b")
    view = ExperimentsView()
    view.summaries = [first, second]
    monkeypatch.setattr(
        view,
        "query_one",
        lambda *args, **kwargs: SimpleNamespace(value=str(second.path)),
    )

    assert view._selected_summary() == second


def test_experiments_view_start_uses_selected_config_from_select(monkeypatch) -> None:
    from pathlib import Path
    from orchestrator.control import ExperimentConfigSummary
    from orchestrator.tui.views.experiments_view import ExperimentsView

    selected_path = Path("/configs/selected.json")
    view = ExperimentsView()
    view.summaries = [
        ExperimentConfigSummary(
            path=Path("/configs/first.json"),
            name="first",
            description=None,
            target_file=None,
            solver_id="solver",
            variants_count=1,
            total_iterations=1,
            baseline_run_dir=None,
            reporting_enabled=True,
            providers=[],
            models=[],
            status="ok",
            message=None,
        ),
        ExperimentConfigSummary(
            path=selected_path,
            name="selected",
            description=None,
            target_file=None,
            solver_id="solver",
            variants_count=1,
            total_iterations=1,
            baseline_run_dir=None,
            reporting_enabled=True,
            providers=[],
            models=[],
            status="ok",
            message=None,
        ),
    ]
    start_calls: list[tuple] = []
    mock_manager = SimpleNamespace(
        start_experiment=lambda config_path, dry_run: start_calls.append((config_path, dry_run)) or "run_001",
    )
    monkeypatch.setattr(view, "_can_start", True)
    monkeypatch.setattr(
        view,
        "query_one",
        lambda *args, **kwargs: SimpleNamespace(
            value=str(selected_path),
            update=lambda _text: None,
        ),
    )
    monkeypatch.setattr(
        ExperimentsView,
        "app",
        SimpleNamespace(active_runs_manager=mock_manager),
    )

    view._start_experiment(dry_run=True)

    assert start_calls == [(selected_path, True)]


def test_baseline_view_refresh_preserves_selected_solver(monkeypatch) -> None:
    import orchestrator.tui.views.baseline_view as baseline_view
    from orchestrator.tui.views.baseline_view import BaselineView

    view = BaselineView()
    select = SimpleNamespace(value="solver_b", options=[])
    select.set_options = lambda options: setattr(select, "options", options)
    statuses: list[str] = []

    monkeypatch.setattr(
        baseline_view,
        "_solver_select_options",
        lambda: ([('Solver A', 'solver_a'), ('Solver B', 'solver_b')], 'solver_a'),
    )

    def query_one(selector, *args, **kwargs):
        if selector == "#baseline-solver":
            return select
        if selector == "#baseline-status":
            return SimpleNamespace(update=statuses.append)
        raise AssertionError(selector)

    monkeypatch.setattr(view, "query_one", query_one)

    view._refresh_solvers()

    assert select.value == "solver_b"
    assert statuses == ["Solver list refreshed."]


# ---------------------------------------------------------------------------
# MainScreen -- active runs sidebar mapping
# ---------------------------------------------------------------------------


def test_main_screen_active_run_selection_uses_stored_run_ids(monkeypatch) -> None:
    from orchestrator.tui.screens.active_run_screen import ActiveRunScreen
    from orchestrator.tui.screens.main_screen import MainScreen

    screen = MainScreen()
    screen._active_run_ids = ["run_002"]
    pushed_screens: list[object] = []

    def fail_list():
        raise AssertionError("manager.list() should not be called for selection")

    monkeypatch.setattr(
        MainScreen,
        "app",
        SimpleNamespace(
            active_runs_manager=SimpleNamespace(list=fail_list),
            push_screen=lambda screen_obj: pushed_screens.append(screen_obj),
        ),
    )

    screen._handle_active_run_selection(
        SimpleNamespace(list_view=SimpleNamespace(index=0))
    )

    assert len(pushed_screens) == 1
    assert isinstance(pushed_screens[0], ActiveRunScreen)
    assert pushed_screens[0]._run_id == "run_002"


def test_main_screen_active_run_selection_prefers_item_mapping(monkeypatch) -> None:
    from orchestrator.tui.screens.active_run_screen import ActiveRunScreen
    from orchestrator.tui.screens.main_screen import MainScreen

    screen = MainScreen()
    selected_item = object()
    screen._active_run_ids = ["wrong_run"]
    screen._active_run_item_to_id = {id(selected_item): "mapped_run"}
    pushed_screens: list[object] = []

    monkeypatch.setattr(
        MainScreen,
        "app",
        SimpleNamespace(push_screen=lambda screen_obj: pushed_screens.append(screen_obj)),
    )

    screen._handle_active_run_selection(
        SimpleNamespace(item=selected_item, list_view=SimpleNamespace(index=0))
    )

    assert len(pushed_screens) == 1
    assert isinstance(pushed_screens[0], ActiveRunScreen)
    assert pushed_screens[0]._run_id == "mapped_run"


def test_main_screen_active_run_refresh_updates_labels_without_rebuild(monkeypatch) -> None:
    from datetime import datetime
    from pathlib import Path
    from orchestrator.tui.screens.main_screen import MainScreen

    screen = MainScreen()
    screen._active_run_ids = ["run_001"]
    updates: list[str] = []
    screen._active_run_labels = {"run_001": SimpleNamespace(update=updates.append)}
    list_view = SimpleNamespace(index=0, clear=lambda: (_ for _ in ()).throw(AssertionError("rebuild")))
    run = SimpleNamespace(
        run_id="run_001",
        kind="experiment",
        config_path=Path("configs/experiments/a.json"),
        dry_run=True,
        status="running",
        started_at=datetime.now().astimezone(),
        finished_at=None,
    )
    manager = SimpleNamespace(list=lambda: [run], active_count=lambda: 1)

    monkeypatch.setattr(MainScreen, "app", SimpleNamespace(active_runs_manager=manager))
    monkeypatch.setattr(screen, "query_one", lambda selector, *args, **kwargs: list_view)
    monkeypatch.setattr(screen, "_update_active_run_count", lambda count: None)
    monkeypatch.setattr(screen, "_sync_active_runs_timer", lambda count: None)

    screen._refresh_active_runs()

    assert updates


def test_main_screen_global_refresh_calls_refreshable_views(monkeypatch) -> None:
    from orchestrator.tui.screens.main_screen import MainScreen

    screen = MainScreen()
    calls: list[str] = []
    refreshable = SimpleNamespace(refresh_view=lambda: calls.append("view"))
    static_view = SimpleNamespace()
    content = SimpleNamespace(children=[refreshable, static_view])

    monkeypatch.setattr(screen, "query_one", lambda selector, *args, **kwargs: content)
    monkeypatch.setattr(screen, "_refresh_active_runs", lambda: calls.append("active-runs"))

    screen.action_global_refresh()

    assert calls == ["view", "active-runs"]


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
