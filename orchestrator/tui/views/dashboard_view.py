"""Dashboard view showing project and environment summary."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Static

from orchestrator.control import load_environment, read_project_status, summarize_environment


def _format_dashboard() -> str:
    status = read_project_status()
    env_statuses = load_environment()
    env_summary = summarize_environment(env_statuses)
    git_branch = status.git_branch or "unknown"
    dirty = "unknown" if status.dirty_worktree is None else str(status.dirty_worktree).lower()
    directory_lines = [
        f"  {name}/: {'ok' if exists else 'missing'}"
        for name, exists in status.directories.items()
    ]
    return (
        f"Repository: {status.repo_root}\n"
        f"Branch: {git_branch}\n"
        f"Dirty worktree: {dirty}\n"
        f"Environment: {env_summary.label}\n"
        f"API keys: {env_summary.api_keys_label}\n"
        + "Directories:\n"
        + "\n".join(directory_lines)
    )


class DashboardView(Widget):
    """Embedded dashboard showing project/environment summary and quick actions."""

    def __init__(self) -> None:
        super().__init__(id="view-dashboard")

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Dashboard", classes="title")
            yield Static(
                "Interactive control layer for LLM optimization experiments",
                classes="subtitle",
            )
            yield Static(_format_dashboard(), id="dashboard-panel", classes="panel")
            yield Static(
                "Active runs are visible in the sidebar. "
                "Click a run to open its live output.",
                classes="panel",
            )
            with Horizontal():
                yield Button("Refresh", id="dashboard-refresh")
                yield Button("Go to Baseline", id="goto-baseline")
                yield Button("Go to Experiments", id="goto-experiments")
                yield Button("Go to Results", id="goto-results")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dashboard-refresh":
            self.query_one("#dashboard-panel", Static).update(_format_dashboard())
            return
        view_by_button = {
            "goto-baseline": "view-baseline",
            "goto-experiments": "view-experiments",
            "goto-results": "view-results",
        }
        view_id = view_by_button.get(event.button.id or "")
        if view_id is None:
            return
        show_view = getattr(self.screen, "action_show_view", None)
        if callable(show_view):
            show_view(view_id)
