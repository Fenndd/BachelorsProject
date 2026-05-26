"""Read-only results browser view with DataTable, filtering, and artifact open actions."""

from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Select, Static

from orchestrator.control import ResultItem, list_result_items, open_path
from orchestrator.control.open_artifact import OpenArtifactError


def _format_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}"


def _format_item(item: ResultItem | None) -> str:
    if item is None:
        return "No saved results found."
    return "\n".join(
        [
            f"Kind: {_display_kind(item.kind)}",
            f"Name: {item.name}",
            f"Path: {item.path}",
            f"Status: {item.status or 'unknown'}",
            f"Started: {item.started_at or '-'}",
            f"Finished: {item.finished_at or '-'}",
            f"Final selection speedup: {_format_number(item.final_speedup_vs_baseline)}",
            f"Final selection runtime reduction %: {_format_number(item.final_runtime_reduction_percent)}",
            f"Best iteration: {item.final_best_iteration if item.final_best_iteration is not None else '-'}",
            f"Accepted improvements: {item.accepted_improvements if item.accepted_improvements is not None else '-'}",
            f"Summary: {item.artifacts.summary_txt or '-'}",
            f"Final source: {item.artifacts.final_optimized_source_dir or '-'}",
            f"Final diff: {item.artifacts.final_optimized_source_diff or '-'}",
            f"Read errors: {'; '.join(item.read_errors) if item.read_errors else '-'}",
        ]
    )


def _compute_duration(started: str | None, finished: str | None) -> str:
    if not started or not finished:
        return "-"
    try:
        start = datetime.fromisoformat(started)
        end = datetime.fromisoformat(finished)
        delta = end - start
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "-"
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    except (ValueError, OverflowError):
        return "-"


def _display_kind(kind: str) -> str:
    return "baseline" if kind == "run" else kind


class ResultsView(Widget):
    """Embedded read-only results browser using DataTable.

    Not a Screen -- does not yield Header/Footer and never calls app.pop_screen.
    """

    def __init__(self) -> None:
        super().__init__(id="view-results")
        self._all_items: list[ResultItem] = []
        self._filtered_items: list[ResultItem] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="results-view"):
            yield Static("Browse Results", classes="title")
            yield Static(
                "Read-only navigation for saved run and experiment artifacts.",
                classes="subtitle",
            )
            with Horizontal(id="filter-row"):
                yield Input(placeholder="Filter by name...", id="name-filter")
                yield Select(
                    [("all", "all"), ("baseline", "run"), ("experiment", "experiment")],
                    prompt="Kind",
                    value="all",
                    id="kind-filter",
                    allow_blank=False,
                )
            yield DataTable(id="results-table", cursor_type="row")
            yield Static("No item selected.", id="result-summary-text", classes="panel")
            yield Static("Status: idle", id="results-status", classes="panel")
            with Horizontal(classes="actions"):
                yield Button("Refresh", id="refresh")
                yield Button("Open Dir", id="open-directory", variant="primary")
                yield Button("Summary", id="open-summary")
                yield Button("Final Source", id="open-final-source")
                yield Button("Final Diff", id="open-final-diff")

    def on_mount(self) -> None:
        self._all_items = list_result_items()
        table = self.query_one("#results-table", DataTable)
        table.add_column("id")
        table.add_column("kind")
        table.add_column("status")
        table.add_column("when")
        table.add_column("duration")
        self._rebuild_table()

    # ------------------------------------------------------------------
    # Public helpers for shell bindings (called by MainScreen)
    # ------------------------------------------------------------------

    def focus_search(self) -> None:
        """Focus the name filter Input."""
        self.query_one("#name-filter", Input).focus()

    def clear_filter_or_blur(self) -> None:
        """Clear filters if active, otherwise blur the search input."""
        name_input = self.query_one("#name-filter", Input)
        kind_select = self.query_one("#kind-filter", Select)
        if name_input.value or kind_select.value != "all":
            name_input.clear()
            kind_select.value = "all"
            self._rebuild_table()
        else:
            name_input.screen.set_focus(None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_table(self) -> None:
        table = self.query_one("#results-table", DataTable)
        name_text = self.query_one("#name-filter", Input).value.strip()
        kind_val = self.query_one("#kind-filter", Select).value

        filtered: list[ResultItem] = []
        for item in self._all_items:
            if name_text and name_text.lower() not in item.name.lower():
                continue
            if kind_val not in (None, "all") and item.kind != kind_val:
                continue
            filtered.append(item)

        self._filtered_items = filtered
        table.clear()

        for i, item in enumerate(filtered):
            when = item.started_at or item.finished_at or "-"
            duration = _compute_duration(item.started_at, item.finished_at)
            table.add_row(
                item.name,
                _display_kind(item.kind),
                item.status or "unknown",
                when,
                duration,
                key=str(i),
            )

        if filtered:
            table.move_cursor(row=0)
        self._update_summary()

    def _selected_item(self) -> ResultItem | None:
        table = self.query_one("#results-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is None or cursor_row < 0 or cursor_row >= len(self._filtered_items):
            return None
        return self._filtered_items[cursor_row]

    def _update_summary(self) -> None:
        self.query_one("#result-summary-text", Static).update(_format_item(self._selected_item()))

    def _set_status(self, message: str) -> None:
        self.query_one("#results-status", Static).update(f"Status: {message}")

    def _refresh(self) -> None:
        self._all_items = list_result_items()
        self._rebuild_table()
        self._set_status("refreshed")

    def _open_artifact(self, artifact: str) -> None:
        item = self._selected_item()
        if item is None:
            self._set_status("no result selected")
            return
        path = {
            "directory": item.artifacts.directory,
            "summary": item.artifacts.summary_txt,
            "final-source": item.artifacts.final_optimized_source_dir,
            "final-diff": item.artifacts.final_optimized_source_diff,
        }.get(artifact)
        if path is None:
            self._set_status(f"artifact missing: {artifact}")
            return
        try:
            open_path(path)
        except OpenArtifactError as exc:
            self._set_status(str(exc))
            return
        self._set_status(f"opened {path}")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "name-filter":
            self._rebuild_table()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "kind-filter":
            self._rebuild_table()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_summary()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._update_summary()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "refresh":
            self._refresh()
            return
        if button_id == "open-directory":
            self._open_artifact("directory")
            return
        if button_id == "open-summary":
            self._open_artifact("summary")
            return
        if button_id == "open-final-source":
            self._open_artifact("final-source")
            return
        if button_id == "open-final-diff":
            self._open_artifact("final-diff")
