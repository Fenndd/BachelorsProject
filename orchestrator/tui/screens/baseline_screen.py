"""Baseline launch screen for the Textual control layer."""

from __future__ import annotations

import queue
import threading

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from orchestrator.control import (
    build_baseline_command,
    load_environment,
    run_baseline,
    summarize_environment,
)


BASELINE_ENV_NAMES = {
    "EIGEN3_INCLUDE_DIR",
    "CMAKE_EXE",
    "CMAKE_GENERATOR",
    "CMAKE_CXX_COMPILER",
    "CMAKE_MAKE_PROGRAM",
    "BENCHMARK_CMAKE_BUILD_TYPE",
}


def _format_baseline_environment() -> str:
    statuses = load_environment()
    summary = summarize_environment(statuses)
    lines = [
        f"Environment: {summary.label}",
        "Baseline uses the existing orchestrator.cli.main entry point.",
        "",
        "Relevant variables:",
    ]
    for status in statuses:
        if status.name in BASELINE_ENV_NAMES:
            value = status.display_value or "-"
            lines.append(
                f"  {status.name}: {status.status} [{status.source}] {value}"
            )
    return "\n".join(lines)


class BaselineScreen(Screen[None]):
    BINDINGS = [("escape", "request_back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._running = False
        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._result_queue: queue.Queue[str] = queue.Queue()
        self._drain_timer = None

    def compose(self) -> ComposeResult:
        command = " ".join(build_baseline_command())
        yield Header()
        with Container(id="main"):
            yield Static("Run Baseline", classes="title")
            yield Static(
                "Runs CMake configure/build, smoke tests, adapter validation, "
                "benchmark parsing, and artifact saving through the existing baseline entry point.",
                classes="subtitle",
            )
            yield Static(_format_baseline_environment(), id="baseline-env", classes="panel")
            yield Static(f"Command: {command}", classes="panel")
            yield Static("Status: idle", id="baseline-status", classes="panel")
            yield RichLog(id="baseline-log", classes="panel", wrap=True, highlight=True)
            with Horizontal(classes="actions"):
                yield Button("Start", id="start-baseline", variant="primary")
                yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_request_back()
            return
        if event.button.id == "start-baseline":
            self._start_baseline()

    def action_request_back(self) -> None:
        if self._running:
            self._set_status_message(
                "Baseline is still running. Wait until it finishes before leaving this screen."
            )
            return
        self.app.pop_screen()

    def _start_baseline(self) -> None:
        if self._running:
            return
        self._clear_queues()
        self._running = True
        command = build_baseline_command()
        register_process = getattr(self.app, "register_process", None)
        if callable(register_process):
            register_process()
        self.query_one("#start-baseline", Button).disabled = True
        self.query_one("#baseline-status", Static).update("Status: starting")
        log = self.query_one("#baseline-log", RichLog)
        log.clear()
        log.write("Starting baseline subprocess...")
        log.write(f"Command: {' '.join(command)}")
        log.write("Waiting for output...")
        self._start_drain_timer()
        thread = threading.Thread(target=self._run_baseline_thread, daemon=True)
        thread.start()
        self.query_one("#baseline-status", Static).update("Status: running")

    def _append_log(self, line: str, stream_name: str) -> None:
        prefix = "[stderr] " if stream_name == "stderr" else ""
        self.query_one("#baseline-log", RichLog).write(f"{prefix}{line}")

    def _set_status_message(self, status_text: str) -> None:
        self.query_one("#baseline-status", Static).update(status_text)

    def _set_result(self, status_text: str) -> None:
        self._running = False
        self.query_one("#start-baseline", Button).disabled = False
        unregister_process = getattr(self.app, "unregister_process", None)
        if callable(unregister_process):
            unregister_process()
        self.query_one("#baseline-status", Static).update(status_text)
        self._stop_drain_timer()

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

    def _run_baseline_thread(self) -> None:
        def on_stdout(line: str) -> None:
            self._log_queue.put(("stdout", line))

        def on_stderr(line: str) -> None:
            self._log_queue.put(("stderr", line))

        try:
            result = run_baseline(on_stdout=on_stdout, on_stderr=on_stderr)
            latest_run = "-" if result.latest_run_dir is None else str(result.latest_run_dir)
            status_text = (
                f"Status: {result.status}\n"
                f"Exit code: {result.exit_code if result.exit_code is not None else 'n/a'}\n"
                f"Latest run directory: {latest_run}\n"
                f"Message: {result.message}"
            )
        except Exception as exc:
            status_text = (
                "Status: failed\n"
                "Exit code: n/a\n"
                "Latest run directory: -\n"
                f"Message: Unexpected baseline launcher error: {exc}"
            )
        self._result_queue.put(status_text)
