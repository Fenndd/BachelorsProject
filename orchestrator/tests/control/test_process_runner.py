from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from orchestrator.control.process_runner import ProcessLaunchError, run_streaming_command


def test_process_runner_streams_successful_python_command(tmp_path: Path) -> None:
    stdout_lines: list[str] = []

    result = run_streaming_command(
        [sys.executable, "-c", "print('hello from runner')"],
        tmp_path,
        on_stdout=stdout_lines.append,
    )

    assert result.exit_code == 0
    assert stdout_lines == ["hello from runner"]


def test_process_runner_returns_nonzero_for_failing_python_command(tmp_path: Path) -> None:
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    result = run_streaming_command(
        [
            sys.executable,
            "-c",
            "import sys; print('before fail'); print('bad', file=sys.stderr); sys.exit(7)",
        ],
        tmp_path,
        on_stdout=stdout_lines.append,
        on_stderr=stderr_lines.append,
    )

    assert result.exit_code == 7
    assert "before fail" in stdout_lines
    assert "bad" in stderr_lines


def test_process_runner_raises_controlled_error_for_missing_executable(tmp_path: Path) -> None:
    with pytest.raises(ProcessLaunchError, match="Command executable not found"):
        run_streaming_command(["definitely_missing_executable_for_test"], tmp_path)


def test_run_streaming_command_cancellation(tmp_path: Path) -> None:
    cancel_event = threading.Event()
    started = time.perf_counter()

    def delayed_cancel():
        time.sleep(0.3)
        cancel_event.set()

    threading.Thread(target=delayed_cancel, daemon=True).start()

    result = run_streaming_command(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        tmp_path,
        cancel_event=cancel_event,
    )

    elapsed = time.perf_counter() - started
    assert elapsed < 10.0, f"cancellation took too long: {elapsed:.1f}s"
    assert result.exit_code is not None
    assert result.exit_code != 0


def test_run_streaming_command_on_process_started(tmp_path: Path) -> None:
    started_processes: list[subprocess.Popen] = []

    def on_process_started(process: subprocess.Popen) -> None:
        started_processes.append(process)

    result = run_streaming_command(
        [sys.executable, "-c", "print('ok')"],
        tmp_path,
        on_process_started=on_process_started,
    )

    assert result.exit_code == 0
    assert len(started_processes) == 1
    assert isinstance(started_processes[0], subprocess.Popen)
    assert started_processes[0].returncode == 0
