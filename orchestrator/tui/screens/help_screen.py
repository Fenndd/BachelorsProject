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
                "This is the first skeleton of the Interactive Terminal Control Layer.",
                classes="subtitle",
            )
            yield Static(
                "Use the main screen to inspect repository status and open placeholder "
                "controls. Real baseline and experiment launching will be connected in "
                "later architecture steps.",
                classes="panel",
            )
            yield Static(
                "CLI entry points:\n"
                "  python -m orchestrator.cli.app --help\n"
                "  python -m orchestrator.cli.app doctor\n"
                "  python -m orchestrator.cli.app tui",
                classes="panel",
            )
            yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
