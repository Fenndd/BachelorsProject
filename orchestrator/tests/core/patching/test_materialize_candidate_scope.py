"""Focused tests for materialize_candidate scope enforcement artifacts."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.core.patching.materialize_candidate import main as materialize_main

from orchestrator.tests.conftest import TARGET_FILE


def _write_candidate(
    run_dir: Path,
    *,
    edits: list[dict[str, Any]] | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "summary": "test candidate",
        "rationale": "test rationale",
        "correctness_notes": "no issues",
        "edits": [] if edits is None else edits,
    }
    (run_dir / "candidate.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _noop_materialize(
    run_dir: Path,
    target_file: str,
    allowed_files: list[str] | None = None,
) -> int:
    source_dir = run_dir.parent / "source"
    source_dir.mkdir(exist_ok=True)
    argv = [
        "--candidate-run",
        str(run_dir),
        "--candidate-workspace-dir",
        str(run_dir.parent / "workspaces" / run_dir.name),
        "--base-source-root",
        str(source_dir),
        "--target-file",
        target_file,
    ]
    for allowed_file in allowed_files or []:
        argv.extend(["--allowed-file", allowed_file])
    return materialize_main(argv)


def _read_materialization(run_dir: Path) -> dict[str, object]:
    return json.loads((run_dir / "materialization.json").read_text(encoding="utf-8"))


class MaterializeCandidateScopeTests(unittest.TestCase):
    def test_external_allowed_file_passes_and_is_recorded_on_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "candidate_allowed"
            _write_candidate(run_dir, edits=[])

            exit_code = _noop_materialize(
                run_dir,
                target_file=TARGET_FILE,
                allowed_files=[TARGET_FILE],
            )

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "skipped")
            self.assertEqual(materialization["scope_enforcement"], "external_allowed_files")
            self.assertEqual(materialization["allowed_files"], [TARGET_FILE])
            self.assertEqual(materialization["target_files"], [TARGET_FILE])

    def test_target_file_outside_allowed_files_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "candidate_target_outside"
            _write_candidate(run_dir, edits=[])

            exit_code = _noop_materialize(
                run_dir,
                target_file="cpp/external/poselib/PoseLib/solvers/other.cc",
                allowed_files=[TARGET_FILE],
            )

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "failed")
            self.assertEqual(materialization["failed_step"], "validate_candidate_scope")
            self.assertEqual(materialization["scope_enforcement"], "external_allowed_files")
            self.assertIn("outside allowed optimization scope", materialization["error_message"])

    def test_target_file_required_fails_without_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "candidate_no_target"
            _write_candidate(run_dir, edits=[])
            source_dir = run_dir.parent / "source"
            source_dir.mkdir(exist_ok=True)

            with self.assertRaises(SystemExit):
                materialize_main(
                    [
                        "--candidate-run",
                        str(run_dir),
                        "--candidate-workspace-dir",
                        str(run_dir.parent / "workspaces" / run_dir.name),
                        "--base-source-root",
                        str(source_dir),
                        "--allowed-file",
                        TARGET_FILE,
                    ]
                )

    def test_external_allowed_file_missing_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "candidate_no_allowed"
            _write_candidate(run_dir, edits=[])

            exit_code = _noop_materialize(run_dir, target_file=TARGET_FILE, allowed_files=[])

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "failed")
            self.assertEqual(materialization["failed_step"], "validate_candidate_scope")
            self.assertIn("--allowed-file is required", materialization["error_message"])


if __name__ == "__main__":
    unittest.main()
