"""Reusable placeholder screen for future TUI actions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static


class PlaceholderScreen(Screen[None]):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self.placeholder_title = title
        self.message = message

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main"):
            yield Static(self.placeholder_title, classes="title")
            yield Static(self.message, classes="panel")
            yield Button("Back", id="back")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
