"""Compatibility screen for the embedded config builder view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header

from orchestrator.tui.views.config_builder_view import ConfigBuilderView


class ConfigBuilderScreen(Screen[None]):
    """Standalone wrapper used by legacy callers."""

    BINDINGS = [("escape", "request_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield ConfigBuilderView()
        yield Footer()

    def action_request_back(self) -> None:
        self.app.pop_screen()


__all__ = ["ConfigBuilderScreen"]
