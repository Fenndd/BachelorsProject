"""Active run model and manager for non-blocking run lifecycle."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from orchestrator.control.baseline_launcher import (
    build_baseline_command,
    run_baseline,
)
from orchestrator.control.experiment_launcher import (
    build_experiment_command,
    run_experiment_control,
)
from orchestrator.tui.debug_log import write_tui_debug

ActiveRunKind = Literal["baseline", "experiment"]
ActiveRunStatus = Literal["starting", "running", "succeeded", "failed", "cancelled"]
ActiveRunRunner = Callable[
    [
        "ActiveRun",
        threading.Event,
        Callable[[str], None],
        Callable[[str], None],
        Callable[[object], None],
    ],
    object,
]


@dataclass(frozen=True)
class ActiveRunSummary:
    run_id: str
    kind: ActiveRunKind
    config_path: Path
    dry_run: bool
    status: ActiveRunStatus
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    latest_result_dir: Path | None
    latest_experiment_dir: Path | None


class ActiveRun:
    __slots__ = (
        "run_id",
        "config_path",
        "dry_run",
        "kind",
        "command",
        "started_at",
        "finished_at",
        "status",
        "exit_code",
        "message",
        "latest_result_dir",
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
        kind: ActiveRunKind = "experiment",
    ) -> None:
        self.run_id = run_id
        self.config_path = config_path
        self.dry_run = dry_run
        self.kind: ActiveRunKind = kind
        self.command = command
        self.started_at = started_at
        self.finished_at: datetime | None = None
        self.status: ActiveRunStatus = "starting"
        self.exit_code: int | None = None
        self.message: str = ""
        self.latest_result_dir: Path | None = None
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
            kind=self.kind,
            config_path=self.config_path,
            dry_run=self.dry_run,
            status=self.status,
            started_at=self.started_at,
            finished_at=self.finished_at,
            exit_code=self.exit_code,
            latest_result_dir=self.latest_result_dir,
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
        return self.start_experiment(config_path, dry_run=dry_run)

    def start_experiment(self, config_path: Path, dry_run: bool = False) -> str:
        command = build_experiment_command(config_path, dry_run=dry_run)
        return self._start_run(
            kind="experiment",
            config_path=config_path,
            dry_run=dry_run,
            command=command,
            runner=self._experiment_runner(config_path, dry_run),
        )

    def start_baseline(self, solver_id: str | None = None) -> str:
        command = build_baseline_command(solver_id)
        return self._start_run(
            kind="baseline",
            config_path=Path("<baseline>"),
            dry_run=False,
            command=command,
            runner=self._baseline_runner(solver_id),
        )

    def _start_run(
        self,
        kind: ActiveRunKind,
        config_path: Path,
        dry_run: bool,
        command: list[str],
        runner: ActiveRunRunner,
    ) -> str:
        with self._lock:
            self._counter += 1
            run_id = f"run_{self._counter:03d}"

        now = datetime.now().astimezone()
        run = ActiveRun(
            run_id=run_id,
            kind=kind,
            config_path=config_path,
            dry_run=dry_run,
            command=command,
            started_at=now,
        )
        with self._lock:
            self._runs[run_id] = run

        write_tui_debug(
            f"ActiveRunsManager.start_{kind}: {run_id} cmd={' '.join(command)}"
        )

        app = self._app
        run_worker = getattr(app, "run_worker", None)
        if run_worker is None:
            run.status = "failed"
            run.message = "Application does not support workers."
            run.finished_at = datetime.now().astimezone()
            self._notify_global_subscribers(direct=True)
            return run_id

        worker_handle = run_worker(
            lambda: self._run_worker(run, runner),
            thread=True,
            exit_on_error=False,
            exclusive=False,
        )
        run.worker_handle = worker_handle
        self._notify_global_subscribers(direct=True)
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

    def _notify_global_subscribers(self, direct: bool = False) -> None:
        with self._lock:
            callbacks = list(self._global_subscribers)
        if direct:
            for cb in callbacks:
                try:
                    cb()
                except Exception:
                    pass
            return
        call_from_thread = getattr(self._app, "call_from_thread", None)
        if call_from_thread is None:
            return
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

    def clear_finished(self) -> int:
        """Remove completed runs from recent history without touching active runs."""
        finished_statuses = {"succeeded", "failed", "cancelled"}
        with self._lock:
            run_ids = [
                run_id
                for run_id, run in self._runs.items()
                if run.status in finished_statuses
            ]
            for run_id in run_ids:
                self._runs.pop(run_id, None)
        if run_ids:
            write_tui_debug(f"ActiveRunsManager.clear_finished removed {len(run_ids)} run(s)")
            self._notify_global_subscribers(direct=True)
        return len(run_ids)

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1
                for run in self._runs.values()
                if run.status in ("starting", "running")
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
        runner: ActiveRunRunner,
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
            result = runner(
                run,
                run.cancel_requested,
                on_stdout,
                on_stderr,
                on_process_started,
            )
            if run.cancel_requested.is_set():
                run.status = "cancelled"
            elif getattr(result, "status", None) == "success":
                run.status = "succeeded"
            else:
                run.status = "failed"
            run.exit_code = getattr(result, "exit_code", None)
            run.message = getattr(result, "message", "")
            if run.kind == "experiment":
                run.latest_result_dir = getattr(result, "latest_experiment_dir", None)
                run.latest_experiment_dir = run.latest_result_dir
            else:
                run.latest_result_dir = getattr(result, "latest_run_dir", None)
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

    def _experiment_runner(self, config_path: Path, dry_run: bool) -> ActiveRunRunner:
        def runner(
            run: ActiveRun,
            cancel_event: threading.Event,
            on_stdout: Callable[[str], None],
            on_stderr: Callable[[str], None],
            on_process_started: Callable[[object], None],
        ) -> object:
            return run_experiment_control(
                config_path,
                dry_run=dry_run,
                repo_root=self._repo_root,
                cancel_event=cancel_event,
                on_process_started=on_process_started,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )

        return runner

    def _baseline_runner(self, solver_id: str | None) -> ActiveRunRunner:
        def runner(
            run: ActiveRun,
            cancel_event: threading.Event,
            on_stdout: Callable[[str], None],
            on_stderr: Callable[[str], None],
            on_process_started: Callable[[object], None],
        ) -> object:
            return run_baseline(
                repo_root=self._repo_root,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
                solver_id=solver_id,
                cancel_event=cancel_event,
                on_process_started=on_process_started,
            )

        return runner
