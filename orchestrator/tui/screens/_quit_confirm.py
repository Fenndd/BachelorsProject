"""Quit confirmation modal screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class QuitConfirmScreen(ModalScreen[bool]):
    """Ask for confirmation when active runs would be cancelled."""

    def __init__(self, active_run_count: int, legacy_count: int = 0) -> None:
        super().__init__()
        self._count = active_run_count
        self._active_run_count = active_run_count
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
                f"There are {self._active_run_count} active run(s)."
                f"{legacy_line}\nCancel active runs and quit?"
            )
            with Horizontal():
                yield Button(
                    "Cancel Active Runs & Quit",
                    id="quit-confirm-yes",
                    variant="error",
                )
                yield Button("Stay", id="quit-confirm-no", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-confirm-yes":
            self.dismiss(True)
        elif event.button.id == "quit-confirm-no":
            self.dismiss(False)
