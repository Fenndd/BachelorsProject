"""Shared non-streaming process/step runner.

This module provides a reusable StepRunner for executing subprocess commands
with consistent output formatting, log writing, and error handling. It is the
non-streaming counterpart to :mod:`orchestrator.control.process_runner`, which
provides streaming execution via ``subprocess.Popen``.

Output policy:
  - Machine-readable stdout contracts use plain ``print``.
  - Diagnostics use ``logging``.
  - Low-level subprocess execution is quiet by default (``echo=False``).
  - Visible CLI progress must be explicitly requested (``echo=True``).
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass
class StepResult:
    name: str
    status: str
    exit_code: int | None
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""
    error_message: str | None = None


def format_command(command: Sequence[str] | str) -> str:
    """Format a command sequence as a display/log-friendly string."""
    if isinstance(command, str):
        return command
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


class StepRunner:
    """Run subprocess steps with consistent logging and error handling."""

    def run_step(
        self,
        label: str,
        cmd: Sequence[str],
        cwd: Path,
        *,
        title: str | None = None,
        env: dict[str, str] | None = None,
        log_path: Path | None = None,
        stream: bool = False,
        echo: bool = False,
    ) -> StepResult:
        """Execute a single step, returning a structured result.

        When *echo* is ``True`` prints ``[STEP]`` / ``[CMD ]`` / ``[CWD ]``
        headers and captured stdout/stderr.  When *echo* is ``False`` (the
        default) the step runs silently — stdout/stderr are still captured in
        the returned ``StepResult`` and written to *log_path* when provided.

        *stream* is reserved for future streaming support; this implementation
        always uses ``subprocess.run`` (non-streaming).
        """
        display_title = title if title is not None else label
        if echo:
            print(f"\n[STEP] {display_title}")
            print(f"[CMD ] {format_command(cmd)}")
            print(f"[CWD ] {cwd}")

        started = time.perf_counter()
        try:
            result = subprocess.run(
                list(cmd),
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            duration_seconds = round(time.perf_counter() - started, 3)
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except FileNotFoundError:
            duration_seconds = round(time.perf_counter() - started, 3)
            exit_code = None
            stdout = ""
            stderr = (
                f"Required command not found: '{cmd[0]}'. "
                "Make sure it is installed and available in PATH."
            )
        except OSError as exc:
            duration_seconds = round(time.perf_counter() - started, 3)
            exit_code = None
            stdout = ""
            stderr = f"Could not start command '{cmd[0]}': {exc}"

        if log_path is not None:
            self._write_log(log_path, label, cmd, cwd, exit_code, stdout, stderr)

        if echo:
            if stdout:
                print(stdout, end="" if stdout.endswith("\n") else "\n")
            if stderr:
                print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

        status = "success" if exit_code == 0 else "failed"
        error_message = None
        if exit_code is not None and exit_code != 0:
            error_message = (
                f"Step failed with exit code {exit_code}: {format_command(cmd)}"
            )
        elif exit_code is None:
            error_message = stderr

        return StepResult(
            name=label,
            status=status,
            exit_code=exit_code,
            duration_seconds=duration_seconds,
            stdout=stdout,
            stderr=stderr,
            error_message=error_message,
        )

    @staticmethod
    def _write_log(
        log_path: Path,
        step: str,
        command: Sequence[str] | str,
        cwd: Path,
        exit_code: int | None,
        stdout: str,
        stderr: str,
    ) -> None:
        command_text = (
            command if isinstance(command, str) else format_command(command)
        )
        lines = [
            f"STEP: {step}",
            f"COMMAND: {command_text}",
            f"CWD: {cwd}",
            f"EXIT_CODE: {exit_code}",
            "",
            "STDOUT:",
            stdout,
            "",
            "STDERR:",
            stderr,
            "",
        ]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(lines), encoding="utf-8")
