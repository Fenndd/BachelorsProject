"""Textual application entry point."""

from __future__ import annotations

from textual.app import App

from orchestrator.tui.screens.main_screen import MainScreen


class OptimizerTuiApp(App[None]):
    """Interactive terminal UI skeleton for the optimizer project."""

    TITLE = "3D Vision Algorithms Optimizer"
    BINDINGS = [("ctrl+q", "quit", "Quit")]
    CSS = """
    Screen {
        background: #d8c3a5;
        color: #111827;
        text-style: bold;
    }

    Header, Footer {
        background: #1f2937;
        color: #f8fafc;
        text-style: bold;
    }

    #main {
        padding: 1 2;
        height: 1fr;
    }

    Static {
        text-style: bold;
    }

    .title {
        text-style: bold;
        color: #111827;
        margin-bottom: 1;
    }

    .subtitle {
        text-style: bold;
        color: #1f2937;
        margin-bottom: 1;
    }

    .panel {
        background: #2f3136;
        color: #f8fafc;
        border: solid #6b7280;
        padding: 1 2;
        margin-bottom: 1;
        text-style: bold;
    }

    ListView {
        background: #2f3136;
        color: #f8fafc;
        text-style: bold;
    }

    RichLog {
        background: #2f3136;
        color: #f8fafc;
        text-style: bold;
    }

    .actions {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        margin-top: 1;
    }

    Button {
        width: 100%;
        text-style: bold;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.active_processes = 0

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    def register_process(self) -> None:
        self.active_processes += 1

    def unregister_process(self) -> None:
        self.active_processes = max(0, self.active_processes - 1)

    def has_active_processes(self) -> bool:
        return self.active_processes > 0

    def action_quit(self) -> None:
        if self.has_active_processes():
            self.notify(
                "A baseline or experiment run is still active. Wait for it to finish before quitting.",
                severity="warning",
            )
            return
        self.exit()
