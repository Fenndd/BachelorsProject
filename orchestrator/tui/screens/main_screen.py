"""Main screen for the Textual control layer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static

from orchestrator.control import load_environment, read_project_status, summarize_environment
from orchestrator.control import placeholders
from orchestrator.tui.screens.active_run_screen import ActiveRunScreen
from orchestrator.tui.screens.baseline_screen import BaselineScreen
from orchestrator.tui.screens.config_builder_screen import ConfigBuilderScreen
from orchestrator.tui.screens.doctor_screen import DoctorScreen
from orchestrator.tui.screens.environment_screen import EnvironmentScreen
from orchestrator.tui.screens.experiment_screen import ExperimentScreen
from orchestrator.tui.screens.help_screen import HelpScreen
from orchestrator.tui.screens.results_screen import ResultsScreen
from orchestrator.tui.screens.workspace_screen import WorkspaceScreen


def _format_run_label(run_summary) -> str:
    from orchestrator.tui.active_runs import ActiveRunSummary

    started = (
        run_summary.started_at.strftime("%H:%M:%S")
        if run_summary.started_at
        else "-"
    )
    mode = "dry" if run_summary.dry_run else "real"
    return (
        f"[{run_summary.run_id}] {run_summary.status}"
        f" | {run_summary.config_path.name}"
        f" | {mode} | {started}"
    )


class MainScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        status = read_project_status()
        env_statuses = load_environment()
        env_summary = summarize_environment(env_statuses)
        directory_lines = [
            f"{name}/: {'ok' if exists else 'missing'}"
            for name, exists in status.directories.items()
        ]
        git_branch = status.git_branch or "unknown"
        dirty = "unknown" if status.dirty_worktree is None else str(status.dirty_worktree).lower()

        yield Header()
        with VerticalScroll(id="main"):
            yield Static("Interactive control layer for LLM optimization experiments", classes="subtitle")
            yield Static(
                f"Repository: {status.repo_root}\n"
                f"Branch: {git_branch}\n"
                f"Dirty worktree: {dirty}\n"
                f"Environment: {env_summary.label}\n"
                f"API keys: {env_summary.api_keys_label}\n\n"
                + "\n".join(directory_lines),
                classes="panel",
            )
            yield Static("Active Runs", classes="subtitle")
            yield ListView(id="active-runs-list", classes="panel")
            yield Button("Refresh Runs", id="refresh-runs")
            with Horizontal(classes="actions"):
                yield Button("Run Baseline", id="run-baseline", variant="primary")
                yield Button("Run Experiment", id="run-experiment")
                yield Button("Build Config", id="build-config")
                yield Button("Browse Results", id="browse-results")
                yield Button("Environment", id="environment")
                yield Button("Doctor", id="doctor")
                yield Button("Workspace", id="workspace")
                yield Button("Help", id="help")
                yield Button("Quit", id="quit", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#active-runs-list", ListView).styles.height = 5
        self._refresh_active_runs()
        self.set_interval(1.5, self._refresh_active_runs)

    def _refresh_active_runs(self) -> None:
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            return
        runs = manager.list()
        list_view = self.query_one("#active-runs-list", ListView)
        list_view.clear()
        if not runs:
            list_view.append(ListItem(Static("No active or recent runs.")))
            return
        for r in runs:
            list_view.append(ListItem(Static(_format_run_label(r))))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "active-runs-list":
            return
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            return
        runs = manager.list()
        index = event.list_view.index
        if index is None or index < 0 or index >= len(runs):
            return
        run_id = runs[index].run_id
        self.app.push_screen(ActiveRunScreen(run_id))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "quit":
            self.app.exit()
            return
        if button_id == "help":
            self.app.push_screen(HelpScreen())
            return
        if button_id == "doctor":
            self.app.push_screen(DoctorScreen())
            return
        if button_id == "run-baseline":
            self.app.push_screen(BaselineScreen())
            return
        if button_id == "run-experiment":
            self.app.push_screen(ExperimentScreen())
            return
        if button_id == "build-config":
            self.app.push_screen(ConfigBuilderScreen())
            return
        if button_id == "browse-results":
            self.app.push_screen(ResultsScreen())
            return
        if button_id == "environment":
            self.app.push_screen(EnvironmentScreen())
            return
        if button_id == "workspace":
            self.app.push_screen(WorkspaceScreen())
            return
        if button_id == "refresh-runs":
            self._refresh_active_runs()
