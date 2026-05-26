"""Textual application entry point."""

from __future__ import annotations

import time

from textual.app import App

from orchestrator.tui.active_runs import ActiveRunsManager
from orchestrator.tui.debug_log import write_tui_debug
from orchestrator.tui.screens._quit_confirm import QuitConfirmScreen
from orchestrator.tui.screens.main_screen import MainScreen


class OptimizerTuiApp(App[None]):
    """Interactive terminal UI for the optimizer project."""

    TITLE = "3D Vision Algorithms Optimizer"
    BINDINGS = [("ctrl+q", "quit", "Quit")]
    CSS_PATH = ["styles/app.tcss", "styles/sidebar.tcss", "styles/views.tcss"]

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
        active_run_count = self.active_runs_manager.active_count()
        legacy_count = self.active_processes
        if active_run_count == 0 and legacy_count == 0:
            self.exit()
            return
        self.push_screen(
            QuitConfirmScreen(active_run_count, legacy_count),
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
