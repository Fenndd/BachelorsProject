"""Tests for :mod:`orchestrator.shared.process.step_runner`."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from orchestrator.shared.process.step_runner import (
    StepResult,
    StepRunner,
    format_command,
)


class TestFormatCommand:
    def test_simple_command(self) -> None:
        assert format_command(["cmake", "--version"]) == "cmake --version"

    def test_command_with_spaces(self) -> None:
        result = format_command(["cmake", "--build", "my build dir"])
        assert '"my build dir"' in result

    def test_empty_sequence(self) -> None:
        assert format_command([]) == ""

    def test_string_input_passthrough(self) -> None:
        assert format_command("some arbitrary string") == "some arbitrary string"

    def test_single_element(self) -> None:
        assert format_command(["echo"]) == "echo"


class TestStepRunner:
    def test_run_successful_command(self, tmp_path: Path) -> None:
        runner = StepRunner()
        result = runner.run_step(
            label="test_success",
            cmd=[sys.executable, "-c", "print('hello')"],
            cwd=tmp_path,
        )

        assert result.name == "test_success"
        assert result.status == "success"
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.error_message is None

    def test_run_failing_command(self, tmp_path: Path) -> None:
        runner = StepRunner()
        result = runner.run_step(
            label="test_fail",
            cmd=[sys.executable, "-c", "import sys; sys.exit(3)"],
            cwd=tmp_path,
        )

        assert result.status == "failed"
        assert result.exit_code == 3
        assert result.error_message is not None
        assert "exit code 3" in result.error_message

    def test_run_missing_executable(self, tmp_path: Path) -> None:
        runner = StepRunner()
        result = runner.run_step(
            label="test_missing",
            cmd=["nonexistent_executable_xyz_123"],
            cwd=tmp_path,
        )

        assert result.status == "failed"
        assert result.exit_code is None
        assert "not found" in result.stderr.lower()

    def test_log_file_written(self, tmp_path: Path) -> None:
        log_path = tmp_path / "logs" / "test_step.log"
        runner = StepRunner()
        result = runner.run_step(
            label="log_test",
            cmd=[sys.executable, "-c", "print('log output')"],
            cwd=tmp_path,
            log_path=log_path,
        )

        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "STEP: log_test" in content
        assert "COMMAND:" in content
        assert "CWD:" in content
        assert "EXIT_CODE: 0" in content
        assert "STDOUT:" in content
        assert "log output" in content
        assert result.status == "success"

    def test_log_file_written_for_failure(self, tmp_path: Path) -> None:
        log_path = tmp_path / "fail.log"
        runner = StepRunner()
        runner.run_step(
            label="fail_log",
            cmd=[sys.executable, "-c", "import sys; sys.exit(5)"],
            cwd=tmp_path,
            log_path=log_path,
        )

        content = log_path.read_text(encoding="utf-8")
        assert "EXIT_CODE: 5" in content
        assert "STDERR:" in content

    def test_title_override(self, tmp_path: Path, capsys) -> None:
        runner = StepRunner()
        runner.run_step(
            label="internal_label",
            cmd=[sys.executable, "-c", "print('ok')"],
            cwd=tmp_path,
            title="Display Title",
        )

        captured = capsys.readouterr()
        assert "[STEP] Display Title" in captured.out

    def test_step_result_dataclass_fields(self) -> None:
        sr = StepResult(
            name="my_step",
            status="success",
            exit_code=0,
            duration_seconds=1.5,
            stdout="out",
            stderr="err",
            error_message=None,
        )

        assert sr.name == "my_step"
        assert sr.status == "success"
        assert sr.exit_code == 0
        assert sr.duration_seconds == 1.5
        assert sr.stdout == "out"
        assert sr.stderr == "err"
        assert sr.error_message is None

    def test_env_passed_to_subprocess(self, tmp_path: Path) -> None:
        runner = StepRunner()
        result = runner.run_step(
            label="env_test",
            cmd=[
                sys.executable,
                "-c",
                "import os; print(os.environ.get('TEST_VAR', 'NOT_SET'))",
            ],
            cwd=tmp_path,
            env={"TEST_VAR": "hello_env", "PATH": os.environ.get("PATH", "")},
        )

        assert "hello_env" in result.stdout

    def test_stderr_captured(self, tmp_path: Path) -> None:
        runner = StepRunner()
        result = runner.run_step(
            label="stderr_test",
            cmd=[
                sys.executable,
                "-c",
                "import sys; print('to_stderr', file=sys.stderr)",
            ],
            cwd=tmp_path,
        )

        assert "to_stderr" in result.stderr

    def test_oserror_handling(self, tmp_path: Path, monkeypatch) -> None:
        import subprocess as sp

        def fake_run(*args, **kwargs):
            raise OSError("simulated OS error")

        monkeypatch.setattr(sp, "run", fake_run)

        runner = StepRunner()
        result = runner.run_step(
            label="oserror_test",
            cmd=["some_cmd"],
            cwd=tmp_path,
        )

        assert result.status == "failed"
        assert result.exit_code is None
        assert "Could not start command" in result.stderr



