"""Read-only results browser view with DataTable, filtering, and artifact open actions."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Select, Static

from orchestrator.control import ResultItem, list_result_items, open_path
from orchestrator.control.open_artifact import OpenArtifactError


def _format_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}"


def _read_json_object(path: Path | None, errors: list[str]) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: {exc}")
        return None
    return payload if isinstance(payload, dict) else None


def _summary_excerpt(text: str | None, limit: int = 1200) -> str:
    if not text:
        return "-"
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "..."


def _artifact_lines(item: ResultItem, labels: list[tuple[str, Path | None]]) -> list[str]:
    return [f"{label}: {path or '-'}" for label, path in labels]


def _format_baseline_item(item: ResultItem) -> str:
    lines = [
        "Kind: baseline",
        f"Name: {item.name}",
        f"Path: {item.path}",
        f"Status: {item.status or 'unknown'}",
        f"Started: {item.started_at or '-'}",
        f"Finished: {item.finished_at or '-'}",
    ]
    lines.extend(
        _artifact_lines(
            item,
            [
                ("Summary path", item.artifacts.summary_txt),
                ("Metadata path", item.artifacts.metadata_json),
                ("Status path", item.artifacts.status_json),
                ("Metrics path", item.artifacts.metrics_json),
            ],
        )
    )
    lines.extend(
        [
            "Summary text:",
            _summary_excerpt(item.summary_text),
            f"Read errors: {'; '.join(item.read_errors) if item.read_errors else '-'}",
        ]
    )
    return "\n".join(lines)


def _format_candidate_item(item: ResultItem) -> str:
    errors: list[str] = []
    candidate_path = item.path / "candidate.json"
    candidate = _read_json_object(candidate_path, errors)
    status = _read_json_object(item.artifacts.status_json, errors)
    metrics = _read_json_object(item.artifacts.metrics_json, errors)
    useful: list[str] = []
    for label, payload, keys in (
        ("Candidate", candidate, ("summary", "expected_effect", "risk_level", "target_file")),
        ("Status", status, ("scenario", "overall_status", "message")),
        ("Metrics", metrics, ("solver", "runtime_ns_per_problem_median", "gt_found_percent")),
    ):
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                useful.append(f"{label} {key}: {value}")
    lines = [
        "Kind: candidate",
        f"Name: {item.name}",
        f"Path: {item.path}",
        f"Status: {item.status or 'unknown'}",
        f"Started: {item.started_at or '-'}",
        f"Finished: {item.finished_at or '-'}",
        f"Candidate artifact path: {candidate_path if candidate_path.is_file() else '-'}",
    ]
    lines.extend(
        _artifact_lines(
            item,
            [
                ("Summary path", item.artifacts.summary_txt),
                ("Status path", item.artifacts.status_json),
                ("Metadata path", item.artifacts.metadata_json),
                ("Metrics path", item.artifacts.metrics_json),
            ],
        )
    )
    if useful:
        lines.extend(["Candidate fields:", *useful])
    lines.extend(
        [
            "Summary text:",
            _summary_excerpt(item.summary_text),
            f"Read errors: {'; '.join([*item.read_errors, *errors]) if item.read_errors or errors else '-'}",
        ]
    )
    return "\n".join(lines)


def _format_experiment_item(item: ResultItem) -> str:
    lines = [
        "Kind: experiment",
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
        f"Report HTML: {item.artifacts.report_html or '-'}",
        f"Report PDF: {item.artifacts.report_pdf or '-'}",
        "Summary text:",
        _summary_excerpt(item.summary_text),
        f"Read errors: {'; '.join(item.read_errors) if item.read_errors else '-'}",
    ]
    return "\n".join(lines)


def _format_item(item: ResultItem | None) -> str:
    if item is None:
        return "No saved results found."
    if item.kind == "candidate":
        return _format_candidate_item(item)
    if item.kind == "experiment":
        return _format_experiment_item(item)
    return _format_baseline_item(item)


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
        self._selected_key: tuple[Path, str] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="results-view"):
            with VerticalScroll(id="results-scroll"):
                yield Static("Browse Results", classes="title")
                yield Static(
                    "Read-only navigation for saved run and experiment artifacts.",
                    classes="subtitle",
                )
                with Vertical(id="results-filter-panel", classes="panel"):
                    with Horizontal(id="filter-row"):
                        yield Input(placeholder="Filter by name...", id="name-filter")
                        yield Select(
                            [("all", "all"), ("baseline", "baseline"), ("candidate", "candidate"), ("experiment", "experiment")],
                            prompt="Kind",
                            value="all",
                            id="kind-filter",
                            allow_blank=False,
                        )
                yield DataTable(id="results-table", cursor_type="row")
                with VerticalScroll(id="result-summary-panel", classes="panel"):
                    yield Static("No item selected.", id="result-summary-text")
                yield Static("Status: idle", id="results-status", classes="panel")
                with Horizontal(classes="actions", id="results-actions"):
                    yield Button("Open Dir", id="open-directory", variant="primary")
                    yield Button("Summary", id="open-summary")

    def on_mount(self) -> None:
        self._all_items = list_result_items()
        table = self.query_one("#results-table", DataTable)
        table.add_column("id")
        table.add_column("kind")
        table.add_column("status")
        table.add_column("when")
        table.add_column("duration")
        self._rebuild_table()

    def refresh_summaries(self, status_message: str | None = None) -> None:
        selected = self._selected_item()
        selected_key = (selected.path, selected.name) if selected is not None else self._selected_key
        self._all_items = list_result_items()
        self._rebuild_table(selected_key=selected_key)
        if status_message is not None:
            self._set_status(status_message)

    def refresh_view(self) -> None:
        self.refresh_summaries("refreshed")

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

    def _rebuild_table(self, selected_key: tuple[Path, str] | None = None) -> None:
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
            selected_index = 0
            if selected_key is not None:
                for index, item in enumerate(filtered):
                    if (item.path, item.name) == selected_key:
                        selected_index = index
                        break
            table.move_cursor(row=selected_index)
        self._update_summary()

    def _selected_item(self) -> ResultItem | None:
        table = self.query_one("#results-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is None or cursor_row < 0 or cursor_row >= len(self._filtered_items):
            return None
        return self._filtered_items[cursor_row]

    def _update_summary(self) -> None:
        selected = self._selected_item()
        if selected is not None:
            self._selected_key = (selected.path, selected.name)
        self.query_one("#result-summary-text", Static).update(_format_item(selected))

    def _set_status(self, message: str) -> None:
        self.query_one("#results-status", Static).update(f"Status: {message}")

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
        if button_id == "open-directory":
            self._open_artifact("directory")
            return
        if button_id == "open-summary":
            self._open_artifact("summary")
            return
