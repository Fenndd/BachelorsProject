"""Experiment config browser and launcher screen."""

from __future__ import annotations

import threading
import queue

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


class ExperimentScreen(Screen[None]):
    BINDINGS = [("escape", "request_back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self.summaries = list_experiment_config_summaries()
        self._running = False
        self._confirm_real_run = False
        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._result_queue: queue.Queue[str] = queue.Queue()

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
                    ListItem(Static(f"{summary.path.name} - {summary.name}"))
                    for summary in self.summaries
                ],
                id="experiment-list",
                classes="panel",
            )
            yield Static(_format_summary(self._selected_summary()), id="experiment-summary", classes="panel")
            yield Static("Status: idle", id="experiment-status", classes="panel")
            yield RichLog(id="experiment-log", classes="panel", wrap=True, highlight=True)
            with Horizontal(classes="actions"):
                yield Button("Dry Run", id="dry-run", variant="primary")
                yield Button("Run", id="real-run", variant="warning")
                yield Button("Back", id="back")
        yield Footer()

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

    def on_mount(self) -> None:
        self.set_interval(0.1, self._drain_queues)
        if self.summaries:
            self.query_one("#experiment-list", ListView).index = 0

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self._confirm_real_run = False
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
            if not self._confirm_real_run:
                self._confirm_real_run = True
                self.query_one("#experiment-status", Static).update(
                    "Status: confirmation required\n"
                    "This may use paid LLM API calls. Click Run again to continue."
                )
                return
            self._start_experiment(dry_run=False)

    def action_request_back(self) -> None:
        if self._running:
            self._set_status_message(
                "Experiment is still running. Wait until it finishes before leaving this screen."
            )
            return
        self.app.pop_screen()

    def _set_buttons_disabled(self, disabled: bool) -> None:
        self.query_one("#dry-run", Button).disabled = disabled
        self.query_one("#real-run", Button).disabled = disabled

    def _start_experiment(self, dry_run: bool) -> None:
        if self._running:
            return
        summary = self._selected_summary()
        if summary is None:
            self.query_one("#experiment-status", Static).update("Status: no configs available")
            return
        self._running = True
        self._confirm_real_run = False
        command = build_experiment_command(summary.path, dry_run=dry_run)
        register_process = getattr(self.app, "register_process", None)
        if callable(register_process):
            register_process()
        self._set_buttons_disabled(True)
        self.query_one("#experiment-status", Static).update("Status: starting")
        log = self.query_one("#experiment-log", RichLog)
        log.clear()
        log.write("Starting experiment subprocess...")
        log.write(f"Command: {' '.join(command)}")
        log.write(f"Mode: {'dry-run' if dry_run else 'real run'}")
        log.write("Waiting for output...")
        thread = threading.Thread(
            target=self._run_experiment_thread,
            args=(summary, dry_run),
            daemon=True,
        )
        thread.start()
        self.query_one("#experiment-status", Static).update(
            f"Status: running {'dry-run' if dry_run else 'real run'}"
        )

    def _append_log(self, line: str, stream_name: str) -> None:
        prefix = "[stderr] " if stream_name == "stderr" else ""
        self.query_one("#experiment-log", RichLog).write(f"{prefix}{line}")

    def _set_status_message(self, status_text: str) -> None:
        self.query_one("#experiment-status", Static).update(status_text)

    def _set_result(self, status_text: str) -> None:
        self._running = False
        self._set_buttons_disabled(False)
        unregister_process = getattr(self.app, "unregister_process", None)
        if callable(unregister_process):
            unregister_process()
        self.query_one("#experiment-status", Static).update(status_text)

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

    def _run_experiment_thread(
        self,
        summary: ExperimentConfigSummary,
        dry_run: bool,
    ) -> None:
        def on_stdout(line: str) -> None:
            self._log_queue.put(("stdout", line))

        def on_stderr(line: str) -> None:
            self._log_queue.put(("stderr", line))

        try:
            result = run_experiment_control(
                summary.path,
                dry_run=dry_run,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )
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
        self._result_queue.put(status_text)
