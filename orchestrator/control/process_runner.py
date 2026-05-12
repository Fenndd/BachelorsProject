"""Generic subprocess streaming helpers for control-layer commands."""

from __future__ import annotations

import queue
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


def run_streaming_command(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
) -> ProcessResult:
    """Run a command and stream stdout/stderr line-by-line."""

    started_at = datetime.now().astimezone()
    started = time.perf_counter()
    cwd = cwd.resolve()

    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise ProcessLaunchError(
            f"Command executable not found: {command[0]}"
        ) from exc
    except OSError as exc:
        raise ProcessLaunchError(f"Could not start command: {exc}") from exc

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

    while process.poll() is None or any(thread.is_alive() for thread in threads):
        try:
            stream_name, line = output_queue.get(timeout=0.05)
        except queue.Empty:
            continue
        if stream_name == "stdout" and on_stdout is not None:
            on_stdout(line)
        elif stream_name == "stderr" and on_stderr is not None:
            on_stderr(line)

    for thread in threads:
        thread.join()

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
