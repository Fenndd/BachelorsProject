"""Embedded experiment launch view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Select, Static

from orchestrator.control import (
    ExperimentConfigSummary,
    list_experiment_config_summaries,
)
from orchestrator.tui.debug_log import write_tui_debug
from orchestrator.tui.screens._confirm_paid_run import ConfirmPaidRunScreen

_NO_CONFIG_VALUE = "__no_config__"


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


def _config_select_options(
    summaries: list[ExperimentConfigSummary],
) -> list[tuple[str, str]]:
    if not summaries:
        return [("No configs available", _NO_CONFIG_VALUE)]
    return [(_compact_summary_label(summary), str(summary.path)) for summary in summaries]


class ExperimentsView(Widget):
    """Embedded experiment config browser and launcher view.

    Starts experiments through ActiveRunsManager -- no local queue, worker,
    or legacy process registration.
    """

    def __init__(self) -> None:
        super().__init__(id="view-experiments")
        self.summaries = list_experiment_config_summaries()
        self._can_start = False

    def compose(self) -> ComposeResult:
        with Vertical(id="experiments-view"):
            with VerticalScroll(id="experiments-scroll"):
                yield Static("Run Experiment", classes="title")
                yield Static(
                    "Select a config, run a safe dry-run, or launch the existing experiment runner.",
                    classes="subtitle",
                )
                yield Static("Experiment Config", classes="field-label")
                yield Select(
                    _config_select_options(self.summaries),
                    value=(str(self.summaries[0].path) if self.summaries else _NO_CONFIG_VALUE),
                    id="experiment-config",
                    allow_blank=False,
                )
                summary = Static(
                    _format_summary(self._selected_summary()),
                    id="experiment-summary",
                    classes="panel",
                )
                yield summary
                yield Static(
                    "Idle. Select a config and press Dry Run or Real Run.",
                    id="experiment-status-text",
                    classes="panel",
                )
            with Horizontal(classes="actions", id="experiment-actions"):
                yield Button("Dry Run", id="dry-run")
                yield Button("Real Run", id="real-run")

    def on_mount(self) -> None:
        self.refresh_summaries(status_message=None)
        self._set_status_message(
            "Idle. Select a config and press Dry Run or Real Run."
        )
        write_tui_debug("ExperimentsView mounted")
        self.set_timer(0.2, self._mark_ready)

    def refresh_summaries(self, status_message: str | None = "Config list refreshed.") -> None:
        current = self._selected_summary()
        current_path = str(current.path) if current is not None else None
        self.summaries = list_experiment_config_summaries()
        try:
            config_select = self.query_one("#experiment-config", Select)
            options = _config_select_options(self.summaries)
            config_select.set_options(options)
            if self.summaries:
                values = {str(summary.path) for summary in self.summaries}
                config_select.value = (
                    current_path
                    if current_path in values
                    else str(self.summaries[0].path)
                )
            else:
                config_select.value = _NO_CONFIG_VALUE
            self.query_one("#experiment-summary", Static).update(
                _format_summary(self._selected_summary())
            )
            if status_message is not None:
                self._set_status_message(status_message)
        except Exception:
            pass

    def refresh_view(self) -> None:
        self.refresh_summaries()

    def _selected_summary(self) -> ExperimentConfigSummary | None:
        if not self.summaries:
            return None
        try:
            value = self.query_one("#experiment-config", Select).value
        except Exception:
            value = str(self.summaries[0].path)
        if isinstance(value, str) and value != _NO_CONFIG_VALUE:
            for summary in self.summaries:
                if str(summary.path) == value:
                    return summary
        return self.summaries[0]

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "experiment-config":
            self.query_one("#experiment-summary", Static).update(
                _format_summary(self._selected_summary())
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dry-run":
            self._start_experiment(dry_run=True)
        elif event.button.id == "real-run":
            self._request_real_run()

    def _mark_ready(self) -> None:
        self._can_start = True
        write_tui_debug("ExperimentsView ready for explicit start")

    def _request_real_run(self) -> None:
        if not self._can_start:
            write_tui_debug("ignored real run before view ready")
            self._set_status_message("View initializing, try again.")
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
        try:
            self.query_one("#experiment-status-text", Static).update(status_text)
        except Exception:
            pass

    def _start_experiment(self, dry_run: bool) -> None:
        if not self._can_start:
            write_tui_debug("ignored experiment start before view ready")
            self._set_status_message("View initializing, try again.")
            return
        summary = self._selected_summary()
        if summary is None:
            self._set_status_message("No configs available.")
            write_tui_debug(
                "ignored experiment start because no configs are available"
            )
            return
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            self._set_status_message(
                "Error: active_runs_manager not available."
            )
            write_tui_debug("ignored experiment start: manager missing")
            return
        mode_text = "dry-run" if dry_run else "real run"
        write_tui_debug(f"experiment {mode_text} start accepted")
        run_id = manager.start_experiment(summary.path, dry_run=dry_run)
        write_tui_debug(f"experiment {mode_text} started as {run_id}")
        self._set_status_message(
            f"{mode_text.title()} started as {run_id}. "
            "Open it from the sidebar to view live output."
        )

    def focus_search(self) -> None:
        pass

    def clear_filter_or_blur(self) -> None:
        pass
