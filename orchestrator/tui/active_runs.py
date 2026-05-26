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

    def append_output(self, stream: str, line: str) -> None:
        with self._lock:
            self.output_buffer.append((stream, line))

    def snapshot_and_attach(
        self,
        subscriber: Callable[[str | None, str | None], None],
    ) -> list[tuple[str, str]]:
        """Atomically snapshot buffer and register subscriber to prevent missing lines."""
        with self._lock:
            snapshot = list(self.output_buffer)
            self._subscribers.add(subscriber)
        return snapshot


class ActiveRunsManager:
    def __init__(self, app: object, repo_root: Path | None = None) -> None:
        self._app = app
        self._repo_root = repo_root
        self._counter = 0
        self._runs: dict[str, ActiveRun] = {}
        self._lock = threading.Lock()
        self._max_finished_history = 20
        self._global_subscribers: set[Callable[[], None]] = set()

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

        worker_handle = run_worker(
            lambda: self._run_worker(run, config_path, dry_run),
            thread=True,
            exit_on_error=False,
            exclusive=False,
        )
        run.worker_handle = worker_handle
        return run_id

    def get(self, run_id: str) -> ActiveRun | None:
        return self._runs.get(run_id)

    def list(self) -> list[ActiveRunSummary]:
        with self._lock:
            self._prune_finished_locked()
            return [run.summary() for run in self._runs.values()]

    def attach(
        self,
        run_id: str,
        subscriber: Callable[[str | None, str | None], None],
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        with run._lock:
            run._subscribers.add(subscriber)

    def detach(
        self,
        run_id: str,
        subscriber: Callable[[str | None, str | None], None],
    ) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        with run._lock:
            run._subscribers.discard(subscriber)

    def snapshot_and_attach(
        self,
        run_id: str,
        subscriber: Callable[[str | None, str | None], None],
    ) -> list[tuple[str, str]]:
        """Atomically return buffered output and register subscriber."""
        run = self._runs.get(run_id)
        if run is None:
            return []
        return run.snapshot_and_attach(subscriber)

    def attach_global(self, callback: Callable[[], None]) -> None:
        """Register a callback to be notified on any run status change."""
        with self._lock:
            self._global_subscribers.add(callback)

    def detach_global(self, callback: Callable[[], None]) -> None:
        """Unregister a global status-change callback."""
        with self._lock:
            self._global_subscribers.discard(callback)

    def _notify_global_subscribers(self) -> None:
        call_from_thread = getattr(self._app, "call_from_thread", None)
        if call_from_thread is None:
            return
        with self._lock:
            callbacks = list(self._global_subscribers)
        for cb in callbacks:
            try:
                call_from_thread(cb)
            except Exception:
                pass

    def cancel(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        write_tui_debug(f"ActiveRunsManager.cancel: {run_id}")
        run.cancel_requested.set()

    def cancel_all(self) -> None:
        write_tui_debug("ActiveRunsManager.cancel_all")
        with self._lock:
            runs_snapshot = list(self._runs.values())
        for run in runs_snapshot:
            run.cancel_requested.set()

    def active_count(self) -> int:
        return sum(
            1 for run in self._runs.values() if run.status in ("starting", "running")
        )

    def _prune_finished_locked(self) -> None:
        finished = [
            run
            for run in self._runs.values()
            if run.status not in ("starting", "running")
        ]
        if len(finished) <= self._max_finished_history:
            return
        keep = {
            run.run_id
            for run in sorted(
                finished,
                key=lambda r: r.finished_at or r.started_at,
                reverse=True,
            )[: self._max_finished_history]
        }
        for run in finished:
            if run.run_id not in keep:
                self._runs.pop(run.run_id, None)

    def _notify_subscribers(
        self,
        run: ActiveRun,
        stream_name: str | None,
        line: str | None,
    ) -> None:
        call_from_thread = getattr(self._app, "call_from_thread", None)
        if call_from_thread is None:
            return
        with run._lock:
            callbacks = list(run._subscribers)
        for cb in callbacks:
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
            self._notify_global_subscribers()
            return

        run.status = "running"
        self._notify_subscribers(run, None, None)
        self._notify_global_subscribers()

        def on_stdout(line: str) -> None:
            run.append_output("stdout", line)
            self._notify_subscribers(run, "stdout", line)

        def on_stderr(line: str) -> None:
            run.append_output("stderr", line)
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
            with self._lock:
                self._prune_finished_locked()
            self._notify_subscribers(run, None, None)
            self._notify_global_subscribers()
            write_tui_debug(f"worker finished for {run.run_id} status={run.status}")
