from __future__ import annotations

from types import SimpleNamespace

from orchestrator.tui import debug_log
from orchestrator.tui.app import OptimizerTuiApp
from orchestrator.tui.screens.baseline_screen import BaselineScreen
from orchestrator.tui.screens.experiment_screen import ExperimentScreen


class _FakeTimer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


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


def test_optimizer_tui_quit_is_blocked_with_active_process(
    monkeypatch,
) -> None:
    app = OptimizerTuiApp()
    notifications: list[tuple[str, str | None]] = []
    exits: list[bool] = []

    def fake_notify(self, message: str, severity: str | None = None) -> None:
        notifications.append((message, severity))

    def fake_exit(self) -> None:
        exits.append(True)

    monkeypatch.setattr(OptimizerTuiApp, "notify", fake_notify)
    monkeypatch.setattr(OptimizerTuiApp, "exit", fake_exit)

    app.register_process()
    app.action_quit()

    assert not exits
    assert notifications
    assert "still active" in notifications[0][0]
    assert notifications[0][1] == "warning"


def test_optimizer_tui_quit_exits_without_active_process(monkeypatch) -> None:
    app = OptimizerTuiApp()
    exits: list[bool] = []

    def fake_exit(self) -> None:
        exits.append(True)

    monkeypatch.setattr(OptimizerTuiApp, "exit", fake_exit)

    app.action_quit()

    assert exits == [True]


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


def test_experiment_back_is_blocked_while_running(monkeypatch) -> None:
    screen = ExperimentScreen()
    messages: list[str] = []

    monkeypatch.setattr(screen, "_set_status_message", messages.append)
    screen._running = True

    screen.action_request_back()

    assert messages == [
        "Experiment is still running. Wait until it finishes before leaving this screen."
    ]


def test_experiment_screen_initializes_queues_and_timer() -> None:
    screen = ExperimentScreen()

    assert screen._log_queue.empty()
    assert screen._result_queue.empty()
    assert screen._drain_timer is None


def test_experiment_drain_queues_appends_logs(monkeypatch) -> None:
    screen = ExperimentScreen()
    appended: list[tuple[str, str]] = []

    monkeypatch.setattr(
        screen,
        "_append_log",
        lambda line, stream_name: appended.append((stream_name, line)),
    )
    screen._log_queue.put(("stdout", "experiment out"))
    screen._log_queue.put(("stderr", "experiment err"))

    screen._drain_queues()

    assert appended == [
        ("stdout", "experiment out"),
        ("stderr", "experiment err"),
    ]


def test_experiment_drain_queues_applies_result(monkeypatch) -> None:
    screen = ExperimentScreen()
    results: list[str] = []

    monkeypatch.setattr(screen, "_set_result", results.append)
    screen._result_queue.put("Status: failed")

    screen._drain_queues()

    assert results == ["Status: failed"]


def test_experiment_stop_drain_timer_stops_and_clears_timer() -> None:
    screen = ExperimentScreen()
    timer = _FakeTimer()
    screen._drain_timer = timer

    screen._stop_drain_timer()

    assert timer.stopped
    assert screen._drain_timer is None
