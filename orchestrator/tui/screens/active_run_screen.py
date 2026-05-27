"""Live output screen for a single ActiveRun."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RichLog, Static

from orchestrator.tui.active_runs import ActiveRun, ActiveRunStatus
from orchestrator.tui.debug_log import write_tui_debug


def _status_display(status: ActiveRunStatus) -> str:
    display: dict[ActiveRunStatus, str] = {
        "starting": "[yellow]starting[/yellow]",
        "running": "[bold #2563eb]running[/bold #2563eb]",
        "succeeded": "[bold #15803d]succeeded[/bold #15803d]",
        "failed": "[bold #b91c1c]failed[/bold #b91c1c]",
        "cancelled": "[bold #6b7280]cancelled[/bold #6b7280]",
    }
    return display.get(status, status)


def _format_status(run: ActiveRun) -> str:
    items: list[str] = [
        f"Run: {run.run_id}",
        f"Kind: {run.kind}",
    ]
    if run.kind == "baseline":
        items.append("Config: baseline")
        items.append("Mode: baseline")
    else:
        items.append(f"Config: {run.config_path.name}")
        items.append(f"Mode: {'dry-run' if run.dry_run else 'real run'}")
    items.append(f"Status: {_status_display(run.status)}")
    items.append(
        f"Started: {run.started_at.strftime('%Y-%m-%d %H:%M:%S') if run.started_at else '-'}"
    )
    if run.finished_at is not None:
        items.append(
            f"Finished: {run.finished_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    if run.exit_code is not None:
        items.append(f"Exit code: {run.exit_code}")
    if run.latest_result_dir is not None:
        items.append(f"Result dir: {run.latest_result_dir}")
    if run.latest_experiment_dir is not None:
        items.append(f"Experiment dir: {run.latest_experiment_dir}")
    if run.message:
        items.append(f"Message: {run.message}")
    return "\n".join(items)


class ActiveRunScreen(Screen[None]):
    BINDINGS = [("escape", "request_back", "Back")]

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self._run_id = run_id
        self._terminal_statuses: set[ActiveRunStatus] = {
            "succeeded",
            "failed",
            "cancelled",
        }
        self._loaded_count = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            yield Static(f"Run: {self._run_id}", classes="title")
            yield Static("", id="run-status", classes="panel")
            yield RichLog(
                id="run-log",
                classes="panel",
                wrap=True,
                highlight=True,
                auto_scroll=True,
            )
            with Horizontal(classes="run-action-row"):
                yield Button(
                    "Cancel",
                    id="cancel-run",
                    variant="error",
                    classes="run-action-button",
                )
                yield Button(
                    "Back",
                    id="back",
                    classes="run-action-button",
                )
        yield Footer()

    def on_mount(self) -> None:
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            self._set_status_text("Error: active_runs_manager not available on app.")
            return

        run = manager.get(self._run_id)
        if run is None:
            self._set_status_text(f"Error: run {self._run_id} not found.")
            return

        log = self.query_one("#run-log", RichLog)
        snapshot = manager.snapshot_and_attach(self._run_id, self._on_run_update)
        for stream_name, line in snapshot:
            prefix = "[stderr] " if stream_name == "stderr" else ""
            log.write(f"{prefix}{line}")
        self._loaded_count = len(snapshot)

        self._update_status_panel(run)

        if run.status in self._terminal_statuses:
            self.query_one("#cancel-run", Button).disabled = True
        write_tui_debug(f"ActiveRunScreen mounted for {self._run_id}")

    def on_unmount(self) -> None:
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is not None:
            manager.detach(self._run_id, self._on_run_update)
        write_tui_debug(f"ActiveRunScreen unmounted for {self._run_id}")

    def _set_status_text(self, text: str) -> None:
        try:
            self.query_one("#run-status", Static).update(text)
        except Exception:
            pass

    def _update_status_panel(self, run: ActiveRun) -> None:
        self._set_status_text(_format_status(run))
        if run.status in self._terminal_statuses:
            try:
                self.query_one("#cancel-run", Button).disabled = True
            except Exception:
                pass

    def _on_run_update(self, stream_name: str | None, line: str | None) -> None:
        if stream_name is not None and line is not None:
            prefix = "[stderr] " if stream_name == "stderr" else ""
            try:
                self.query_one("#run-log", RichLog).write(f"{prefix}{line}")
            except Exception:
                pass
        else:
            manager = getattr(self.app, "active_runs_manager", None)
            if manager is None:
                return
            run = manager.get(self._run_id)
            if run is None:
                return
            self._update_status_panel(run)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.action_request_back()
            return
        if event.button.id == "cancel-run":
            manager = getattr(self.app, "active_runs_manager", None)
            if manager is not None:
                manager.cancel(self._run_id)
            try:
                self.query_one("#cancel-run", Button).disabled = True
            except Exception:
                pass
            write_tui_debug(f"ActiveRunScreen cancel requested for {self._run_id}")

    def action_request_back(self) -> None:
        self.app.pop_screen()
