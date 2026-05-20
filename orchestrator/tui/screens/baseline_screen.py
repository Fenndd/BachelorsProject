"""Baseline launch screen for the Textual control layer."""

from __future__ import annotations

import queue
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from orchestrator.control import (
    build_baseline_command,
    load_environment,
    run_baseline,
    summarize_environment,
)
from orchestrator.tui.debug_log import write_tui_debug


BASELINE_ENV_NAMES = {
    "EIGEN3_INCLUDE_DIR",
    "CMAKE_EXE",
    "CMAKE_GENERATOR",
    "CMAKE_CXX_COMPILER",
    "CMAKE_MAKE_PROGRAM",
    "BENCHMARK_CMAKE_BUILD_TYPE",
}

BaselineScreenState = Literal["idle", "starting", "running", "finished", "failed"]


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
    BINDINGS = [
        ("escape", "request_back", "Back"),
        ("ctrl+u", "force_unlock", "Force Unlock"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._state: BaselineScreenState = "idle"
        self._can_start = False
        self._process_registered = False
        self._log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._result_queue: queue.Queue[str] = queue.Queue()
        self._drain_timer = None
        self._watchdog_timer = None

    def compose(self) -> ComposeResult:
        command = " ".join(build_baseline_command())
        yield Header()
        with VerticalScroll(id="main"):
            yield Static("Run Baseline", classes="title")
            yield Static(
                "Runs CMake configure/build, adapter validation, "
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

    def on_mount(self) -> None:
        self._set_state("idle")
        self._set_status_message("Status: idle")
        write_tui_debug("BaselineScreen mounted")
        self.set_timer(0.2, self._mark_ready)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_request_back()
            return
        if event.button.id == "start-baseline":
            self._start_baseline()

    def action_request_back(self) -> None:
        if self._is_active():
            self._set_status_message(
                "Baseline is still running. Wait until it finishes before leaving this screen."
            )
            write_tui_debug(f"back blocked while baseline state={self._state}")
            return
        self.app.pop_screen()

    def action_force_unlock(self) -> None:
        self._force_unlock()

    def _is_active(self) -> bool:
        return self._state in {"starting", "running"}

    def _set_state(self, state: BaselineScreenState) -> None:
        self._state = state

    def _mark_ready(self) -> None:
        self._can_start = True
        write_tui_debug("BaselineScreen ready for explicit start")

    def _start_baseline(self) -> None:
        if self._is_active():
            write_tui_debug(f"ignored start while baseline state={self._state}")
            return
        if not self._can_start:
            write_tui_debug("ignored start before screen ready")
            self._set_status_message("Status: screen initializing, try again")
            return
        self._clear_queues()
        self._set_state("starting")
        command = build_baseline_command()
        write_tui_debug("baseline start accepted")
        write_tui_debug(f"baseline command: {' '.join(command)}")
        register_process = getattr(self.app, "register_process", None)
        if callable(register_process):
            register_process()
            self._process_registered = True
            write_tui_debug("baseline process registered")
        self.query_one("#start-baseline", Button).disabled = True
        self._set_status_message("Status: start accepted")
        log = self.query_one("#baseline-log", RichLog)
        log.clear()
        log.write("Start accepted.")
        log.write("Starting baseline subprocess...")
        log.write(f"Command: {' '.join(command)}")
        log.write("Waiting for output...")
        write_tui_debug("baseline visible start messages written")
        self._start_drain_timer()
        self._drain_queues()
        write_tui_debug("baseline drain timer started")
        self.run_worker(
            self._run_baseline_worker,
            thread=True,
            exit_on_error=False,
            exclusive=True,
        )
        self._set_state("running")
        self._set_status_message("Status: running")
        self._start_watchdog_timer()
        write_tui_debug("baseline worker scheduled")

    def _append_log(self, line: str, stream_name: str) -> None:
        prefix = "[stderr] " if stream_name == "stderr" else ""
        self.query_one("#baseline-log", RichLog).write(f"{prefix}{line}")

    def _set_status_message(self, status_text: str) -> None:
        self.query_one("#baseline-status", Static).update(status_text)

    def _set_result(self, status_text: str) -> None:
        self._set_state("finished" if status_text.startswith("Status: success") else "failed")
        self.query_one("#start-baseline", Button).disabled = False
        self._unregister_process()
        self.query_one("#baseline-status", Static).update(status_text)
        write_tui_debug(f"baseline result applied: {status_text.splitlines()[0] if status_text else '-'}")
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
        message = "Status: still running after 30s. Check workspace/tui_debug.log."
        self._set_status_message(message)
        write_tui_debug(f"baseline watchdog fired while state={self._state}")

    def _unregister_process(self) -> None:
        if not self._process_registered:
            return
        unregister_process = getattr(self.app, "unregister_process", None)
        if callable(unregister_process):
            unregister_process()
        self._process_registered = False
        write_tui_debug("baseline process unregistered")

    def _force_unlock(self) -> None:
        self._set_state("failed")
        self._unregister_process()
        self.query_one("#start-baseline", Button).disabled = False
        self._stop_drain_timer()
        self._stop_watchdog_timer()
        message = (
            "Status: force-unlocked. Check workspace/tui_debug.log and Task Manager "
            "for leftover python processes."
        )
        self._set_status_message(message)
        write_tui_debug("baseline force unlock requested")

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

    def _run_baseline_worker(self) -> None:
        write_tui_debug("baseline worker entered")

        def on_stdout(line: str) -> None:
            self._log_queue.put(("stdout", line))

        def on_stderr(line: str) -> None:
            self._log_queue.put(("stderr", line))

        try:
            write_tui_debug("baseline run_baseline call starting")
            result = run_baseline(on_stdout=on_stdout, on_stderr=on_stderr)
            write_tui_debug(f"baseline run_baseline returned status={result.status}")
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
            write_tui_debug(f"baseline worker unexpected error: {exc}")
        self._result_queue.put(status_text)
        write_tui_debug("baseline worker queued final result")
