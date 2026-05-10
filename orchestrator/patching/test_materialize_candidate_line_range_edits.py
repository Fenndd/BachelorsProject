"""Focused tests for materialize_candidate line_range_edits support."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.patching.materialize_candidate import (
    REPO_ROOT,
    _apply_single_line_range_edit,
    main as materialize_main,
)


TARGET_FILE = "cpp/example.cpp"
P3P_TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


def _write_source(source_root: Path, text: str) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    (source_root / "example.cpp").write_text(text, encoding="utf-8")


def _line_candidate(
    run_dir: Path,
    *,
    edits: list[dict[str, Any]],
    target_files: list[str] | None = None,
    expected_effect: str = "runtime",
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "candidate.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "candidate_type": "line_range_edits",
                "summary": "test line range candidate",
                "target_files": target_files or [TARGET_FILE],
                "expected_effect": expected_effect,
                "edits": edits,
            }
        ),
        encoding="utf-8",
    )


def _unified_diff_candidate(run_dir: Path, diff_text: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "candidate.json").write_text(
        json.dumps(
            {
                "summary": "legacy unified diff candidate",
                "target_files": [TARGET_FILE],
                "expected_effect": "runtime",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "candidate.diff").write_text(diff_text, encoding="utf-8")


def _materialize(tmp_path: Path, run_dir: Path, source_root: Path) -> int:
    return materialize_main(
        [
            "--candidate-run",
            str(run_dir),
            "--workspace-root",
            str(tmp_path / "workspaces"),
            "--source-root",
            str(source_root),
            "--overwrite",
            "--allowed-file",
            TARGET_FILE,
        ]
    )


def _read_materialization(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "materialization.json").read_text(encoding="utf-8"))


def _workspace_file(materialization: dict[str, Any]) -> Path:
    return Path(materialization["workspace_path"]) / TARGET_FILE


def _workspace_target_file(materialization: dict[str, Any], target_file: str) -> Path:
    return Path(materialization["workspace_path"]) / target_file


class MaterializeCandidateLineRangeEditsTests(unittest.TestCase):
    def test_exact_line_replacement_success_without_candidate_diff(self) -> None:
        repo_text_before = (REPO_ROOT / P3P_TARGET_FILE).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_exact"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "file": TARGET_FILE,
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int value = 1;",
                        "replace": "int value = 2;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "success")
            self.assertEqual(materialization["candidate_type"], "line_range_edits")
            self.assertEqual(materialization["patch_apply_strategy"], "line_range_edits")
            self.assertEqual(materialization["source_root"], str(source_root))
            self.assertEqual(materialization["base_source_root"], str(source_root.resolve()))
            self.assertEqual(materialization["source_root_mode"], "legacy_source_root")
            self.assertEqual(materialization["line_range_exact_matches"], 1)
            self.assertEqual(materialization["generated_diff_base"], "base_source_root")
            self.assertEqual(_workspace_file(materialization).read_text(encoding="utf-8"), "int value = 2;\n")
            self.assertEqual((source_root / "example.cpp").read_text(encoding="utf-8"), "int value = 1;\n")
            self.assertEqual((REPO_ROOT / P3P_TARGET_FILE).read_text(encoding="utf-8"), repo_text_before)
            self.assertTrue((run_dir / "candidate.generated.diff").exists())
            self.assertFalse((run_dir / "candidate.diff").exists())

    def test_explicit_base_source_root_line_range_uses_current_best_content(self) -> None:
        current_best_text = "int current_best_value = 42;\n"
        candidate_text = "int current_best_value = 43;\n"
        repo_text_before = (REPO_ROOT / P3P_TARGET_FILE).read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = tmp_path / "current_best_source"
            base_file = base_source_root / P3P_TARGET_FILE
            base_file.parent.mkdir(parents=True)
            base_file.write_text(current_best_text, encoding="utf-8")
            run_dir = tmp_path / "candidate_current_best"
            _line_candidate(
                run_dir,
                target_files=[P3P_TARGET_FILE],
                edits=[
                    {
                        "file": P3P_TARGET_FILE,
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int current_best_value = 42;",
                        "replace": "int current_best_value = 43;",
                    }
                ],
            )

            exit_code = materialize_main(
                [
                    "--candidate-run",
                    str(run_dir),
                    "--workspace-root",
                    str(tmp_path / "workspaces"),
                    "--base-source-root",
                    str(base_source_root),
                    "--overwrite",
                    "--allowed-file",
                    P3P_TARGET_FILE,
                ]
            )

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            workspace_file = _workspace_target_file(materialization, P3P_TARGET_FILE)
            self.assertEqual(workspace_file.read_text(encoding="utf-8"), candidate_text)
            self.assertEqual(base_file.read_text(encoding="utf-8"), current_best_text)
            self.assertEqual((REPO_ROOT / P3P_TARGET_FILE).read_text(encoding="utf-8"), repo_text_before)
            self.assertEqual(materialization["overall_status"], "success")
            self.assertEqual(materialization["base_source_root"], str(base_source_root.resolve()))
            self.assertEqual(materialization["source_root"], str(base_source_root))
            self.assertEqual(materialization["source_root_mode"], "explicit_base_source_root")
            self.assertEqual(materialization["generated_diff_base"], "base_source_root")
            self.assertIn(P3P_TARGET_FILE, materialization["changed_files"])

            generated_diff = (run_dir / "candidate.generated.diff").read_text(encoding="utf-8")
            self.assertIn("--- a/cpp/external/lambdatwist/p3p.cc", generated_diff)
            self.assertIn("+++ b/cpp/external/lambdatwist/p3p.cc", generated_diff)
            self.assertIn("-int current_best_value = 42;", generated_diff)
            self.assertIn("+int current_best_value = 43;", generated_diff)

            log_text = (run_dir / "apply_candidate.log").read_text(encoding="utf-8")
            self.assertIn("Base source root:", log_text)
            self.assertIn("Source root mode: explicit_base_source_root", log_text)
            self.assertIn("Generated diff base: base_source_root", log_text)

    def test_explicit_base_source_root_missing_target_file_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = tmp_path / "current_best_source"
            (base_source_root / "cpp").mkdir(parents=True)
            run_dir = tmp_path / "candidate_missing_target"
            _line_candidate(
                run_dir,
                target_files=[P3P_TARGET_FILE],
                edits=[
                    {
                        "file": P3P_TARGET_FILE,
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int current_best_value = 42;",
                        "replace": "int current_best_value = 43;",
                    }
                ],
            )

            exit_code = materialize_main(
                [
                    "--candidate-run",
                    str(run_dir),
                    "--workspace-root",
                    str(tmp_path / "workspaces"),
                    "--base-source-root",
                    str(base_source_root),
                    "--overwrite",
                    "--allowed-file",
                    P3P_TARGET_FILE,
                ]
            )

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["failed_step"], "line_range_apply")
            self.assertIn("target file not found", materialization["error_message"])
            self.assertEqual(materialization["base_source_root"], str(base_source_root.resolve()))

    def test_explicit_source_root_and_base_source_root_combination_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int value = 1;\n")
            base_source_root = tmp_path / "current_best_source"
            (base_source_root / TARGET_FILE).parent.mkdir(parents=True)
            (base_source_root / TARGET_FILE).write_text("int value = 1;\n", encoding="utf-8")
            run_dir = tmp_path / "candidate_ambiguous_roots"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "file": TARGET_FILE,
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int value = 1;",
                        "replace": "int value = 2;",
                    }
                ],
            )

            exit_code = materialize_main(
                [
                    "--candidate-run",
                    str(run_dir),
                    "--workspace-root",
                    str(tmp_path / "workspaces"),
                    "--source-root",
                    str(source_root),
                    "--base-source-root",
                    str(base_source_root),
                    "--overwrite",
                    "--allowed-file",
                    TARGET_FILE,
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse((run_dir / "materialization.json").exists())

    def test_line_range_mismatch_without_fallback_fails_clearly(self) -> None:
        edit = {
            "index": 0,
            "file": TARGET_FILE,
            "start_line": 1,
            "end_line": 1,
            "original": "int unique = 7;",
            "replace": "int unique = 8;",
        }

        with self.assertRaises(ValueError) as ctx:
            _apply_single_line_range_edit(
                "int other = 1;\nint unique = 7;\n",
                edit,
                allow_exact_search_fallback=False,
            )

        self.assertIn("fallback is disabled", str(ctx.exception))

    def test_multiple_edits_in_same_file_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int a = 1;\nint b = 2;\nint c = 3;\n")
            run_dir = tmp_path / "candidate_multiple"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "file": TARGET_FILE,
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int a = 1;",
                        "replace": "int a = 10;",
                    },
                    {
                        "file": TARGET_FILE,
                        "start_line": 3,
                        "end_line": 3,
                        "original": "int c = 3;",
                        "replace": "int c = 30;",
                    },
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            workspace_text = _workspace_file(materialization).read_text(encoding="utf-8")
            self.assertIn("int a = 10;", workspace_text)
            self.assertIn("int c = 30;", workspace_text)
            self.assertEqual(materialization["line_range_exact_matches"], 2)

    def test_line_range_mismatch_fallback_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int a = 1;\nint unique = 7;\n")
            run_dir = tmp_path / "candidate_fallback"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "file": TARGET_FILE,
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int unique = 7;",
                        "replace": "int unique = 8;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["line_range_fallback_matches"], 1)
            self.assertTrue(materialization["line_range_fallback_used"])

    def test_fallback_ambiguous_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int same = 1;\nint x = 0;\nint same = 1;\n")
            run_dir = tmp_path / "candidate_ambiguous"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "file": TARGET_FILE,
                        "start_line": 2,
                        "end_line": 2,
                        "original": "int same = 1;",
                        "replace": "int same = 2;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, source_root)

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["failed_step"], "line_range_apply")
            self.assertEqual(materialization["patch_apply_strategy"], "line_range_edits_failed")

    def test_original_not_found_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_not_found"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "file": TARGET_FILE,
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int missing = 9;",
                        "replace": "int missing = 10;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, source_root)

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["failed_step"], "line_range_apply")
            self.assertIn("not found", materialization["error_message"])

    def test_edit_file_outside_target_files_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_outside_target"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "file": "cpp/other.cpp",
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int value = 1;",
                        "replace": "int value = 2;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, source_root)

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["failed_step"], "validate_patch_scope")
            self.assertIn("not listed", materialization["error_message"])

    def test_line_range_noop_skipped_without_candidate_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_noop"
            _line_candidate(run_dir, edits=[], expected_effect="none")

            exit_code = _materialize(tmp_path, run_dir, source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "skipped")
            self.assertEqual(materialization["candidate_type"], "line_range_edits")
            self.assertEqual(materialization["patch_apply_strategy"], "not_run")
            self.assertFalse((run_dir / "candidate.diff").exists())

    def test_legacy_unified_diff_still_works(self) -> None:
        diff_text = "\n".join(
            [
                "--- a/cpp/example.cpp",
                "+++ b/cpp/example.cpp",
                "@@ -1 +1 @@",
                "-int value = 1;",
                "+int value = 2;",
                "",
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            _write_source(source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_unified"
            _unified_diff_candidate(run_dir, diff_text)

            exit_code = _materialize(tmp_path, run_dir, source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["candidate_type"], "unified_diff")
            self.assertEqual(materialization["patch_apply_strategy"], "git_apply")
            self.assertIn(TARGET_FILE, materialization["changed_files"])


if __name__ == "__main__":
    unittest.main()