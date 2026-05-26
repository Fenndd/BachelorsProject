"""Shared modal dialog for confirming a paid LLM experiment run."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmPaidRunScreen(ModalScreen[bool]):
    """Confirm launching a real experiment that may call paid LLM APIs."""

    DEFAULT_CSS = """
    ConfirmPaidRunScreen {
        align: center middle;
    }
    #paid-run-dialog {
        width: 62;
        height: auto;
        background: #1f2937;
        border: solid #ef4444;
        padding: 2 3;
    }
    #paid-run-dialog Static {
        color: #f8fafc;
        margin-bottom: 1;
    }
    #paid-run-dialog Button {
        width: 100%;
    }
    """

    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self._config_path = config_path

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="paid-run-dialog"):
            yield Static(
                "This will start a real LLM experiment and may use paid LLM API calls.\n"
                f"Config: {self._config_path}"
            )
            with Horizontal():
                yield Button("Confirm Run", id="confirm-paid-run", variant="error")
                yield Button("Cancel", id="cancel-paid-run", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-paid-run":
            self.dismiss(True)
        elif event.button.id == "cancel-paid-run":
            self.dismiss(False)
