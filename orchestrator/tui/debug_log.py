"""Best-effort debug logging for TUI control flow."""

from __future__ import annotations

from datetime import datetime

from orchestrator.control.project_paths import get_project_paths


def write_tui_debug(message: str) -> None:
    """Append a timestamped TUI debug message without raising to the caller."""

    try:
        workspace = get_project_paths().workspace
        workspace.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with (workspace / "tui_debug.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")
    except Exception:
        return
