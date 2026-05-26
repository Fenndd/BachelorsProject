"""System view consolidating Environment, Doctor, and Workspace diagnostics."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Static

from orchestrator.control import (
    CleanupResult,
    WorkspaceStatus,
    clean_workspace_all,
    clean_workspace_candidates,
    clean_workspace_experiments,
    get_workspace_status,
    load_environment,
    read_project_status,
    summarize_environment,
)


def _format_bytes(size: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _format_environment() -> str:
    statuses = load_environment()
    summary = summarize_environment(statuses)
    lines = [
        f"Environment: {summary.label}",
        f"API keys: {summary.api_keys_label}",
        f".env.local: {'found' if summary.env_local_exists else 'missing'}",
        "",
        "Variables:",
    ]
    for s in statuses:
        value = s.display_value or "-"
        lines.append(f"  {s.name}: {s.status} [{s.source}] {value} - {s.message}")
    if not summary.env_local_exists:
        lines.extend(
            [
                "",
                "Hint: copy .env.example to .env.local and fill local paths/API keys.",
            ]
        )
    lines.extend(
        [
            "",
            "Secrets are masked and are never displayed in full.",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Doctor helpers
# ---------------------------------------------------------------------------


def _format_doctor() -> str:
    status = read_project_status()
    git_branch = status.git_branch or "unknown"
    dirty = "unknown" if status.dirty_worktree is None else str(status.dirty_worktree).lower()
    lines = [
        f"Repository: {status.repo_root}",
        f"Branch: {git_branch}",
        f"Dirty worktree: {dirty}",
        "",
        "Directories:",
    ]
    lines.extend(
        f"  {name}/: {'ok' if exists else 'missing'}"
        for name, exists in status.directories.items()
    )
    lines.extend(
        [
            "",
            "Full build/run checks will be added later.",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------


def _format_workspace(status: WorkspaceStatus) -> str:
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


# ---------------------------------------------------------------------------
# SystemView
# ---------------------------------------------------------------------------


class SystemView(Widget):
    """Embedded view with Environment, Doctor, and Workspace sections."""

    def __init__(self) -> None:
        super().__init__(id="view-system")
        self._pending_cleanup: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="system-view"):
            with VerticalScroll(id="system-scroll"):
                yield Static("System", classes="title")
                yield Static(
                    "Environment, project, and workspace diagnostics in one view.",
                    classes="subtitle",
                )

                # --- Environment section ---
                yield Static("Environment", classes="title")
                yield Static(
                    _format_environment(),
                    id="system-environment",
                    classes="panel",
                )
                yield Button("Refresh Environment", id="refresh-environment")

                # --- Doctor section ---
                yield Static("Doctor", classes="title")
                yield Static(
                    _format_doctor(),
                    id="system-doctor",
                    classes="panel",
                )
                yield Button("Refresh Doctor", id="refresh-doctor")

                # --- Workspace section ---
                yield Static("Workspace", classes="title")
                yield Static(
                    _format_workspace(get_workspace_status()),
                    id="system-workspace",
                    classes="panel",
                )
                yield Static("Status: idle", id="workspace-message", classes="panel")
                yield Static("", classes="bottom-spacer")
            with Horizontal(classes="actions", id="system-actions"):
                yield Button("Refresh Workspace", id="refresh-workspace")
                yield Button("Clean Candidates", id="clean-candidates")
                yield Button("Clean Experiments", id="clean-experiments")
                yield Button("Clean All", id="clean-all", variant="warning")

    # --- Helpers ---

    def clear_filter_or_blur(self) -> None:
        pass

    def _refresh_environment(self) -> None:
        self.query_one("#system-environment", Static).update(_format_environment())

    def _refresh_doctor(self) -> None:
        self.query_one("#system-doctor", Static).update(_format_doctor())

    def _refresh_workspace(self) -> None:
        self.query_one("#system-workspace", Static).update(
            _format_workspace(get_workspace_status())
        )

    def _set_message(self, message: str) -> None:
        self.query_one("#workspace-message", Static).update(f"Status: {message}")

    def _cleanup(self, kind: str) -> None:
        if self._pending_cleanup != kind:
            self._pending_cleanup = kind
            self._set_message(
                f"Click {kind} again to confirm. "
                "Cleanup only affects workspace/ and never results/."
            )
            return
        self._pending_cleanup = None
        cleanup_fn = {
            "clean-candidates": clean_workspace_candidates,
            "clean-experiments": clean_workspace_experiments,
            "clean-all": clean_workspace_all,
        }[kind]
        result = cleanup_fn()
        self._refresh_workspace()
        self._set_message(_format_cleanup(result))

    # --- Button handling ---

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "refresh-environment":
            self._refresh_environment()
            return
        if button_id == "refresh-doctor":
            self._refresh_doctor()
            return
        if button_id == "refresh-workspace":
            self._pending_cleanup = None
            self._refresh_workspace()
            self._set_message("refreshed")
            return
        if button_id in {"clean-candidates", "clean-experiments", "clean-all"}:
            self._cleanup(button_id)
            return
