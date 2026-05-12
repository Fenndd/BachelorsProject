"""Doctor screen for project and environment diagnostics."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from orchestrator.control import load_environment, read_project_status, summarize_environment


def _format_directory_status() -> str:
    status = read_project_status()
    lines = [
        f"Repository: {status.repo_root}",
        f"Branch: {status.git_branch or 'unknown'}",
        f"Dirty worktree: {'unknown' if status.dirty_worktree is None else str(status.dirty_worktree).lower()}",
        "",
        "Directories:",
    ]
    lines.extend(
        f"  {name}/: {'ok' if exists else 'missing'}"
        for name, exists in status.directories.items()
    )
    return "\n".join(lines)


def _format_environment_status() -> str:
    statuses = load_environment()
    summary = summarize_environment(statuses)
    lines = [
        f"Environment: {summary.label}",
        f"API keys: {summary.api_keys_label}",
        f".env.local: {'found' if summary.env_local_exists else 'missing'}",
        "",
        "Variables:",
    ]
    for status in statuses:
        value = status.display_value or "-"
        lines.append(
            f"  {status.name}: {status.status} [{status.source}] {value} - {status.message}"
        )
    if not summary.env_local_exists:
        lines.extend(
            [
                "",
                "Hint: copy .env.example to .env.local and fill local paths/API keys.",
            ]
        )
    return "\n".join(lines)


class DoctorScreen(Screen[None]):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main"):
            yield Static("Doctor", classes="title")
            yield Static(
                "Project structure and local environment diagnostics.",
                classes="subtitle",
            )
            yield Static(_format_directory_status(), classes="panel")
            yield Static(_format_environment_status(), classes="panel")
            yield Static("Full build/run checks will be added later.", classes="panel")
            yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
