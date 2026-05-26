"""Textual application entry point."""

from __future__ import annotations

import time

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Static

from orchestrator.tui.active_runs import ActiveRunsManager
from orchestrator.tui.debug_log import write_tui_debug
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

    def __init__(self, experiment_count: int, legacy_count: int = 0) -> None:
        super().__init__()
        self._count = experiment_count
        self._experiment_count = experiment_count
        self._legacy_count = legacy_count

    def compose(self) -> ComposeResult:
        legacy_line = ""
        if self._legacy_count:
            legacy_line = (
                f"\nThere are also {self._legacy_count} legacy process(es). "
                "They may be interrupted when the app closes."
            )
        with Container(id="quit-confirm-dialog"):
            yield Static(
                f"There are {self._experiment_count} active experiment run(s)."
                f"{legacy_line}\nCancel active experiment runs and quit?"
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
        self._quit_wait_started: float | None = None
        self._quit_wait_timer = None
        self._quit_wait_timeout_seconds = 8.0

    def on_mount(self) -> None:
        self.push_screen(MainScreen())

    def register_process(self) -> None:
        self.active_processes += 1

    def unregister_process(self) -> None:
        self.active_processes = max(0, self.active_processes - 1)

    def has_active_processes(self) -> bool:
        return self.active_processes > 0

    async def action_quit(self) -> None:
        experiment_count = self.active_runs_manager.active_count()
        legacy_count = self.active_processes
        if experiment_count == 0 and legacy_count == 0:
            self.exit()
            return
        self.push_screen(
            QuitConfirmScreen(experiment_count, legacy_count),
            callback=self._on_quit_confirm,
        )

    def _on_quit_confirm(self, confirmed: bool | None) -> None:
        if confirmed:
            self.active_runs_manager.cancel_all()
            self._quit_wait_started = time.monotonic()
            self._start_quit_wait_timer()

    def _start_quit_wait_timer(self) -> None:
        self._stop_quit_wait_timer()
        self._quit_wait_timer = self.set_interval(0.2, self._finish_quit_when_ready)
        self._finish_quit_when_ready()

    def _stop_quit_wait_timer(self) -> None:
        timer = self._quit_wait_timer
        self._quit_wait_timer = None
        if timer is None:
            return
        stop = getattr(timer, "stop", None)
        if callable(stop):
            stop()
            return
        pause = getattr(timer, "pause", None)
        if callable(pause):
            pause()

    def _finish_quit_when_ready(self) -> None:
        active_count = self.active_runs_manager.active_count()
        started = self._quit_wait_started or time.monotonic()
        if active_count == 0:
            self._stop_quit_wait_timer()
            self.exit()
            return
        if time.monotonic() - started >= self._quit_wait_timeout_seconds:
            write_tui_debug(
                f"quit timeout expired with {active_count} active run(s) still stopping"
            )
            self._stop_quit_wait_timer()
            self.exit()


def main() -> None:
    OptimizerTuiApp().run()


if __name__ == "__main__":
    main()
