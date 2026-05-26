from __future__ import annotations

import asyncio

import pytest
from types import SimpleNamespace

pytestmark = pytest.mark.unit

from orchestrator.tui import debug_log
from orchestrator.tui.app import OptimizerTuiApp, QuitConfirmScreen
from orchestrator.tui.active_runs import ActiveRunsManager, ActiveRun, ActiveRunStatus
from orchestrator.tui.screens.baseline_screen import BaselineScreen
from orchestrator.tui.screens.experiment_screen import ExperimentScreen


class _FakeTimer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


# ---------------------------------------------------------------------------
# App process guard (BaselineScreen backward compat)
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
# BaselineScreen (unchanged behavior)
# ---------------------------------------------------------------------------


def test_baseline_back_is_blocked_while_active(monkeypatch) -> None:
    screen = BaselineScreen()
    messages: list[str] = []

    monkeypatch.setattr(screen, "_set_status_message", messages.append)
    screen._state = "running"

    screen.action_request_back()

    assert messages == [
        "Baseline is still running. Wait until it finishes before leaving this screen."
    ]


def test_baseline_back_is_not_blocked_when_inactive(monkeypatch) -> None:
    screen = BaselineScreen()
    popped: list[bool] = []

    monkeypatch.setattr(BaselineScreen, "app", SimpleNamespace(pop_screen=lambda: popped.append(True)))
    screen._state = "failed"

    screen.action_request_back()

    assert popped == [True]


def test_baseline_screen_initializes_queues_and_timer() -> None:
    screen = BaselineScreen()

    assert screen._state == "idle"
    assert not screen._can_start
    assert not screen._process_registered
    assert not screen._is_active()
    assert screen._log_queue.empty()
    assert screen._result_queue.empty()
    assert screen._drain_timer is None
    assert screen._watchdog_timer is None


def test_baseline_start_before_ready_is_ignored(monkeypatch) -> None:
    screen = BaselineScreen()
    statuses: list[str] = []

    monkeypatch.setattr(screen, "_set_status_message", statuses.append)

    screen._start_baseline()

    assert screen._state == "idle"
    assert not screen._process_registered
    assert statuses == ["Status: screen initializing, try again"]


def test_baseline_drain_queues_appends_logs(monkeypatch) -> None:
    screen = BaselineScreen()
    appended: list[tuple[str, str]] = []

    monkeypatch.setattr(
        screen,
        "_append_log",
        lambda line, stream_name: appended.append((stream_name, line)),
    )
    screen._log_queue.put(("stdout", "baseline out"))
    screen._log_queue.put(("stderr", "baseline err"))

    screen._drain_queues()

    assert appended == [
        ("stdout", "baseline out"),
        ("stderr", "baseline err"),
    ]


def test_baseline_drain_queues_applies_result(monkeypatch) -> None:
    screen = BaselineScreen()
    results: list[str] = []

    monkeypatch.setattr(screen, "_set_result", results.append)
    screen._result_queue.put("Status: success")

    screen._drain_queues()

    assert results == ["Status: success"]


def test_baseline_stop_drain_timer_stops_and_clears_timer() -> None:
    screen = BaselineScreen()
    timer = _FakeTimer()
    screen._drain_timer = timer

    screen._stop_drain_timer()

    assert timer.stopped
    assert screen._drain_timer is None


def test_baseline_force_unlock_clears_active_state(monkeypatch) -> None:
    screen = BaselineScreen()
    button = SimpleNamespace(disabled=True)
    statuses: list[str] = []
    unregistered: list[bool] = []

    screen._state = "running"
    screen._process_registered = True
    monkeypatch.setattr(screen, "query_one", lambda *args, **kwargs: button)
    monkeypatch.setattr(screen, "_set_status_message", statuses.append)
    monkeypatch.setattr(screen, "_unregister_process", lambda: unregistered.append(True))

    screen._force_unlock()

    assert screen._state == "failed"
    assert not button.disabled
    assert unregistered == [True]
    assert statuses == [
        "Status: force-unlocked. Check workspace/tui_debug.log and Task Manager for leftover python processes."
    ]


# ---------------------------------------------------------------------------
# ExperimentScreen (refactored — no queues, no timers, no back blocking)
# ---------------------------------------------------------------------------


def test_experiment_back_is_never_blocked(monkeypatch) -> None:
    screen = ExperimentScreen()
    popped: list[bool] = []

    monkeypatch.setattr(ExperimentScreen, "app", SimpleNamespace(pop_screen=lambda: popped.append(True)))

    screen.action_request_back()
    assert popped == [True]


def test_experiment_screen_initializes_without_queues_or_timers() -> None:
    screen = ExperimentScreen()

    assert not screen._can_start
    assert not hasattr(screen, "_state")
    assert not hasattr(screen, "_process_registered")
    assert not hasattr(screen, "_log_queue")
    assert not hasattr(screen, "_result_queue")
    assert not hasattr(screen, "_drain_timer")
    assert not hasattr(screen, "_watchdog_timer")


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


def test_experiment_start_before_ready_is_ignored(monkeypatch) -> None:
    screen = ExperimentScreen()
    statuses: list[str] = []

    monkeypatch.setattr(screen, "_set_status_message", statuses.append)

    screen._start_experiment(dry_run=True)

    assert statuses == ["Screen initializing, try again."]


def test_experiment_real_run_shows_confirm_modal(monkeypatch) -> None:
    from pathlib import Path
    from orchestrator.tui.screens._confirm_paid_run import ConfirmPaidRunScreen

    screen = ExperimentScreen()
    pushed_screens: list[object] = []
    fake_path = Path("/fake/config.json")

    screen._can_start = True
    monkeypatch.setattr(screen, "_selected_summary", lambda: SimpleNamespace(path=fake_path))
    monkeypatch.setattr(
        ExperimentScreen,
        "app",
        SimpleNamespace(push_screen=lambda s, callback=None: pushed_screens.append(s)),
    )

    screen._request_real_run()

    assert len(pushed_screens) == 1
    assert isinstance(pushed_screens[0], ConfirmPaidRunScreen)


def test_experiment_on_list_view_highlighted_updates_summary(monkeypatch) -> None:
    screen = ExperimentScreen()
    updates: list[str] = []
    summary_widget = SimpleNamespace(update=updates.append)

    monkeypatch.setattr(screen, "_selected_summary", lambda: None)
    monkeypatch.setattr(screen, "query_one", lambda *args, **kwargs: summary_widget)

    screen.on_list_view_highlighted(SimpleNamespace())

    assert len(updates) == 1
