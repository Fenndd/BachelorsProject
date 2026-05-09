"""Tests for generate_candidate logical source path vs physical source root."""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from orchestrator.llm import generate_candidate
from orchestrator.llm.generate_candidate import (
    CandidateGenerationFailure,
    REPO_ROOT,
    _read_source,
    _resolve_logical_target_file,
)
from orchestrator.storage import RunStorage


TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"
MOCK_CONFIG = REPO_ROOT / "configs" / "llm_mock_line_range_p3p.json"
DISTINCTIVE_SOURCE = "int distinctive_current_best_source = 42;\n"


class GenerateCandidateSourceRootTests(unittest.TestCase):
    def test_repo_relative_source_without_source_root_reads_repo_root(self) -> None:
        logical_target = _resolve_logical_target_file(
            TARGET_FILE,
            source_root_provided=False,
        )
        physical_source = REPO_ROOT / logical_target

        self.assertEqual(logical_target, TARGET_FILE)
        self.assertIn("namespace lambdatwist", _read_source(physical_source, 120000))

    def test_absolute_source_under_repo_without_source_root_stays_supported(self) -> None:
        logical_target = _resolve_logical_target_file(
            str((REPO_ROOT / TARGET_FILE).resolve()),
            source_root_provided=False,
        )

        self.assertEqual(logical_target, TARGET_FILE)

    def test_absolute_source_with_source_root_fails_clearly(self) -> None:
        with self.assertRaises(CandidateGenerationFailure) as ctx:
            _resolve_logical_target_file(
                str((REPO_ROOT / TARGET_FILE).resolve()),
                source_root_provided=True,
            )

        self.assertEqual(ctx.exception.failed_step, "parse_args")
        self.assertIn("--source must be a repo-relative logical path", ctx.exception.error_message)

    def test_custom_source_root_reads_physical_file_but_prompt_uses_logical_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            source_root = tmp_root / "current_best_source"
            physical_source = source_root / TARGET_FILE
            physical_source.parent.mkdir(parents=True)
            physical_source.write_text(DISTINCTIVE_SOURCE, encoding="utf-8")

            run_dir = self._run_generate_candidate(tmp_root, source_root)

            llm_request = json.loads((run_dir / "llm_request.json").read_text(encoding="utf-8"))
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
            user_prompt = llm_request["user_prompt"]

            self.assertEqual(llm_request["target_file"], TARGET_FILE)
            self.assertEqual(llm_request["allowed_files"], [TARGET_FILE])
            self.assertEqual(metadata["target_file"], TARGET_FILE)
            self.assertEqual(llm_request["source_root"], str(source_root.resolve()))
            self.assertEqual(metadata["source_root"], str(source_root.resolve()))
            self.assertEqual(llm_request["physical_source_path"], str(physical_source.resolve()))
            self.assertEqual(metadata["physical_source_path"], str(physical_source.resolve()))
            self.assertIn(DISTINCTIVE_SOURCE.strip(), user_prompt)
            self.assertIn(f"Target file path:\n{TARGET_FILE}", user_prompt)
            self.assertNotIn(f"Target file path:\n{source_root.resolve()}", user_prompt)
            self.assertNotIn(str(source_root.resolve()).replace("\\", "/"), user_prompt)

    def test_missing_file_under_custom_source_root_fails_at_read_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            source_root = tmp_root / "current_best_source"
            source_root.mkdir()

            run_dir = self._run_generate_candidate(
                tmp_root,
                source_root,
                expected_exit_code=1,
            )

            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))

            self.assertEqual(status["overall_status"], "failed")
            self.assertEqual(status["failed_step"], "read_source")
            self.assertIn("Target source file not found", status["error_message"])
            self.assertEqual(metadata["target_file"], TARGET_FILE)
            self.assertEqual(metadata["source_root"], str(source_root.resolve()))

    def _run_generate_candidate(
        self,
        tmp_root: Path,
        source_root: Path,
        expected_exit_code: int = 0,
    ) -> Path:
        results_root = tmp_root / "results"

        def storage_factory(_results_root: Path) -> RunStorage:
            return RunStorage(results_root)

        argv = [
            "--config",
            str(MOCK_CONFIG),
            "--source",
            TARGET_FILE,
            "--source-root",
            str(source_root),
            "--candidate-type",
            "line_range_edits",
            "--source-presentation",
            "line_numbered",
        ]
        stdout = StringIO()
        with patch.object(generate_candidate, "RunStorage", storage_factory), redirect_stdout(stdout):
            exit_code = generate_candidate.main(argv)

        self.assertEqual(exit_code, expected_exit_code, stdout.getvalue())
        run_dirs = sorted((results_root / "runs").iterdir())
        self.assertEqual(len(run_dirs), 1)
        return run_dirs[0]


if __name__ == "__main__":
    unittest.main()