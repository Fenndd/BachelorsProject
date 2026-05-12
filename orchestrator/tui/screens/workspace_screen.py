"""Workspace status and safe cleanup screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from orchestrator.control import (
    CleanupResult,
    WorkspaceStatus,
    clean_workspace_all,
    clean_workspace_candidates,
    clean_workspace_experiments,
    get_workspace_status,
)


def _format_bytes(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _format_status(status: WorkspaceStatus) -> str:
    return "\n".join(
        [
            f"Path: {status.path}",
            f"Exists: {str(status.exists).lower()}",
            f"Total files: {status.total_files}",
            f"Total directories: {status.total_dirs}",
            f"Total size: {_format_bytes(status.total_size_bytes)}",
            f"Candidate workspaces: {len(status.candidate_workspaces)}",
            f"Experiment workspaces: {len(status.experiment_workspaces)}",
            f"Other entries: {len(status.other_entries)}",
            "",
            "Cleanup only affects workspace/ and never deletes results/.",
        ]
    )


def _format_cleanup(result: CleanupResult) -> str:
    lines = [
        f"Cleanup: {result.kind}",
        f"Deleted paths: {result.deleted_paths_count}",
        f"Deleted files: {result.deleted_files_count}",
        f"Deleted bytes estimate: {_format_bytes(result.deleted_bytes_estimate)}",
    ]
    if result.errors:
        lines.append("Errors:")
        lines.extend(f"  {error}" for error in result.errors)
    return "\n".join(lines)


class WorkspaceScreen(Screen[None]):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._pending_cleanup: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main"):
            yield Static("Workspace", classes="title")
            yield Static("Inspect and clean temporary workspace data.", classes="subtitle")
            yield Static(_format_status(get_workspace_status()), id="workspace-status", classes="panel")
            yield Static("Status: idle", id="workspace-message", classes="panel")
            with Horizontal(classes="actions"):
                yield Button("Refresh", id="refresh")
                yield Button("Clean Candidates", id="clean-candidates")
                yield Button("Clean Experiments", id="clean-experiments")
                yield Button("Clean All", id="clean-all", variant="warning")
                yield Button("Back", id="back")
        yield Footer()

    def _refresh(self) -> None:
        self.query_one("#workspace-status", Static).update(_format_status(get_workspace_status()))

    def _set_message(self, message: str) -> None:
        self.query_one("#workspace-message", Static).update(f"Status: {message}")

    def _cleanup(self, kind: str) -> None:
        if self._pending_cleanup != kind:
            self._pending_cleanup = kind
            self._set_message(
                f"Click {kind} again to confirm. Cleanup only affects workspace/ and never results/."
            )
            return
        self._pending_cleanup = None
        cleanup = {
            "clean-candidates": clean_workspace_candidates,
            "clean-experiments": clean_workspace_experiments,
            "clean-all": clean_workspace_all,
        }[kind]
        result = cleanup()
        self._refresh()
        self._set_message(_format_cleanup(result))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "back":
            self.app.pop_screen()
            return
        if button_id == "refresh":
            self._pending_cleanup = None
            self._refresh()
            self._set_message("refreshed")
            return
        if button_id in {"clean-candidates", "clean-experiments", "clean-all"}:
            self._cleanup(button_id)
