"""Read-only results browser screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ListItem, ListView, Static

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
            f"Kind: {item.kind}",
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


class ResultsScreen(Screen[None]):
    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self.items: list[ResultItem] = list_result_items()

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="main"):
            yield Static("Browse Results", classes="title")
            yield Static(
                "Read-only navigation for saved run and experiment artifacts.",
                classes="subtitle",
            )
            yield ListView(
                *[
                    ListItem(Static(f"{item.kind}: {item.name} [{item.status or 'unknown'}]"))
                    for item in self.items
                ],
                id="results-list",
                classes="panel",
            )
            with VerticalScroll(id="result-summary-panel", classes="panel"):
                yield Static(_format_item(self._selected_item()), id="result-summary-text")
            yield Static("Status: idle", id="results-status", classes="panel")
            with Horizontal(classes="actions"):
                yield Button("Refresh", id="refresh")
                yield Button("Open Dir", id="open-directory", variant="primary")
                yield Button("Summary", id="open-summary")
                yield Button("Final Source", id="open-final-source")
                yield Button("Final Diff", id="open-final-diff")
                yield Button("Back", id="back")
        yield Footer()

    def on_mount(self) -> None:
        if self.items:
            self.query_one("#results-list", ListView).index = 0

    def _selected_item(self) -> ResultItem | None:
        if not self.items:
            return None
        try:
            index = self.query_one("#results-list", ListView).index
        except Exception:
            index = 0
        if index is None or index < 0 or index >= len(self.items):
            index = 0
        return self.items[index]

    def _set_status(self, message: str) -> None:
        self.query_one("#results-status", Static).update(f"Status: {message}")

    def _refresh(self) -> None:
        self.items = list_result_items()
        list_view = self.query_one("#results-list", ListView)
        list_view.clear()
        for item in self.items:
            list_view.append(
                ListItem(Static(f"{item.kind}: {item.name} [{item.status or 'unknown'}]"))
            )
        if self.items:
            list_view.index = 0
        self.query_one("#result-summary-text", Static).update(_format_item(self._selected_item()))
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

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        self.query_one("#result-summary-text", Static).update(_format_item(self._selected_item()))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.app.pop_screen()
            return
        if event.button.id == "refresh":
            self._refresh()
            return
        if event.button.id == "open-directory":
            self._open_artifact("directory")
            return
        if event.button.id == "open-summary":
            self._open_artifact("summary")
            return
        if event.button.id == "open-final-source":
            self._open_artifact("final-source")
            return
        if event.button.id == "open-final-diff":
            self._open_artifact("final-diff")
