"""Reusable storage layer for experiment run artifacts.

This module only writes files in the documented run storage format. It is not
responsible for running commands, parsing benchmark output, comparing runs, or
calling LLMs.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


class RunStorage:
    """Create run directories and write persistent run artifacts."""

    def __init__(self, results_root: Path | str = "results") -> None:
        """Initialize storage rooted at the given results directory."""
        self.results_root = Path(results_root)

    def build_run_id(self, scenario: str, started_at: datetime | None = None) -> str:
        """Build a timestamped run id using the documented naming format."""
        timestamp = (started_at or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
        safe_scenario = self._sanitize_name(scenario)
        return f"{timestamp}_{safe_scenario}"

    def create_run_directory(
        self, scenario: str, run_id: str | None = None
    ) -> Path:
        """Create and return results/runs/<run_id>/ with a logs directory."""
        resolved_run_id = run_id or self.build_run_id(scenario)
        run_dir = self.results_root / "runs" / resolved_run_id
        logs_dir = run_dir / "logs"

        run_dir.mkdir(parents=True, exist_ok=False)
        logs_dir.mkdir()

        return run_dir

    def create_explicit_run_directory(self, run_dir: Path) -> Path:
        """Create a run directory at an explicit path without index registration.

        Unlike ``create_run_directory``, this does **not** generate a timestamped
        run id and does **not** append to the global index. It is designed for
        closed-loop experiment managed paths where the caller owns the naming.
        """
        run_dir = Path(run_dir)
        logs_dir = run_dir / "logs"

        run_dir.mkdir(parents=True, exist_ok=False)
        logs_dir.mkdir()

        return run_dir

    def save_metadata(self, run_dir: Path | str, metadata: dict[str, Any]) -> Path:
        """Write metadata.json and return its path."""
        return self._write_json(run_dir, "metadata.json", metadata)

    def save_status(self, run_dir: Path | str, status: dict[str, Any]) -> Path:
        """Write status.json and return its path."""
        return self._write_json(run_dir, "status.json", status)

    def save_metrics(self, run_dir: Path | str, metrics: dict[str, Any]) -> Path:
        """Write metrics.json and return its path."""
        return self._write_json(run_dir, "metrics.json", metrics)

    def save_log(
        self,
        run_dir: Path | str,
        step_name: str,
        command: Sequence[str] | str,
        cwd: Path | str,
        exit_code: int | None,
        stdout: str,
        stderr: str,
    ) -> Path:
        """Write logs/<safe_step_name>.log and return its path."""
        safe_step_name = self._sanitize_name(step_name)
        log_path = Path(run_dir) / "logs" / f"{safe_step_name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        log_text = "\n".join(
            [
                "STEP",
                step_name,
                "",
                "COMMAND",
                self._format_command(command),
                "",
                "CWD",
                str(cwd),
                "",
                "EXIT_CODE",
                "" if exit_code is None else str(exit_code),
                "",
                "STDOUT",
                stdout,
                "",
                "STDERR",
                stderr,
                "",
            ]
        )
        log_path.write_text(log_text, encoding="utf-8")
        return log_path

    def save_summary(self, run_dir: Path | str, summary_text: str) -> Path:
        """Write summary.txt and return its path."""
        summary_path = Path(run_dir) / "summary.txt"
        summary_path.write_text(summary_text, encoding="utf-8")
        return summary_path

    def append_index_record(self, record: dict[str, Any]) -> Path:
        """Append one compact JSON Lines record to results/index.jsonl."""
        index_path = self.results_root / "index.jsonl"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("a", encoding="utf-8") as index_file:
            index_file.write(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
        return index_path

    @staticmethod
    def _sanitize_name(value: str) -> str:
        """Return a lowercase filesystem-safe name fragment."""
        lowered = value.lower()
        separated = re.sub(r"[\s/\\]+", "_", lowered)
        safe = re.sub(r"[^a-z0-9_-]+", "_", separated)
        compacted = re.sub(r"_+", "_", safe).strip("_-")
        return compacted or "run"

    @staticmethod
    def _format_command(command: Sequence[str] | str) -> str:
        """Return a readable command string for log files."""
        if isinstance(command, str):
            return command
        return " ".join(str(part) for part in command)

    @staticmethod
    def _write_json(
        run_dir: Path | str, filename: str, payload: dict[str, Any]
    ) -> Path:
        """Write a UTF-8 JSON artifact and return its path."""
        path = Path(run_dir) / filename
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
