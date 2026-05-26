"""Experiment config browser and launcher screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static

from orchestrator.control import (
    ExperimentConfigSummary,
    list_experiment_config_summaries,
)
from orchestrator.tui.debug_log import write_tui_debug
from orchestrator.tui.screens._confirm_paid_run import ConfirmPaidRunScreen
from orchestrator.tui.screens.active_run_screen import ActiveRunScreen


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
            f"Solver: {summary.solver_id or 'unknown'}",
            f"Target: {summary.target_file or 'unknown'}",
            f"Baseline: {summary.baseline_run_dir or 'unknown'}",
            f"Iterations: {summary.total_iterations if summary.total_iterations is not None else 'unknown'}",
            "Mode: closed-loop optimization",
            f"Reporting: {_format_bool(summary.reporting_enabled)}",
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
    solver = summary.solver_id or "?"
    return f"{summary.path.name} [{summary.status}] {iterations} iter {providers}/{models} [{solver}]"


class ExperimentScreen(Screen[None]):
    DEFAULT_CSS = """
    #experiment-action-row {
        height: 3;
        margin-top: 1;
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
    }

    .experiment-button {
        width: 100%;
        height: 3;
    }

    .experiment-back-button {
        width: 100%;
        height: 3;
        margin-top: 1;
    }
    """
    BINDINGS = [("escape", "request_back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self.summaries = list_experiment_config_summaries()
        self._can_start = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main"):
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
            summary.styles.height = 10
            yield summary
            yield Static("Idle. Select a config and press Dry Run or Real Run.", id="experiment-status-text", classes="panel")
            with Horizontal(id="experiment-action-row"):
                yield Button("Dry Run", id="dry-run", classes="experiment-button")
                yield Button("Real Run", id="real-run", classes="experiment-button")
            yield Button("Back", id="back", classes="experiment-back-button")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#experiment-list", ListView).styles.height = 6
        self._set_status_message("Idle. Select a config and press Dry Run or Real Run.")
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
        self.app.pop_screen()

    def _mark_ready(self) -> None:
        self._can_start = True
        write_tui_debug("ExperimentScreen ready for explicit start")

    def _request_real_run(self) -> None:
        if not self._can_start:
            write_tui_debug("ignored real run before screen ready")
            self._set_status_message("Screen initializing, try again.")
            return
        summary = self._selected_summary()
        if summary is None:
            self._set_status_message("No configs available.")
            return
        write_tui_debug("experiment real run confirmation dialog shown")
        self.app.push_screen(
            ConfirmPaidRunScreen(summary.path),
            callback=self._on_paid_run_confirmed,
        )

    def _on_paid_run_confirmed(self, confirmed: bool | None) -> None:
        if not confirmed:
            self._set_status_message("Idle. Real run cancelled.")
            write_tui_debug("experiment real run cancelled by user")
            return
        self._start_experiment(dry_run=False)

    def _set_status_message(self, status_text: str) -> None:
        self.query_one("#experiment-status-text", Static).update(status_text)

    def _start_experiment(self, dry_run: bool) -> None:
        if not self._can_start:
            write_tui_debug("ignored experiment start before screen ready")
            self._set_status_message("Screen initializing, try again.")
            return
        summary = self._selected_summary()
        if summary is None:
            self._set_status_message("No configs available.")
            write_tui_debug("ignored experiment start because no configs are available")
            return
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            self._set_status_message("Error: active_runs_manager not available.")
            write_tui_debug("ignored experiment start: manager missing")
            return
        mode_text = "dry-run" if dry_run else "real run"
        write_tui_debug(f"experiment {mode_text} start accepted")
        run_id = manager.start(summary.path, dry_run=dry_run)
        write_tui_debug(f"experiment {mode_text} started as {run_id}")
        self._set_status_message(
            f"{mode_text.title()} started as {run_id}. Opening live output..."
        )
        self.app.push_screen(ActiveRunScreen(run_id))
