"""Help screen for the Textual control layer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class HelpScreen(Screen[None]):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            yield Static("Help", classes="title")
            yield Static(
                "Interactive Terminal Control Layer for the bachelor project optimizer.",
                classes="subtitle",
            )
            yield Static(
                "Core actions:\n"
                "  Doctor: project and environment diagnostics\n"
                "  Environment: masked .env.local/process/default settings\n"
                "  Run Baseline: launch the existing baseline automation with live logs\n"
                "  Run Experiment: select configs, dry-run, or confirm real runs\n"
                "  Browse Results: read-only navigation for saved artifacts\n"
                "  Workspace: inspect and clean temporary workspace data",
                classes="panel",
            )
            yield Static(
                "CLI entry points:\n"
                "  python -m orchestrator.cli.app --help\n"
                "  python -m orchestrator.cli.app doctor\n"
                "  python -m orchestrator.cli.app baseline run\n"
                "  python -m orchestrator.cli.app experiment list\n"
                "  python -m orchestrator.cli.app results list\n"
                "  python -m orchestrator.cli.app workspace status\n"
                "  python -m orchestrator.cli.app tui",
                classes="panel",
            )
            yield Static(
                "Hotkeys:\n"
                "  Ctrl+Q: quit\n"
                "  Esc: back from secondary screens\n"
                "  Active baseline/experiment runs must finish before Back, Esc, or Ctrl+Q will leave the screen.",
                classes="panel",
            )
            yield Static(
                "Safety notes:\n"
                "  Results browsing is read-only.\n"
                "  Workspace cleanup only affects workspace/ and never results/.\n"
                "  Real experiments may use API tokens from .env.local.\n"
                "  Baseline and experiment cancellation is not implemented yet.\n"
                "  The control layer does not automatically modify the main cpp/ source tree.",
                classes="panel",
            )
            yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
