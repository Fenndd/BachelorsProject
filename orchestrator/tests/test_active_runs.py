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
    assert run.status == "starting"
    assert run.exit_code is None
    assert run.finished_at is None
    assert run.message == ""
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
    assert summary.config_path == Path("configs/experiments/test.json")
    assert summary.dry_run is True
    assert summary.status == "starting"
    assert summary.started_at is started
    assert summary.finished_at is None
    assert summary.exit_code is None
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
    manager.start(Path("b.json"), dry_run=True)

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
