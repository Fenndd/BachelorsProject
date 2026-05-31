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


@pytestmark_windows
def test_candidate_evaluation_lock_cross_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(queue, "RETRY_SLEEP_SECONDS", 0.01)

    repo_root = Path(__file__).resolve().parents[3]

    script_path = tmp_path / "_cross_process_lock_test.py"
    script_path.write_text(f'''
import sys
sys.path.insert(0, {str(repo_root)!r})
import time
from pathlib import Path
from orchestrator.control.candidate_evaluation_queue import candidate_evaluation_lock

mode = sys.argv[1]
workspace = Path(sys.argv[2])

if mode == "holder":
    with candidate_evaluation_lock(experiment_id="test", iteration=1, workspace_root=workspace):
        (workspace / "holder_acquired").write_text("")
        release_file = workspace / "release_holder"
        while not release_file.exists():
            time.sleep(0.01)

elif mode == "waiter":
    while not (workspace / "holder_acquired").exists():
        time.sleep(0.01)
    with candidate_evaluation_lock(experiment_id="test", iteration=2, workspace_root=workspace):
        (workspace / "waiter_acquired").write_text("")
'''.lstrip(), encoding="utf-8")

    import subprocess
    import sys as _sys

    holder = subprocess.Popen(
        [_sys.executable, str(script_path), "holder", str(workspace)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )

    waited = 0.0
    while not (workspace / "holder_acquired").exists():
        if holder.poll() is not None:
            _, stderr = holder.communicate()
            pytest.fail(f"Holder process exited early with code {holder.returncode}: {stderr.decode()}")
        time.sleep(0.01)
        waited += 0.01
        if waited > 10.0:
            holder.kill()
            holder.wait()
            pytest.fail("Holder did not acquire lock within 10 seconds")

    waiter = subprocess.Popen(
        [_sys.executable, str(script_path), "waiter", str(workspace)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
    )

    time.sleep(0.3)
    assert not (workspace / "waiter_acquired").exists(), (
        "Waiter entered critical section while holder still holds the lock"
    )

    (workspace / "release_holder").write_text("")

    waited = 0.0
    while not (workspace / "waiter_acquired").exists():
        if waiter.poll() is not None:
            _, stderr = waiter.communicate()
            pytest.fail(f"Waiter process exited early with code {waiter.returncode}: {stderr.decode()}")
        time.sleep(0.1)
        waited += 0.1
        if waited > 10.0:
            holder.kill()
            waiter.kill()
            holder.wait()
            waiter.wait()
            pytest.fail("Waiter did not acquire lock within 10 seconds after holder release")

    assert (workspace / "waiter_acquired").exists(), (
        "Waiter should have entered critical section after holder released the lock"
    )

    holder.wait(timeout=5)
    waiter.wait(timeout=5)
    assert holder.returncode == 0, f"Holder exited with code {holder.returncode}"
    assert waiter.returncode == 0, f"Waiter exited with code {waiter.returncode}"
