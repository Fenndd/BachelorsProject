from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from orchestrator.control import candidate_evaluation_queue as queue
from orchestrator.control.candidate_evaluation_queue import candidate_evaluation_lock


pytestmark = pytest.mark.unit


pytestmark_windows = pytest.mark.skipif(
    os.name != "nt",
    reason="candidate evaluation queue uses Windows msvcrt locking",
)


@pytestmark_windows
def test_candidate_evaluation_lock_creates_lock_directory_and_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    with candidate_evaluation_lock(experiment_id="exp", iteration=1, workspace_root=workspace):
        assert (workspace / "locks").is_dir()
        assert (workspace / "locks" / "candidate_evaluation.lock").is_file()


@pytestmark_windows
def test_candidate_evaluation_lock_is_released_after_context_exit(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    with candidate_evaluation_lock(experiment_id="exp", iteration=1, workspace_root=workspace):
        pass

    with candidate_evaluation_lock(experiment_id="exp", iteration=2, workspace_root=workspace):
        assert True


@pytestmark_windows
def test_candidate_evaluation_lock_is_exclusive_and_waits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workspace = tmp_path / "workspace"
    entered = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []
    monkeypatch.setattr(queue, "RETRY_SLEEP_SECONDS", 0.01)

    def wait_for_lock() -> None:
        try:
            with candidate_evaluation_lock(experiment_id="exp", iteration=2, workspace_root=workspace):
                entered.set()
        except BaseException as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)
        finally:
            finished.set()

    with candidate_evaluation_lock(experiment_id="exp", iteration=1, workspace_root=workspace):
        thread = threading.Thread(target=wait_for_lock)
        thread.start()
        time.sleep(0.05)
        assert not entered.is_set()

    assert finished.wait(2.0)
    thread.join(timeout=2.0)
    assert entered.is_set()
    assert not errors
    assert "Waiting for candidate evaluation queue lock..." in capsys.readouterr().out


@pytestmark_windows
def test_candidate_evaluation_lock_wait_has_no_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    entered = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []
    monkeypatch.setattr(queue, "RETRY_SLEEP_SECONDS", 0.01)
    monkeypatch.setattr(queue, "WAIT_LOG_INTERVAL_SECONDS", 0.02)

    def wait_for_lock() -> None:
        try:
            with candidate_evaluation_lock(experiment_id="exp", iteration=2, workspace_root=workspace):
                entered.set()
        except BaseException as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)
        finally:
            finished.set()

    with candidate_evaluation_lock(experiment_id="exp", iteration=1, workspace_root=workspace):
        thread = threading.Thread(target=wait_for_lock)
        thread.start()
        time.sleep(0.08)
        assert not entered.is_set()
        assert not finished.is_set()

    assert finished.wait(2.0)
    thread.join(timeout=2.0)
    assert entered.is_set()
    assert not errors
