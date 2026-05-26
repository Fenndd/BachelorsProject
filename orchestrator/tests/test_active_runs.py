"""Tests for ActiveRunsManager lifecycle.

Tests the model via direct construction and mock-application paths.
No subprocesses are spawned.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

import orchestrator.tui.active_runs as active_runs
from orchestrator.tui.active_runs import (
    ActiveRun,
    ActiveRunSummary,
    ActiveRunsManager,
)


# ---------------------------------------------------------------------------
# ActiveRun model tests
# ---------------------------------------------------------------------------


def test_active_run_initializes_with_starting_status() -> None:
    run = ActiveRun(
        run_id="run_001",
        config_path=Path("configs/experiments/test.json"),
        dry_run=False,
        command=["py", "-m", "test"],
        started_at=datetime.now().astimezone(),
    )

    assert run.run_id == "run_001"
    assert run.kind == "experiment"
    assert run.status == "starting"
    assert run.exit_code is None
    assert run.finished_at is None
    assert run.message == ""
    assert run.latest_result_dir is None
    assert run.latest_experiment_dir is None
    assert len(run.output_buffer) == 0
    assert not run.cancel_requested.is_set()


def test_active_run_summary() -> None:
    started = datetime.now().astimezone()
    run = ActiveRun(
        run_id="run_001",
        config_path=Path("configs/experiments/test.json"),
        dry_run=True,
        command=["py", "-m", "test", "--dry-run"],
        started_at=started,
    )

    summary = run.summary()

    assert isinstance(summary, ActiveRunSummary)
    assert summary.run_id == "run_001"
    assert summary.kind == "experiment"
    assert summary.config_path == Path("configs/experiments/test.json")
    assert summary.dry_run is True
    assert summary.status == "starting"
    assert summary.started_at is started
    assert summary.finished_at is None
    assert summary.exit_code is None
    assert summary.latest_result_dir is None
    assert summary.latest_experiment_dir is None


def test_active_run_output_buffer_bounded() -> None:
    run = ActiveRun(
        run_id="run_001",
        config_path=Path("test.json"),
        dry_run=False,
        command=["echo"],
        started_at=datetime.now().astimezone(),
    )

    for i in range(2500):
        run.output_buffer.append(("stdout", f"line {i}"))

    assert len(run.output_buffer) == 2000
    assert run.output_buffer[0][1] == "line 500"


def test_active_run_cancel_requested() -> None:
    run = ActiveRun(
        run_id="run_001",
        config_path=Path("test.json"),
        dry_run=False,
        command=["echo"],
        started_at=datetime.now().astimezone(),
    )

    assert not run.cancel_requested.is_set()
    run.cancel_requested.set()
    assert run.cancel_requested.is_set()


# ---------------------------------------------------------------------------
# ActiveRunsManager tests
# ---------------------------------------------------------------------------


def _make_mock_app(run_worker_calls: list | None = None):
    app = SimpleNamespace()
    if run_worker_calls is not None:
        app.run_worker = lambda fn, thread=False, exit_on_error=False, exclusive=False: run_worker_calls.append(fn)
    else:
        app.run_worker = MagicMock()
    app.call_from_thread = lambda fn: fn()
    return app


def test_manager_creates_run_with_sequential_ids() -> None:
    worker_calls: list = []
    app = _make_mock_app(run_worker_calls=worker_calls)
    manager = ActiveRunsManager(app)

    id1 = manager.start(Path("configs/experiments/a.json"), dry_run=False)
    id2 = manager.start(Path("configs/experiments/b.json"), dry_run=True)

    assert id1 == "run_001"
    assert id2 == "run_002"
    assert len(worker_calls) == 2


def test_manager_start_experiment_preserves_experiment_behavior() -> None:
    worker_calls: list = []
    app = _make_mock_app(run_worker_calls=worker_calls)
    manager = ActiveRunsManager(app)

    run_id = manager.start_experiment(Path("configs/experiments/a.json"), dry_run=True)
    run = manager.get(run_id)

    assert run is not None
    assert run.kind == "experiment"
    assert run.config_path == Path("configs/experiments/a.json")
    assert run.dry_run is True
    assert "orchestrator.experiments.run_experiment" in run.command
    assert "--dry-run" in run.command


def test_manager_start_baseline_creates_baseline_run() -> None:
    worker_calls: list = []
    app = _make_mock_app(run_worker_calls=worker_calls)
    manager = ActiveRunsManager(app)

    run_id = manager.start_baseline(solver_id="poselib_p3p")
    run = manager.get(run_id)

    assert run is not None
    assert run.kind == "baseline"
    assert run.config_path == Path("<baseline>")
    assert run.dry_run is False
    assert "orchestrator.cli.main" in run.command
    assert run.command[-2:] == ["--solver", "poselib_p3p"]


def test_manager_start_notifies_global_subscribers_immediately() -> None:
    worker_calls: list = []
    app = _make_mock_app(run_worker_calls=worker_calls)
    manager = ActiveRunsManager(app)
    calls: list[bool] = []

    manager.attach_global(lambda: calls.append(True))

    manager.start_experiment(Path("configs/experiments/a.json"), dry_run=True)

    assert calls == [True]


def test_manager_start_failure_without_worker_notifies_global_subscribers() -> None:
    app = SimpleNamespace(call_from_thread=lambda fn: fn())
    manager = ActiveRunsManager(app)
    calls: list[bool] = []

    manager.attach_global(lambda: calls.append(True))
    run_id = manager.start_baseline()
    run = manager.get(run_id)

    assert run is not None
    assert run.status == "failed"
    assert calls == [True]


def test_manager_stores_worker_handle() -> None:
    app = SimpleNamespace()
    app.run_worker = lambda *args, **kwargs: "worker-handle"
    app.call_from_thread = lambda fn: fn()
    manager = ActiveRunsManager(app)

    run_id = manager.start(Path("configs/experiments/a.json"), dry_run=False)
    run = manager.get(run_id)

    assert run is not None
    assert run.worker_handle == "worker-handle"


def test_manager_get_returns_run() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)
    run_id = manager.start(Path("configs/experiments/test.json"), dry_run=False)

    run = manager.get(run_id)
    assert run is not None
    assert run.run_id == run_id
    assert run.status == "starting"


def test_manager_get_returns_none_for_unknown_run() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    assert manager.get("nonexistent") is None


def test_manager_list_returns_summaries() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    manager.start(Path("configs/experiments/a.json"), dry_run=False)
    manager.start(Path("configs/experiments/b.json"), dry_run=True)

    summaries = manager.list()
    assert len(summaries) == 2
    assert all(isinstance(s, ActiveRunSummary) for s in summaries)
    run_ids = {s.run_id for s in summaries}
    assert run_ids == {"run_001", "run_002"}
    assert {s.kind for s in summaries} == {"experiment"}


def test_manager_active_count_counts_starting_and_running_only() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    manager.start(Path("a.json"), dry_run=False)

    assert manager.active_count() == 1

    run = manager.get("run_001")
    assert run is not None
    run.status = "running"
    assert manager.active_count() == 1

    run.status = "succeeded"
    assert manager.active_count() == 0

    run.status = "failed"
    assert manager.active_count() == 0

    run.status = "cancelled"
    assert manager.active_count() == 0


def test_manager_active_count_includes_baseline_runs() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    manager.start_baseline()

    assert manager.active_count() == 1


def test_manager_clear_finished_removes_only_terminal_runs() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    running_id = manager.start(Path("running.json"), dry_run=False)
    succeeded_id = manager.start(Path("succeeded.json"), dry_run=False)
    failed_id = manager.start(Path("failed.json"), dry_run=False)
    cancelled_id = manager.start_baseline()

    running = manager.get(running_id)
    succeeded = manager.get(succeeded_id)
    failed = manager.get(failed_id)
    cancelled = manager.get(cancelled_id)
    assert running is not None
    assert succeeded is not None
    assert failed is not None
    assert cancelled is not None
    running.status = "running"
    succeeded.status = "succeeded"
    failed.status = "failed"
    cancelled.status = "cancelled"

    global_calls: list[bool] = []
    manager.attach_global(lambda: global_calls.append(True))

    removed = manager.clear_finished()

    assert removed == 3
    assert manager.get(running_id) is running
    assert manager.get(succeeded_id) is None
    assert manager.get(failed_id) is None
    assert manager.get(cancelled_id) is None
    assert global_calls == [True]


def test_manager_finished_history_limit_keeps_running_runs() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)
    now = datetime.now().astimezone()

    running_id = manager.start(Path("running.json"), dry_run=False)
    running = manager.get(running_id)
    assert running is not None
    running.status = "running"

    for index in range(25):
        run_id = manager.start(Path(f"finished_{index}.json"), dry_run=False)
        run = manager.get(run_id)
        assert run is not None
        run.status = "succeeded"
        run.finished_at = now + timedelta(seconds=index)

    summaries = manager.list()

    assert any(summary.run_id == running_id for summary in summaries)
    assert sum(1 for summary in summaries if summary.status == "succeeded") == 20
    assert manager.active_count() == 1


def test_manager_cancel_sets_event() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    manager.start(Path("test.json"), dry_run=False)
    run = manager.get("run_001")
    assert run is not None

    assert not run.cancel_requested.is_set()
    manager.cancel("run_001")
    assert run.cancel_requested.is_set()


def test_manager_cancel_all_sets_all_events() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    manager.start(Path("a.json"), dry_run=False)
    manager.start_baseline()

    manager.cancel_all()

    for run_id in ("run_001", "run_002"):
        r = manager.get(run_id)
        assert r is not None
        assert r.cancel_requested.is_set()


def test_manager_attach_detach_subscriber() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    manager.start(Path("test.json"), dry_run=False)
    run = manager.get("run_001")
    assert run is not None

    calls: list[tuple[str | None, str | None]] = []

    def subscriber(stream_name, line):
        calls.append((stream_name, line))

    manager.attach("run_001", subscriber)
    assert subscriber in run._subscribers

    manager.detach("run_001", subscriber)
    assert subscriber not in run._subscribers


def test_manager_cancel_nonexistent_run_is_noop() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    manager.cancel("nonexistent")


def test_manager_detach_nonexistent_run_is_noop() -> None:
    app = _make_mock_app()
    manager = ActiveRunsManager(app)

    def cb(s, l):
        pass

    manager.detach("nonexistent", cb)


def test_manager_worker_maps_experiment_result(monkeypatch) -> None:
    worker_calls: list = []
    app = _make_mock_app(run_worker_calls=worker_calls)
    manager = ActiveRunsManager(app)
    result_dir = Path("results/experiments/fake")

    def fake_runner(
        config_path,
        dry_run=False,
        repo_root=None,
        require_api_key=True,
        on_stdout=None,
        on_stderr=None,
        cancel_event=None,
        on_process_started=None,
    ):
        assert config_path == Path("configs/experiments/test.json")
        assert dry_run is True
        assert cancel_event is not None
        if on_process_started is not None:
            on_process_started("fake-process")
        if on_stdout is not None:
            on_stdout("experiment out")
        if on_stderr is not None:
            on_stderr("experiment err")
        return SimpleNamespace(
            status="success",
            exit_code=0,
            message="Experiment completed successfully.",
            latest_experiment_dir=result_dir,
        )

    monkeypatch.setattr(active_runs, "run_experiment_control", fake_runner)
    run_id = manager.start_experiment(Path("configs/experiments/test.json"), dry_run=True)

    worker_calls[0]()
    run = manager.get(run_id)

    assert run is not None
    assert run.status == "succeeded"
    assert run.exit_code == 0
    assert run.message == "Experiment completed successfully."
    assert run.latest_result_dir == result_dir
    assert run.latest_experiment_dir == result_dir
    assert run.process == "fake-process"
    assert list(run.output_buffer) == [
        ("stdout", "experiment out"),
        ("stderr", "experiment err"),
    ]


def test_manager_worker_maps_baseline_result(monkeypatch) -> None:
    worker_calls: list = []
    app = _make_mock_app(run_worker_calls=worker_calls)
    manager = ActiveRunsManager(app)
    result_dir = Path("results/runs/fake")

    def fake_run_baseline(
        repo_root=None,
        on_stdout=None,
        on_stderr=None,
        solver_id=None,
        cancel_event=None,
        on_process_started=None,
    ):
        assert solver_id == "poselib_p3p"
        assert cancel_event is not None
        if on_process_started is not None:
            on_process_started("fake-process")
        if on_stdout is not None:
            on_stdout("baseline out")
        if on_stderr is not None:
            on_stderr("baseline err")
        return SimpleNamespace(
            status="success",
            exit_code=0,
            message="Baseline completed successfully.",
            latest_run_dir=result_dir,
        )

    monkeypatch.setattr(active_runs, "run_baseline", fake_run_baseline)
    run_id = manager.start_baseline(solver_id="poselib_p3p")

    worker_calls[0]()
    run = manager.get(run_id)

    assert run is not None
    assert run.kind == "baseline"
    assert run.status == "succeeded"
    assert run.exit_code == 0
    assert run.message == "Baseline completed successfully."
    assert run.latest_result_dir == result_dir
    assert run.latest_experiment_dir is None
    assert run.process == "fake-process"
    assert list(run.output_buffer) == [
        ("stdout", "baseline out"),
        ("stderr", "baseline err"),
    ]
