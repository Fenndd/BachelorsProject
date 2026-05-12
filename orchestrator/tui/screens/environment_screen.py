"""Environment diagnostics screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from orchestrator.control import load_environment, summarize_environment


def _format_environment() -> str:
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
    lines.extend(
        [
            "",
            "Hint: edit .env.local manually or copy .env.example to .env.local.",
            "Secrets are masked and are never displayed in full.",
        ]
    )
    return "\n".join(lines)


class EnvironmentScreen(Screen[None]):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            yield Static("Environment", classes="title")
            yield Static("Local environment diagnostics for CLI/TUI launchers.", classes="subtitle")
            yield Static(_format_environment(), id="environment-status", classes="panel")
            yield Button("Refresh", id="refresh")
            yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
            return
        if event.button.id == "refresh":
            self.query_one("#environment-status", Static).update(_format_environment())
