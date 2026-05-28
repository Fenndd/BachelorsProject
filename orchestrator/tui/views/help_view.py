"""Help view for the Textual control layer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Static


class HelpView(Widget):
    """Embedded help view with updated navigation, hotkeys, and safety notes."""

    def __init__(self) -> None:
        super().__init__(id="view-help")

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Help", classes="title")
            yield Static(
                "Interactive Terminal Control Layer for the bachelor project optimizer.",
                classes="subtitle",
            )
            yield Static(
                "Sidebar Navigation:\n"
                "  Dashboard (1): project and environment summary\n"
                "  Baseline (2): launch the existing baseline automation with live logs\n"
                "  Experiments (3): select configs, dry-run, or confirm real runs\n"
                "  Results (4): read-only navigation for saved artifacts\n"
                "  Config Builder: interactive JSON config builder\n"
                "  System (5): environment, project, and workspace diagnostics\n"
                "  Help (6 / F1 / ?): this reference screen\n"
                "  Active runs panel: always visible, click a run to open its live output",
                classes="panel",
            )
            yield Static(
                "CLI entry points:\n"
                "  py -m orchestrator.cli.app --help\n"
                "  py -m orchestrator.cli.app doctor\n"
                "  py -m orchestrator.cli.app baseline run\n"
                "  py -m orchestrator.cli.app experiment list\n"
                "  py -m orchestrator.cli.app results list\n"
                "  py -m orchestrator.cli.app workspace status\n"
                "  py -m orchestrator.cli.app tui",
                classes="panel",
            )
            yield Static(
                "On Windows, examples use the Python launcher `py`.\n\n"
                "Diagnostic log: TUI messages may be written to workspace/tui_debug.log.\n"
                "It is a local debug-only file and can be removed manually or via the\n"
                "workspace cleanup commands.",
                classes="panel",
            )
            yield Static(
                "Hotkeys:\n"
                "  Ctrl+Q: quit\n"
                "  1: Dashboard\n"
                "  2: Baseline\n"
                "  3: Experiments\n"
                "  4: Results\n"
                "  5: System\n"
                "  6: Help\n"
                "  /: focus search/filter in current view when supported\n"
                "  F1 or ?: Help\n"
                "  Esc: clear filter / blur current view when supported",
                classes="panel",
            )
            yield Static(
                "Safety notes:\n"
                "  Results browsing is read-only.\n"
                "  Workspace cleanup only affects workspace/ and never results/.\n"
                "  Real experiments may use API tokens from .env.local.\n"
                "  Active baseline/experiment runs can be cancelled from the live run\n"
                "    view or on quit confirmation if supported by the active run manager.\n"
                "  The control layer does not automatically modify the main cpp/ source tree.",
                classes="panel",
            )

    def clear_filter_or_blur(self) -> None:
        pass
