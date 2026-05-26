"""Embedded baseline launch view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Static

from orchestrator.control import (
    build_baseline_command,
    load_environment,
    summarize_environment,
)
from orchestrator.tui.debug_log import write_tui_debug
from orchestrator.tui.screens.active_run_screen import ActiveRunScreen

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


class BaselineView(Widget):
    """Embedded baseline launch view.

    Starts baseline through ActiveRunsManager -- no local queues, watchdog
    timers, or process-registration.
    """

    def __init__(self) -> None:
        super().__init__(id="view-baseline")

    def compose(self) -> ComposeResult:
        command = " ".join(build_baseline_command())
        with VerticalScroll():
            yield Static("Baseline", classes="title")
            yield Static(
                "Runs CMake configure/build, adapter validation, "
                "benchmark parsing, and artifact saving through the existing "
                "baseline entry point.",
                classes="subtitle",
            )
            yield Static(
                _format_baseline_environment(), id="baseline-env", classes="panel"
            )
            yield Static(
                f"Command: {command}", id="baseline-command", classes="panel"
            )
            yield Static("Status: idle", id="baseline-status", classes="panel")
            yield Static(
                "Live output opens in a run screen after start and remains "
                "available from the sidebar active-runs list.",
                id="baseline-live-note",
                classes="panel",
            )
            with Horizontal(classes="actions"):
                yield Button(
                    "Start Baseline", id="start-baseline", variant="primary"
                )
                yield Button("Refresh Environment", id="refresh-env")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-baseline":
            self._start_baseline()
        elif event.button.id == "refresh-env":
            self._refresh_environment()

    def _start_baseline(self) -> None:
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            self._set_status("Error: active_runs_manager not available.")
            write_tui_debug("baseline view start blocked: manager missing")
            return

        write_tui_debug("baseline view start accepted")
        run_id = manager.start_baseline()
        write_tui_debug(f"baseline started as {run_id}")
        self._set_status(f"Started as {run_id}. Opening live output...")
        self.app.push_screen(ActiveRunScreen(run_id))

    def _refresh_environment(self) -> None:
        self.query_one("#baseline-env", Static).update(
            _format_baseline_environment()
        )
        command = " ".join(build_baseline_command())
        self.query_one("#baseline-command", Static).update(
            f"Command: {command}"
        )

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#baseline-status", Static).update(text)
        except Exception:
            pass

    def focus_search(self) -> None:
        pass

    def clear_filter_or_blur(self) -> None:
        pass
