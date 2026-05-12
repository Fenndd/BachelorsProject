"""Main screen for the Textual control layer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from orchestrator.control import load_environment, read_project_status, summarize_environment
from orchestrator.control import placeholders
from orchestrator.tui.screens.baseline_screen import BaselineScreen
from orchestrator.tui.screens.doctor_screen import DoctorScreen
from orchestrator.tui.screens.experiment_screen import ExperimentScreen
from orchestrator.tui.screens.help_screen import HelpScreen
from orchestrator.tui.screens.placeholder_screen import PlaceholderScreen
from orchestrator.tui.screens.results_screen import ResultsScreen


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
        with Container(id="main"):
            yield Static("Bachelor Project Optimizer", classes="title")
            yield Static("Interactive Terminal Control Layer skeleton", classes="subtitle")
            yield Static(
                f"Repository: {status.repo_root}\n"
                f"Branch: {git_branch}\n"
                f"Dirty worktree: {dirty}\n"
                f"Environment: {env_summary.label}\n"
                f"API keys: {env_summary.api_keys_label}\n\n"
                + "\n".join(directory_lines),
                classes="panel",
            )
            with Horizontal(classes="actions"):
                yield Button("Run Baseline", id="run-baseline", variant="primary")
                yield Button("Run Experiment", id="run-experiment")
                yield Button("Browse Results", id="browse-results")
                yield Button("Environment", id="environment")
                yield Button("Doctor", id="doctor")
                yield Button("Workspace", id="workspace")
                yield Button("Help", id="help")
                yield Button("Quit", id="quit", variant="error")
        yield Footer()

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
        if button_id == "browse-results":
            self.app.push_screen(ResultsScreen())
            return

        placeholders_by_button = {
            "environment": ("Environment", placeholders.ENVIRONMENT),
            "workspace": ("Workspace", placeholders.WORKSPACE),
        }
        title, message = placeholders_by_button.get(
            button_id or "",
            ("Placeholder", "This action is not implemented yet."),
        )
        self.app.push_screen(PlaceholderScreen(title, message))
