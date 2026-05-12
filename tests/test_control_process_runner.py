from __future__ import annotations

import sys
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
