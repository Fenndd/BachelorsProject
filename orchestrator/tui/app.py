"""Textual application entry point."""

from __future__ import annotations

from textual.app import App

from orchestrator.tui.screens.main_screen import MainScreen


class OptimizerTuiApp(App[None]):
    """Interactive terminal UI skeleton for the optimizer project."""

    TITLE = "Bachelor Project Optimizer"
    BINDINGS = [("ctrl+q", "quit", "Quit")]
    CSS = """
    Screen {
        background: #0f172a;
        color: #dbeafe;
    }

    Header, Footer {
        background: #111827;
        color: #e5e7eb;
    }

    #main {
        padding: 1 2;
    }

    .title {
        text-style: bold;
        color: #67e8f9;
        margin-bottom: 1;
    }

    .subtitle {
        color: #93c5fd;
        margin-bottom: 1;
    }

    .panel {
        border: solid #334155;
        padding: 1 2;
        margin-bottom: 1;
    }

    .actions {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        margin-top: 1;
    }

    Button {
        width: 100%;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(MainScreen())
