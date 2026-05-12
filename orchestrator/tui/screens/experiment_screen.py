"""Experiment config browser and launcher screen."""

from __future__ import annotations

import queue
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ListItem, ListView, RichLog, Static

from orchestrator.control import (
    ExperimentConfigSummary,
    list_experiment_config_summaries,
    build_experiment_command,
    run_experiment_control,
)
from orchestrator.tui.debug_log import write_tui_debug


ExperimentScreenState = Literal[
    "idle",
    "confirming",
    "starting",
    "running",
    "finished",
    "failed",
]


def _format_bool(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "unknown"


def _format_summary(summary: ExperimentConfigSummary | None) -> str:
    if summary is None:
        return "No experiment configs found."
    return "\n".join(
        [
            f"Config: {summary.path.name}",
            f"Experiment: {summary.name}",
            f"Description: {summary.description or 'unknown'}",
            f"Target: {summary.target_file or 'unknown'}",
            f"Iterations: {summary.total_iterations if summary.total_iterations is not None else 'unknown'}",
            f"Candidate format: {summary.candidate_format or 'unknown'}",
            f"Source presentation: {summary.source_presentation or 'unknown'}",
            f"Selection: {_format_bool(summary.selection_enabled)}",
            f"Closed-loop: {_format_bool(summary.closed_loop_enabled)}",
            f"Providers: {_format_list(summary.providers)}",
            f"Models: {_format_list(summary.models)}",
            f"Status: {summary.status}",
            f"Message: {summary.message or '-'}",
        ]
    )


def _compact_summary_label(summary: ExperimentConfigSummary) -> str:
    iterations = (
        str(summary.total_iterations)
        if summary.total_iterations is not None
        else "?"
    )
    providers = "/".join(summary.providers) if summary.providers else "unknown"
    models = "/".join(summary.models) if summary.models else "unknown"
    return f"{summary.path.name} [{summary.status}] {iterations} iter {providers}/{models}"


class ExperimentScreen(Screen[None]):
    BINDINGS = [
        ("escape", "request_back", "Back"),
        ("ctrl+u", "force_unlock", "Force Unlock"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.summaries = list_experiment_config_summaries()
        self._state: ExperimentScreenState = "idle"
        self._can_start = False
        self._process_registered = False
        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._result_queue: queue.Queue[str] = queue.Queue()
        self._drain_timer = None
        self._watchdog_timer = None
        self._debug_stdout_count = 0
        self._debug_stderr_count = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            yield Static("Run Experiment", classes="title")
            yield Static(
                "Select a config, run a safe dry-run, or launch the existing experiment runner.",
                classes="subtitle",
            )
            yield ListView(
                *[
                    ListItem(Static(_compact_summary_label(summary)))
                    for summary in self.summaries
                ],
                id="experiment-list",
                classes="panel",
            )
            summary = Static(_format_summary(self._selected_summary()), id="experiment-summary", classes="panel")
            summary.styles.height = 12
            yield summary
            status = Static("Status: idle", id="experiment-status", classes="panel")
            status.styles.height = 3
            yield status
            log = RichLog(id="experiment-log", classes="panel", wrap=True, highlight=True)
            log.styles.height = 10
            yield log
            with Horizontal(classes="actions"):
                yield Button("Dry Run", id="dry-run")
                yield Button("Real Run", id="real-run")
                yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#experiment-list", ListView).styles.height = 7
        self._set_state("idle")
        self._set_status_message("Status: idle")
        write_tui_debug("ExperimentScreen mounted")
        if self.summaries:
            self.query_one("#experiment-list", ListView).index = 0
        self.set_timer(0.2, self._mark_ready)

    def _selected_summary(self) -> ExperimentConfigSummary | None:
        if not self.summaries:
            return None
        try:
            index = self.query_one("#experiment-list", ListView).index
        except Exception:
            index = 0
        if index is None or index < 0 or index >= len(self.summaries):
            index = 0
        return self.summaries[index]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if self._state == "confirming":
            self._set_state("idle")
            self._set_status_message("Status: idle")
            write_tui_debug("experiment confirmation reset after config highlight")
        self.query_one("#experiment-summary", Static).update(
            _format_summary(self._selected_summary())
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_request_back()
            return
        if event.button.id == "dry-run":
            self._start_experiment(dry_run=True)
            return
        if event.button.id == "real-run":
            self._request_real_run()

    def action_request_back(self) -> None:
        if self._is_active():
            self._set_status_message(
                "Experiment is still running. Wait until it finishes before leaving this screen."
            )
            write_tui_debug(f"back blocked while experiment state={self._state}")
            return
        write_tui_debug(f"back allowed while experiment state={self._state}")
        self.app.pop_screen()

    def action_force_unlock(self) -> None:
        self._force_unlock()

    def _is_active(self) -> bool:
        return self._state in {"starting", "running"}

    def _set_state(self, state: ExperimentScreenState) -> None:
        self._state = state

    def _mark_ready(self) -> None:
        self._can_start = True
        write_tui_debug("ExperimentScreen ready for explicit start")

    def _request_real_run(self) -> None:
        if self._is_active():
            write_tui_debug(f"ignored real run request while experiment state={self._state}")
            return
        if not self._can_start:
            write_tui_debug("ignored real run before screen ready")
            self._set_status_message("Status: screen initializing, try again")
            return
        if self._state != "confirming":
            self._set_state("confirming")
            self._set_status_message(
                "Status: confirmation required. This may use paid LLM API calls. Click Run again to continue."
            )
            write_tui_debug("experiment real run confirmation requested")
            return
        self._start_experiment(dry_run=False)

    def _set_buttons_disabled(self, disabled: bool) -> None:
        self.query_one("#dry-run", Button).disabled = disabled
        self.query_one("#real-run", Button).disabled = disabled

    def _start_experiment(self, dry_run: bool) -> None:
        if self._is_active():
            write_tui_debug(f"ignored experiment start while state={self._state}")
            return
        if not self._can_start:
            write_tui_debug("ignored experiment start before screen ready")
            self._set_status_message("Status: screen initializing, try again")
            return
        summary = self._selected_summary()
        if summary is None:
            self._set_status_message("Status: no configs available")
            write_tui_debug("ignored experiment start because no configs are available")
            return
        self._clear_queues()
        self._set_state("starting")
        self._debug_stdout_count = 0
        self._debug_stderr_count = 0
        command = build_experiment_command(summary.path, dry_run=dry_run)
        mode_text = "dry-run" if dry_run else "real run"
        write_tui_debug(f"experiment {mode_text} start accepted")
        write_tui_debug(f"experiment command: {' '.join(command)}")
        register_process = getattr(self.app, "register_process", None)
        if callable(register_process):
            register_process()
            self._process_registered = True
            write_tui_debug("experiment process registered")
        self._set_buttons_disabled(True)
        self._set_status_message("Status: start accepted")
        log = self.query_one("#experiment-log", RichLog)
        log.clear()
        log.write("Start accepted.")
        log.write("Starting experiment subprocess...")
        log.write(f"Command: {' '.join(command)}")
        log.write(f"Mode: {mode_text}")
        log.write("Waiting for output...")
        write_tui_debug("experiment visible start messages written")
        self._start_drain_timer()
        self._drain_queues()
        write_tui_debug("experiment drain timer started")
        self.run_worker(
            lambda: self._run_experiment_worker(summary, dry_run),
            thread=True,
            exit_on_error=False,
            exclusive=True,
        )
        self._set_state("running")
        self._set_status_message(f"Status: running {mode_text}")
        self._start_watchdog_timer()
        write_tui_debug("experiment worker scheduled")

    def _append_log(self, line: str, stream_name: str) -> None:
        prefix = "[stderr] " if stream_name == "stderr" else ""
        self.query_one("#experiment-log", RichLog).write(f"{prefix}{line}")

    def _set_status_message(self, status_text: str) -> None:
        self.query_one("#experiment-status", Static).update(status_text)

    def _set_result(self, status_text: str) -> None:
        self._set_state("finished" if status_text.startswith("Status: success") else "failed")
        self._set_buttons_disabled(False)
        self._unregister_process()
        self.query_one("#experiment-status", Static).update(status_text)
        write_tui_debug(f"experiment result applied: {status_text.splitlines()[0] if status_text else '-'}")
        self._stop_drain_timer()
        self._stop_watchdog_timer()

    def _clear_queues(self) -> None:
        while True:
            try:
                self._log_queue.get_nowait()
            except queue.Empty:
                break
        while True:
            try:
                self._result_queue.get_nowait()
            except queue.Empty:
                break

    def _start_drain_timer(self) -> None:
        self._stop_drain_timer()
        self._drain_timer = self.set_interval(0.1, self._drain_queues)

    def _stop_drain_timer(self) -> None:
        timer = self._drain_timer
        self._drain_timer = None
        if timer is None:
            return
        stop = getattr(timer, "stop", None)
        if callable(stop):
            stop()
            return
        pause = getattr(timer, "pause", None)
        if callable(pause):
            pause()

    def _start_watchdog_timer(self) -> None:
        self._stop_watchdog_timer()
        self._watchdog_timer = self.set_timer(30.0, self._watchdog_check)

    def _stop_watchdog_timer(self) -> None:
        timer = self._watchdog_timer
        self._watchdog_timer = None
        if timer is None:
            return
        stop = getattr(timer, "stop", None)
        if callable(stop):
            stop()
            return
        pause = getattr(timer, "pause", None)
        if callable(pause):
            pause()

    def _watchdog_check(self) -> None:
        if not self._is_active():
            return
        self._set_status_message(
            "Status: still running after 30s. Check workspace/tui_debug.log."
        )
        write_tui_debug(f"experiment watchdog fired while state={self._state}")

    def _unregister_process(self) -> None:
        if not self._process_registered:
            return
        unregister_process = getattr(self.app, "unregister_process", None)
        if callable(unregister_process):
            unregister_process()
        self._process_registered = False
        write_tui_debug("experiment process unregistered")

    def _force_unlock(self) -> None:
        self._set_state("failed")
        self._unregister_process()
        self._set_buttons_disabled(False)
        self._stop_drain_timer()
        self._stop_watchdog_timer()
        self._set_status_message(
            "Status: force-unlocked. Check workspace/tui_debug.log and Task Manager "
            "for leftover python processes."
        )
        write_tui_debug("experiment force unlock requested")

    def _drain_queues(self) -> None:
        while True:
            try:
                stream_name, line = self._log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line, stream_name)

        try:
            status_text = self._result_queue.get_nowait()
        except queue.Empty:
            return
        self._set_result(status_text)

    def _run_experiment_worker(
        self,
        summary: ExperimentConfigSummary,
        dry_run: bool,
    ) -> None:
        write_tui_debug("experiment worker entered")

        def on_stdout(line: str) -> None:
            self._log_queue.put(("stdout", line))
            self._debug_stdout_count += 1
            if self._debug_stdout_count <= 3:
                write_tui_debug(f"experiment stdout line received #{self._debug_stdout_count}")

        def on_stderr(line: str) -> None:
            self._log_queue.put(("stderr", line))
            self._debug_stderr_count += 1
            if self._debug_stderr_count <= 3:
                write_tui_debug(f"experiment stderr line received #{self._debug_stderr_count}")

        try:
            write_tui_debug("experiment run_experiment_control call starting")
            result = run_experiment_control(
                summary.path,
                dry_run=dry_run,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )
            write_tui_debug(f"experiment run_experiment_control returned status={result.status}")
            latest_dir = "-" if result.latest_experiment_dir is None else str(result.latest_experiment_dir)
            status_text = (
                f"Status: {result.status}\n"
                f"Exit code: {result.exit_code if result.exit_code is not None else 'n/a'}\n"
                f"Latest experiment directory: {latest_dir}\n"
                f"Message: {result.message}"
            )
        except Exception as exc:
            status_text = (
                "Status: failed\n"
                "Exit code: n/a\n"
                "Latest experiment directory: -\n"
                f"Message: Unexpected experiment launcher error: {exc}"
            )
            write_tui_debug(f"experiment worker unexpected error: {exc}")
        self._result_queue.put(status_text)
        write_tui_debug("experiment worker queued final result")
