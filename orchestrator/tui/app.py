"""Textual application entry point."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Static

from orchestrator.tui.active_runs import ActiveRunsManager
from orchestrator.tui.screens.main_screen import MainScreen


class QuitConfirmScreen(ModalScreen[bool]):
    """Ask for confirmation when active runs would be cancelled."""

    DEFAULT_CSS = """
    QuitConfirmScreen {
        align: center middle;
    }

    #quit-confirm-dialog {
        background: #1f2937;
        border: solid #ef4444;
        padding: 2 3;
        width: 52;
        height: auto;
    }

    #quit-confirm-dialog Static {
        text-style: bold;
        color: #f8fafc;
        margin-bottom: 1;
    }

    #quit-confirm-dialog Button {
        width: 100%;
        text-style: bold;
    }
    """

    def __init__(self, count: int) -> None:
        super().__init__()
        self._count = count

    def compose(self) -> ComposeResult:
        with Container(id="quit-confirm-dialog"):
            yield Static(
                f"There are {self._count} active experiment run(s). "
                "Cancel them and quit?"
            )
            with Horizontal():
                yield Button(
                    "Cancel Runs & Quit",
                    id="quit-confirm-yes",
                    variant="error",
                )
                yield Button("Stay", id="quit-confirm-no", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-confirm-yes":
            self.dismiss(True)
        elif event.button.id == "quit-confirm-no":
            self.dismiss(False)


class OptimizerTuiApp(App[None]):
    """Interactive terminal UI for the optimizer project."""

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

    #results-list {
        height: 7;
        min-height: 7;
    }

    #result-summary-panel {
        height: 14;
        min-height: 14;
    }

    #results-status {
        height: 4;
        min-height: 4;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.active_processes = 0
        self.active_runs_manager = ActiveRunsManager(self)

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    def register_process(self) -> None:
        self.active_processes += 1

    def unregister_process(self) -> None:
        self.active_processes = max(0, self.active_processes - 1)

    def has_active_processes(self) -> bool:
        return self.active_processes > 0

    async def action_quit(self) -> None:
        count = self.active_runs_manager.active_count()
        if count == 0:
            self.exit()
            return
        self.push_screen(QuitConfirmScreen(count), callback=self._on_quit_confirm)

    def _on_quit_confirm(self, confirmed: bool | None) -> None:
        if confirmed:
            self.active_runs_manager.cancel_all()
            self.set_timer(0.5, self.exit)
