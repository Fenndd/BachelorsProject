"""Generic subprocess streaming helpers for control-layer commands.

This module provides *streaming* execution via ``subprocess.Popen`` with
line-by-line stdout/stderr callbacks.  For non-streaming step execution with
structured StepResult returns, see :mod:`orchestrator.shared.process.step_runner`.
"""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    command: list[str]
    cwd: Path
    exit_code: int | None
    started_at: datetime
    finished_at: datetime
    duration_seconds: float


class ProcessLaunchError(RuntimeError):
    """Raised when a subprocess cannot be started."""


def _reader(
    stream,
    stream_name: str,
    output_queue: queue.Queue[tuple[str, str]],
) -> None:
    try:
        for line in iter(stream.readline, ""):
            output_queue.put((stream_name, line.rstrip("\r\n")))
    finally:
        stream.close()


def _terminate_process_tree(process: subprocess.Popen, grace_seconds: float = 2.0) -> None:
    """Best-effort termination of a subprocess and its children."""

    if process.poll() is not None:
        return

    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=grace_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            process.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=grace_seconds)
            return
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=grace_seconds)
                return
            except (OSError, subprocess.SubprocessError):
                pass
        except OSError:
            pass

    try:
        process.terminate()
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except OSError:
        try:
            process.kill()
            process.wait()
        except OSError:
            pass


def run_streaming_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    on_process_started: Callable[[subprocess.Popen], None] | None = None,
) -> ProcessResult:
    """Run a command and stream stdout/stderr line-by-line.

    When *cancel_event* is set during execution the process is terminated,
    then killed if it does not stop within a short grace period.
    """

    started_at = datetime.now().astimezone()
    started = time.perf_counter()
    cwd = cwd.resolve()

    try:
        popen_kwargs = {
            "cwd": str(cwd),
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
            "shell": False,
        }
        if cancel_event is not None and os.name != "nt":
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **popen_kwargs)
    except FileNotFoundError as exc:
        raise ProcessLaunchError(
            f"Command executable not found: {command[0]}"
        ) from exc
    except OSError as exc:
        raise ProcessLaunchError(f"Could not start command: {exc}") from exc

    if on_process_started is not None:
        on_process_started(process)

    output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    threads = [
        threading.Thread(
            target=_reader,
            args=(process.stdout, "stdout", output_queue),
            daemon=True,
        ),
        threading.Thread(
            target=_reader,
            args=(process.stderr, "stderr", output_queue),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    _terminated = False
    while process.poll() is None or any(thread.is_alive() for thread in threads):
        if cancel_event is not None and cancel_event.is_set() and not _terminated and process.poll() is None:
            _terminate_process_tree(process)
            _terminated = True
        try:
            stream_name, line = output_queue.get(timeout=0.05)
        except queue.Empty:
            continue
        if stream_name == "stdout" and on_stdout is not None:
            on_stdout(line)
        elif stream_name == "stderr" and on_stderr is not None:
            on_stderr(line)

    for thread_p in threads:
        thread_p.join()

    while not output_queue.empty():
        stream_name, line = output_queue.get_nowait()
        if stream_name == "stdout" and on_stdout is not None:
            on_stdout(line)
        elif stream_name == "stderr" and on_stderr is not None:
            on_stderr(line)

    finished_at = datetime.now().astimezone()
    return ProcessResult(
        command=list(command),
        cwd=cwd,
        exit_code=process.returncode,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=round(time.perf_counter() - started, 3),
    )
