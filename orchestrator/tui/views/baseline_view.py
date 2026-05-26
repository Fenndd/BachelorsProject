"""Embedded baseline launch view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Select, Static

from orchestrator.control import list_solver_manifest_options
from orchestrator.tui.debug_log import write_tui_debug

_DEFAULT_SOLVER_VALUE = "__default__"


def _solver_select_options() -> tuple[list[tuple[str, str]], str]:
    options = [
        (option.display_label, option.solver_id)
        for option in list_solver_manifest_options()
    ]
    if not options:
        return ([('Default baseline', _DEFAULT_SOLVER_VALUE)], _DEFAULT_SOLVER_VALUE)
    return (options, options[0][1])


class BaselineView(Widget):
    """Embedded baseline launch view.

    Starts baseline through ActiveRunsManager -- no local queues, watchdog
    timers, or process-registration.
    """

    def __init__(self) -> None:
        super().__init__(id="view-baseline")
        self._solver_options, self._initial_solver = _solver_select_options()

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Baseline", classes="title")
            yield Static(
                "Runs CMake configure/build, adapter validation, "
                "benchmark parsing, and artifact saving for the selected algorithm.",
                classes="subtitle",
            )
            yield Static("Algorithm / Solver", classes="field-label")
            yield Select(
                self._solver_options,
                value=self._initial_solver,
                allow_blank=False,
                id="baseline-solver",
            )
            yield Static(
                "Status: idle", id="baseline-status", classes="panel"
            )
            with Horizontal(classes="actions"):
                yield Button("Start Baseline", id="start-baseline")
                yield Button("Refresh Solvers", id="refresh-solvers")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-baseline":
            self._start_baseline()
        elif event.button.id == "refresh-solvers":
            self._refresh_solvers()

    def _selected_solver_id(self) -> str | None:
        try:
            value = self.query_one("#baseline-solver", Select).value
        except Exception:
            value = self._initial_solver
        if not isinstance(value, str) or value == _DEFAULT_SOLVER_VALUE:
            return None
        return value

    def _start_baseline(self) -> None:
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            self._set_status("Error: active_runs_manager not available.")
            write_tui_debug("baseline view start blocked: manager missing")
            return

        write_tui_debug("baseline view start accepted")
        solver_id = self._selected_solver_id()
        run_id = manager.start_baseline(solver_id=solver_id)
        write_tui_debug(f"baseline started as {run_id}")
        self._set_status(
            f"Started as {run_id}. Open it from the sidebar to view live output."
        )

    def _refresh_solvers(self) -> None:
        current_value: str | None = None
        try:
            selected = self.query_one("#baseline-solver", Select).value
            current_value = selected if isinstance(selected, str) else None
        except Exception:
            current_value = None
        self._solver_options, self._initial_solver = _solver_select_options()
        try:
            solver_select = self.query_one("#baseline-solver", Select)
            solver_select.set_options(self._solver_options)
            values = {value for _label, value in self._solver_options}
            solver_select.value = (
                current_value
                if current_value in values
                else (self._initial_solver if self._initial_solver in values else _DEFAULT_SOLVER_VALUE)
            )
        except Exception:
            pass
        self._set_status("Solver list refreshed.")

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#baseline-status", Static).update(text)
        except Exception:
            pass

    def focus_search(self) -> None:
        pass

    def clear_filter_or_blur(self) -> None:
        pass
