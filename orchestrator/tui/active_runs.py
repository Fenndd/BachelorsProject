"""Active run model and manager for non-blocking experiment lifecycle."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from orchestrator.control.experiment_launcher import (
    build_experiment_command,
    run_experiment_control,
)
from orchestrator.tui.debug_log import write_tui_debug

ActiveRunStatus = Literal["starting", "running", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class ActiveRunSummary:
    run_id: str
    config_path: Path
    dry_run: bool
    status: ActiveRunStatus
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    latest_experiment_dir: Path | None


class ActiveRun:
    __slots__ = (
        "run_id",
        "config_path",
        "dry_run",
        "command",
        "started_at",
        "finished_at",
        "status",
        "exit_code",
        "message",
        "latest_experiment_dir",
        "output_buffer",
        "process",
        "cancel_requested",
        "worker_handle",
        "_subscribers",
        "_lock",
    )

    def __init__(
        self,
        run_id: str,
        config_path: Path,
        dry_run: bool,
        command: list[str],
        started_at: datetime,
    ) -> None:
        self.run_id = run_id
        self.config_path = config_path
        self.dry_run = dry_run
        self.command = command
        self.started_at = started_at
        self.finished_at: datetime | None = None
        self.status: ActiveRunStatus = "starting"
        self.exit_code: int | None = None
        self.message: str = ""
        self.latest_experiment_dir: Path | None = None
        self.output_buffer: deque[tuple[str, str]] = deque(maxlen=2000)
        self.process: Any = None
        self.cancel_requested = threading.Event()
        self.worker_handle: object | None = None
        self._subscribers: set[Callable[[str | None, str | None], None]] = set()
        self._lock = threading.Lock()

    def summary(self) -> ActiveRunSummary:
        return ActiveRunSummary(
            run_id=self.run_id,
            config_path=self.config_path,
            dry_run=self.dry_run,
            status=self.status,
            started_at=self.started_at,
            finished_at=self.finished_at,
            exit_code=self.exit_code,
            latest_experiment_dir=self.latest_experiment_dir,
        )


class ActiveRunsManager:
    def __init__(self, app: object, repo_root: Path | None = None) -> None:
        self._app = app
        self._repo_root = repo_root
        self._counter = 0
        self._runs: dict[str, ActiveRun] = {}
        self._lock = threading.Lock()

    def start(self, config_path: Path, dry_run: bool = False) -> str:
        with self._lock:
            self._counter += 1
            run_id = f"run_{self._counter:03d}"

        command = build_experiment_command(config_path, dry_run=dry_run)
        now = datetime.now().astimezone()
        run = ActiveRun(
            run_id=run_id,
            config_path=config_path,
            dry_run=dry_run,
            command=command,
            started_at=now,
        )
        with self._lock:
            self._runs[run_id] = run

        write_tui_debug(f"ActiveRunsManager.start: {run_id} cmd={' '.join(command)}")

        app = self._app
        run_worker = getattr(app, "run_worker", None)
        if run_worker is None:
            run.status = "failed"
            run.message = "Application does not support workers."
            run.finished_at = datetime.now().astimezone()
            return run_id

        run_worker(
            lambda: self._run_worker(run, config_path, dry_run),
            thread=True,
            exit_on_error=False,
            exclusive=False,
        )
        return run_id

    def get(self, run_id: str) -> ActiveRun | None:
        return self._runs.get(run_id)

    def list(self) -> list[ActiveRunSummary]:
        with self._lock:
            return [run.summary() for run in self._runs.values()]

    def attach(
        self,
        run_id: str,
        subscriber: Callable[[str | None, str | None], None],
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        run._subscribers.add(subscriber)

    def detach(
        self,
        run_id: str,
        subscriber: Callable[[str | None, str | None], None],
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        run._subscribers.discard(subscriber)

    def cancel(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        write_tui_debug(f"ActiveRunsManager.cancel: {run_id}")
        run.cancel_requested.set()

    def cancel_all(self) -> None:
        write_tui_debug("ActiveRunsManager.cancel_all")
        for run in self._runs.values():
            run.cancel_requested.set()

    def active_count(self) -> int:
        return sum(
            1 for run in self._runs.values() if run.status in ("starting", "running")
        )

    def _notify_subscribers(
        self,
        run: ActiveRun,
        stream_name: str | None,
        line: str | None,
    ) -> None:
        call_from_thread = getattr(self._app, "call_from_thread", None)
        if call_from_thread is None:
            return
        for cb in frozenset(run._subscribers):
            try:
                call_from_thread(lambda c=cb, s=stream_name, l=line: c(s, l))
            except Exception:
                pass

    def _run_worker(
        self,
        run: ActiveRun,
        config_path: Path,
        dry_run: bool,
    ) -> None:
        write_tui_debug(f"worker entered for {run.run_id}")

        if run.cancel_requested.is_set():
            run.status = "cancelled"
            run.message = "Cancelled before start."
            run.finished_at = datetime.now().astimezone()
            self._notify_subscribers(run, None, None)
            return

        run.status = "running"
        self._notify_subscribers(run, None, None)

        def on_stdout(line: str) -> None:
            run.output_buffer.append(("stdout", line))
            self._notify_subscribers(run, "stdout", line)

        def on_stderr(line: str) -> None:
            run.output_buffer.append(("stderr", line))
            self._notify_subscribers(run, "stderr", line)

        def on_process_started(process: object) -> None:
            run.process = process

        try:
            result = run_experiment_control(
                config_path,
                dry_run=dry_run,
                repo_root=self._repo_root,
                cancel_event=run.cancel_requested,
                on_process_started=on_process_started,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )
            if run.cancel_requested.is_set():
                run.status = "cancelled"
            elif result.status == "success":
                run.status = "succeeded"
            else:
                run.status = "failed"
            run.exit_code = result.exit_code
            run.message = result.message
            run.latest_experiment_dir = result.latest_experiment_dir
        except Exception as exc:
            write_tui_debug(f"worker for {run.run_id} unexpected error: {exc}")
            if run.cancel_requested.is_set():
                run.status = "cancelled"
            else:
                run.status = "failed"
            run.message = str(exc)
        finally:
            run.finished_at = datetime.now().astimezone()
            self._notify_subscribers(run, None, None)
            write_tui_debug(f"worker finished for {run.run_id} status={run.status}")
