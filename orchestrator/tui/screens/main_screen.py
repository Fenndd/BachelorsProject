"""Main screen: persistent two-pane layout with sidebar navigation."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import ContentSwitcher, Footer, Header, ListItem, ListView, Static

from orchestrator.tui.active_runs import ActiveRunSummary
from orchestrator.tui.screens.active_run_screen import ActiveRunScreen
from orchestrator.tui.screens.config_builder_screen import ConfigBuilderScreen
from orchestrator.tui.views.baseline_view import BaselineView
from orchestrator.tui.views.dashboard_view import DashboardView
from orchestrator.tui.views.experiments_view import ExperimentsView
from orchestrator.tui.views.help_view import HelpView
from orchestrator.tui.views.results_view import ResultsView
from orchestrator.tui.views.system_view import SystemView

_NAV_ITEMS: list[tuple[str, str]] = [
    ("Dashboard", "view-dashboard"),
    ("Baseline", "view-baseline"),
    ("Experiments", "view-experiments"),
    ("Results", "view-results"),
    ("Config Builder", "__config-builder"),
    ("System", "view-system"),
    ("Help", "view-help"),
]

_VIEW_NAV_INDEX = {
    target: index
    for index, (_label, target) in enumerate(_NAV_ITEMS)
    if target.startswith("view-")
}

_STATUS_MARKER: dict[str, str] = {
    "starting": "[bold #2563eb]\u25cf[/bold #2563eb]",
    "running": "[bold #2563eb]\u25cf[/bold #2563eb]",
    "succeeded": "[bold #15803d]\u25cf[/bold #15803d]",
    "failed": "[bold #b91c1c]\u25cf[/bold #b91c1c]",
    "cancelled": "[bold #6b7280]\u25cf[/bold #6b7280]",
}

_STATUS_LABEL: dict[str, str] = {
    "starting": "[#2563eb]starting[/]",
    "running": "[bold #2563eb]running[/bold #2563eb]",
    "succeeded": "[bold #15803d]succeeded[/bold #15803d]",
    "failed": "[bold #b91c1c]failed[/bold #b91c1c]",
    "cancelled": "[bold #6b7280]cancelled[/bold #6b7280]",
}


def _duration_str(started: datetime, finished: datetime | None) -> str:
    now = datetime.now().astimezone()
    end = finished if finished is not None else now
    total = int((end - started).total_seconds())
    if total < 0:
        total = 0
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _format_run_label(run: ActiveRunSummary) -> str:
    marker = _STATUS_MARKER.get(run.status, "\u25cf")
    status_label = _STATUS_LABEL.get(run.status, run.status)
    duration = _duration_str(run.started_at, run.finished_at)

    config_info = ""
    if run.kind == "experiment":
        config_info = f" {run.config_path.name}"

    return (
        f"{marker} {run.run_id} "
        f"{run.kind} {status_label} "
        f"{duration}{config_info}"
    )


class MainScreen(Screen[None]):
    BINDINGS = [
        Binding("1", "show_view('view-dashboard')", "Dashboard"),
        Binding("2", "show_view('view-baseline')", "Baseline"),
        Binding("3", "show_view('view-experiments')", "Experiments"),
        Binding("4", "show_view('view-results')", "Results"),
        Binding("5", "show_view('view-system')", "System"),
        Binding("6", "show_view('view-help')", "Help"),
        Binding("f1,question_mark", "show_view('view-help')", "Help"),
        Binding("slash", "focus_search", "Search"),
        Binding("escape", "clear_filter_or_blur", "Clear Filter"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="layout"):
            with Vertical(id="sidebar"):
                yield Static("3D Vision Algorithms\nOptimizer", classes="sidebar-title")
                yield ListView(
                    *[ListItem(Static(label)) for label, _ in _NAV_ITEMS],
                    id="nav",
                )
                yield Static("", classes="sidebar-separator")
                yield Static("Active runs (0)", id="active-runs-title")
                yield ListView(id="active-runs")
            with ContentSwitcher(id="content", initial="view-dashboard"):
                yield DashboardView()
                yield BaselineView()
                yield ExperimentsView()
                yield ResultsView()
                yield SystemView()
                yield HelpView()
        yield Footer()

    def on_mount(self) -> None:
        self._switch_to_view("view-dashboard")
        self._refresh_active_runs()
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is not None:
            manager.attach_global(self._refresh_active_runs)

    def on_unmount(self) -> None:
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is not None:
            manager.detach_global(self._refresh_active_runs)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "nav":
            self._handle_nav_selection(event)
        elif event.list_view.id == "active-runs":
            self._handle_active_run_selection(event)

    def _handle_nav_selection(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or index < 0 or index >= len(_NAV_ITEMS):
            return
        _label, target = _NAV_ITEMS[index]
        if target == "__config-builder":
            self.app.push_screen(ConfigBuilderScreen())
        else:
            self._switch_to_view(target)

    def _handle_active_run_selection(self, event: ListView.Selected) -> None:
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            return
        runs = manager.list()
        index = event.list_view.index
        if index is None or index < 0 or index >= len(runs):
            return
        run_id = runs[index].run_id
        self.app.push_screen(ActiveRunScreen(run_id))

    def _switch_to_view(self, view_id: str) -> None:
        content = self.query_one("#content", ContentSwitcher)
        content.current = view_id
        self._sync_nav_selection(view_id)

    def _sync_nav_selection(self, view_id: str) -> None:
        index = _VIEW_NAV_INDEX.get(view_id)
        if index is None:
            return
        nav = self.query_one("#nav", ListView)
        if nav.index != index:
            nav.index = index

    # ------------------------------------------------------------------
    # Keyboard bindings
    # ------------------------------------------------------------------

    def action_show_view(self, view_id: str) -> None:
        self._switch_to_view(view_id)

    def action_focus_search(self) -> None:
        content = self.query_one("#content", ContentSwitcher)
        current = content.current
        if current is None:
            return
        child = self.query_one(f"#{current}")
        method = getattr(child, "focus_search", None)
        if callable(method):
            method()

    def action_clear_filter_or_blur(self) -> None:
        content = self.query_one("#content", ContentSwitcher)
        current = content.current
        if current is None:
            return
        child = self.query_one(f"#{current}")
        method = getattr(child, "clear_filter_or_blur", None)
        if callable(method):
            method()

    # ------------------------------------------------------------------
    # Active runs sidebar
    # ------------------------------------------------------------------

    def _refresh_active_runs(self) -> None:
        manager = getattr(self.app, "active_runs_manager", None)
        if manager is None:
            return
        runs = manager.list()
        list_view = self.query_one("#active-runs", ListView)
        list_view.clear()
        if not runs:
            list_view.append(ListItem(Static("[italic #6b7280]No active or recent runs.[/italic #6b7280]")))
        else:
            for r in runs:
                list_view.append(ListItem(Static(_format_run_label(r))))
        self._update_active_run_count(manager.active_count())

    def _update_active_run_count(self, count: int) -> None:
        try:
            self.query_one("#active-runs-title", Static).update(f"Active runs ({count})")
        except Exception:
            pass
