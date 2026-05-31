"""Focused tests for materialize_candidate line_range_edits support."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.core.patching.materialize_candidate import (
    _apply_single_line_range_edit,
    main as materialize_main,
)
from orchestrator.paths import paths

REPO_ROOT = paths.repo_root


TARGET_FILE = "cpp/example.cpp"
P3P_TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


def _write_source(base_source_root: Path, text: str) -> None:
    cpp_dir = base_source_root / "cpp"
    cpp_dir.mkdir(parents=True, exist_ok=True)
    (cpp_dir / "example.cpp").write_text(text, encoding="utf-8")


def _write_build_artifacts(base_source_root: Path) -> None:
    source_root = base_source_root / "cpp"
    for relative in [
        "build/temp.obj",
        "build-codex/cache.txt",
        "cmake-build-debug/cache.txt",
        "CMakeFiles/generated.txt",
        "Testing/test.xml",
    ]:
        path = source_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")
    for relative in [
        "CMakeCache.txt",
        "build.ninja",
        ".ninja_log",
        "tool.exe",
        "object.obj",
        "object.o",
        "symbols.pdb",
        "link.ilk",
        "library.dll",
        "libtemp.lib",
        "libtemp.a",
    ]:
        path = source_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")


def _line_candidate(
    run_dir: Path,
    *,
    edits: list[dict[str, Any]],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "candidate.json").write_text(
        json.dumps(
            {
                "summary": "test line range candidate",
                "rationale": "test rationale",
                "correctness_notes": "no issues",
                "edits": edits,
            }
        ),
        encoding="utf-8",
    )


def _materialize(
    tmp_path: Path,
    run_dir: Path,
    base_source_root: Path,
    *,
    allow_exact_search_fallback: bool = True,
    target_file: str = TARGET_FILE,
) -> int:
    args = [
            "--candidate-run",
            str(run_dir),
            "--candidate-workspace-dir",
            str(tmp_path / "workspaces" / run_dir.name),
            "--base-source-root",
            str(base_source_root),
            "--overwrite",
            "--allowed-file",
            target_file,
            "--target-file",
            target_file,
        ]
    return materialize_main(args)


def _source_dir(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    return source


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
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_exact"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int value = 1;",
                        "replace": "int value = 2;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "success")
            self.assertEqual(materialization["patch_apply_strategy"], "line_range_edits")
            self.assertEqual(materialization["source_root"], str(base_source_root))
            self.assertEqual(materialization["base_source_root"], str(base_source_root.resolve()))
            self.assertEqual(materialization["line_range_exact_matches"], 1)
            self.assertEqual(materialization["line_range_surrounding_whitespace_tolerant_matches"], 0)
            self.assertTrue(materialization["workspace_retained"])
            self.assertTrue(materialization["workspace_exists_after_run"])
            self.assertEqual(materialization["generated_diff_base"], "base_source_root")
            self.assertTrue(materialization["generated_diff_created"])
            self.assertTrue(materialization["generated_diff_path"].endswith("candidate.generated.diff"))
            self.assertEqual(_workspace_file(materialization).read_text(encoding="utf-8"), "int value = 2;\n")
            self.assertEqual((base_source_root / "cpp" / "example.cpp").read_text(encoding="utf-8"), "int value = 1;\n")
            self.assertEqual((REPO_ROOT / P3P_TARGET_FILE).read_text(encoding="utf-8"), repo_text_before)
            self.assertTrue((run_dir / "candidate.generated.diff").exists())
            self.assertEqual(
                materialization["diff_stats"],
                {
                    "files_changed": 1,
                    "lines_added": 1,
                    "lines_removed": 1,
                    "changed_blocks": 1,
                    "edit_count": 1,
                    "fallback_used": False,
                },
            )

    def test_source_copy_excludes_build_cache_and_generated_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;\n")
            _write_build_artifacts(base_source_root)
            run_dir = tmp_path / "candidate_ignore_artifacts"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int value = 1;",
                        "replace": "int value = 2;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            workspace_source = Path(materialization["workspace_path"]) / "cpp"
            self.assertEqual((workspace_source / "example.cpp").read_text(encoding="utf-8"), "int value = 2;\n")
            for relative in [
                "build",
                "build-codex",
                "cmake-build-debug",
                "CMakeFiles",
                "Testing",
                "CMakeCache.txt",
                "build.ninja",
                ".ninja_log",
                "tool.exe",
                "object.obj",
                "object.o",
                "symbols.pdb",
                "link.ilk",
                "library.dll",
                "libtemp.lib",
                "libtemp.a",
            ]:
                self.assertFalse((workspace_source / relative).exists(), relative)

    def test_line_range_trailing_whitespace_tolerant_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;   \n")
            run_dir = tmp_path / "candidate_trailing_whitespace"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int value = 1;",
                        "replace": "int value = 2;",
                    }
                ],
            )

            exit_code = _materialize(
                tmp_path,
                run_dir,
                base_source_root,
                allow_exact_search_fallback=False,
            )

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(_workspace_file(materialization).read_text(encoding="utf-8"), "int value = 2;\n")
            self.assertEqual(materialization["line_range_exact_matches"], 0)
            self.assertEqual(materialization["line_range_trailing_whitespace_tolerant_matches"], 1)
            result = materialization["line_range_edit_results"][0]
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["match_mode"], "line_range_trailing_whitespace_tolerant")

    def test_single_line_surrounding_whitespace_tolerant_success_adapts_indent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            actual_indent = " " * 20
            llm_indent = " " * 24
            _write_source(base_source_root, f"{actual_indent}refine_lambda(x);\n")
            run_dir = tmp_path / "candidate_leading_whitespace"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": f"{llm_indent}refine_lambda(x);",
                        "replace": f"{llm_indent}refine_lambda_fast(x);",
                    }
                ],
            )

            exit_code = _materialize(
                tmp_path,
                run_dir,
                base_source_root,
                allow_exact_search_fallback=False,
            )

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(
                _workspace_file(materialization).read_text(encoding="utf-8"),
                f"{actual_indent}refine_lambda_fast(x);\n",
            )
            self.assertEqual(materialization["line_range_surrounding_whitespace_tolerant_matches"], 1)
            result = materialization["line_range_edit_results"][0]
            self.assertEqual(result["match_mode"], "line_range_surrounding_whitespace_tolerant")
            self.assertTrue(result["line_range_valid"])

    def test_multi_line_surrounding_whitespace_tolerant_success_preserves_relative_indent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "    if (ok) {\n        do_a();\n    }\n")
            run_dir = tmp_path / "candidate_multi_leading_whitespace"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 3,
                        "original": "        if (ok) {\n            do_a();\n        }",
                        "replace": "        if (ok) {\n            do_b();\n            do_c();\n        }",
                    }
                ],
            )

            exit_code = _materialize(
                tmp_path,
                run_dir,
                base_source_root,
                allow_exact_search_fallback=False,
            )

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(
                _workspace_file(materialization).read_text(encoding="utf-8"),
                "    if (ok) {\n        do_b();\n        do_c();\n    }\n",
            )
            self.assertEqual(
                materialization["line_range_edit_results"][0]["match_mode"],
                "line_range_surrounding_whitespace_tolerant",
            )

    def test_line_range_leading_whitespace_mismatch_direct_apply_succeeds(self) -> None:
        edit = {
            "index": 0,
            "file": TARGET_FILE,
            "start_line": 1,
            "end_line": 1,
            "original": "int value = 1;",
            "replace": "int value = 2;",
        }

        text, result = _apply_single_line_range_edit(
            "  int value = 1;\n",
            edit,
            allow_exact_search_fallback=False,
        )

        self.assertEqual(text, "  int value = 2;\n")
        self.assertEqual(result["match_mode"], "line_range_surrounding_whitespace_tolerant")

    def test_line_range_internal_whitespace_mismatch_still_fails(self) -> None:
        edit = {
            "index": 0,
            "file": TARGET_FILE,
            "start_line": 1,
            "end_line": 1,
            "original": "int value = 1;",
            "replace": "int value = 2;",
        }

        with self.assertRaises(ValueError) as ctx:
            _apply_single_line_range_edit(
                "int  value = 1;\n",
                edit,
                allow_exact_search_fallback=False,
            )

        self.assertIn("fallback is disabled", str(ctx.exception))

    def test_line_range_different_line_counts_do_not_match_surrounding_whitespace_tolerant(self) -> None:
        edit = {
            "index": 0,
            "file": TARGET_FILE,
            "start_line": 1,
            "end_line": 1,
            "original": "int value = 1;\nint other = 2;",
            "replace": "int value = 3;",
        }

        with self.assertRaises(ValueError) as ctx:
            _apply_single_line_range_edit(
                "  int value = 1;\n",
                edit,
                allow_exact_search_fallback=False,
            )

        self.assertIn("fallback is disabled", str(ctx.exception))

    def test_explicit_base_source_root_line_range_uses_current_best_content(self) -> None:
        current_best_text = "int current_best_value = 42;\n"
        candidate_text = "int current_best_value = 43;\n"
        repo_text_before = (REPO_ROOT / P3P_TARGET_FILE).read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path) / "current_best_source"
            base_file = base_source_root / P3P_TARGET_FILE
            base_file.parent.mkdir(parents=True)
            base_file.write_text(current_best_text, encoding="utf-8")
            run_dir = tmp_path / "candidate_current_best"
            _line_candidate(
                run_dir,
                edits=[
                    {
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
                    "--candidate-workspace-dir",
                    str(tmp_path / "workspaces" / run_dir.name),
                    "--base-source-root",
                    str(base_source_root),
                    "--overwrite",
                    "--allowed-file",
                    P3P_TARGET_FILE,
                    "--target-file",
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
            self.assertEqual(materialization["generated_diff_base"], "base_source_root")
            self.assertIn(P3P_TARGET_FILE, materialization["changed_files"])

            generated_diff = (run_dir / "candidate.generated.diff").read_text(encoding="utf-8")
            self.assertIn("--- a/cpp/external/lambdatwist/p3p.cc", generated_diff)
            self.assertIn("+++ b/cpp/external/lambdatwist/p3p.cc", generated_diff)
            self.assertIn("-int current_best_value = 42;", generated_diff)
            self.assertIn("+int current_best_value = 43;", generated_diff)

            log_text = (run_dir / "apply_candidate.log").read_text(encoding="utf-8")
            self.assertIn("Base source root:", log_text)
            self.assertIn("Generated diff base: base_source_root", log_text)

    def test_explicit_base_source_root_missing_target_file_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path) / "current_best_source"
            (base_source_root / "cpp").mkdir(parents=True)
            run_dir = tmp_path / "candidate_missing_target"
            _line_candidate(
                run_dir,
                edits=[
                    {
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
                    "--candidate-workspace-dir",
                    str(tmp_path / "workspaces" / run_dir.name),
                    "--base-source-root",
                    str(base_source_root),
                    "--overwrite",
                    "--allowed-file",
                    P3P_TARGET_FILE,
                    "--target-file",
                    P3P_TARGET_FILE,
                ]
            )

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["failed_step"], "line_range_apply")
            self.assertIn("target file not found", materialization["error_message"])
            self.assertEqual(materialization["base_source_root"], str(base_source_root.resolve()))
            self.assertFalse(materialization["workspace_retained"])
            self.assertFalse(materialization["workspace_exists_after_run"])
            self.assertTrue(materialization["workspace_removed_on_failure"])
            self.assertEqual(materialization["workspace_removal_reason"], "materialization_failed")
            failed = materialization["line_range_edit_results"][0]
            self.assertEqual(failed["file"], P3P_TARGET_FILE)
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["failure_reason"], "target_file_missing")
            self.assertIsNone(materialization["generated_diff_path"])
            self.assertFalse(materialization["generated_diff_created"])
            self.assertFalse((run_dir / "candidate.generated.diff").exists())

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
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int a = 1;\nint b = 2;\nint c = 3;\n")
            run_dir = tmp_path / "candidate_multiple"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int a = 1;",
                        "replace": "int a = 10;",
                    },
                    {
                        "start_line": 3,
                        "end_line": 3,
                        "original": "int c = 3;",
                        "replace": "int c = 30;",
                    },
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            workspace_text = _workspace_file(materialization).read_text(encoding="utf-8")
            self.assertIn("int a = 10;", workspace_text)
            self.assertIn("int c = 30;", workspace_text)
            self.assertEqual(materialization["line_range_exact_matches"], 2)

    def test_line_range_mismatch_fallback_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int a = 1;\nint unique = 7;\n")
            run_dir = tmp_path / "candidate_fallback"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int unique = 7;",
                        "replace": "int unique = 8;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["line_range_fallback_matches"], 1)
            self.assertTrue(materialization["line_range_fallback_used"])
            self.assertTrue(materialization["line_range_allow_exact_search_fallback"])
            result = materialization["line_range_edit_results"][0]
            self.assertEqual(result["match_mode"], "exact_search_fallback")
            self.assertTrue(result["line_range_valid"])

    def test_invalid_line_range_exact_search_fallback_success_records_specific_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int unique = 7;\n")
            run_dir = tmp_path / "candidate_invalid_range_fallback"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 99,
                        "end_line": 99,
                        "original": "int unique = 7;",
                        "replace": "int unique = 8;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            result = materialization["line_range_edit_results"][0]
            self.assertEqual(result["match_mode"], "invalid_line_range_exact_search_fallback")
            self.assertFalse(result["line_range_valid"])
            self.assertEqual(result["fallback_match_count"], 1)

    def test_line_range_mismatch_uses_internal_exact_search_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int a = 1;\nint unique = 7;\n")
            run_dir = tmp_path / "candidate_no_fallback"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int unique = 7;",
                        "replace": "int unique = 8;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "success")
            self.assertTrue(materialization["line_range_allow_exact_search_fallback"])
            result = materialization["line_range_edit_results"][0]
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["method"], "exact_search_fallback")

    def test_fallback_ambiguous_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int same = 1;\nint x = 0;\nint same = 1;\n")
            run_dir = tmp_path / "candidate_ambiguous"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 2,
                        "end_line": 2,
                        "original": "int same = 1;",
                        "replace": "int same = 2;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["failed_step"], "line_range_apply")
            self.assertEqual(materialization["patch_apply_strategy"], "line_range_edits_failed")
            failed = materialization["line_range_edit_results"][0]
            self.assertEqual(failed["file"], TARGET_FILE)
            self.assertEqual(failed["start_line"], 2)
            self.assertEqual(failed["end_line"], 2)
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["failure_reason"], "fallback_ambiguous")
            self.assertEqual(failed["fallback_match_count"], 2)

    def test_original_not_found_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_not_found"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int missing = 9;",
                        "replace": "int missing = 10;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["failed_step"], "line_range_apply")
            self.assertIn("not found", materialization["error_message"])
            failed = materialization["line_range_edit_results"][0]
            self.assertEqual(failed["failure_reason"], "fallback_no_match")
            self.assertEqual(failed["fallback_match_count"], 0)
            self.assertIsNone(materialization["generated_diff_path"])
            self.assertFalse(materialization["generated_diff_created"])
            self.assertFalse((run_dir / "candidate.generated.diff").exists())

    def test_failed_multiple_edits_include_not_attempted_results_sorted_by_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int a = 1;\nint b = 2;\nint c = 3;\n")
            run_dir = tmp_path / "candidate_partial_failure"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int a = 1;",
                        "replace": "int a = 10;",
                    },
                    {
                        "start_line": 2,
                        "end_line": 2,
                        "original": "int missing = 9;",
                        "replace": "int missing = 10;",
                    },
                    {
                        "start_line": 3,
                        "end_line": 3,
                        "original": "int c = 3;",
                        "replace": "int c = 30;",
                    },
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            results = materialization["line_range_edit_results"]
            self.assertEqual([result["index"] for result in results], [0, 1, 2])
            self.assertEqual(len(results), 3)
            self.assertEqual(results[0]["status"], "not_attempted")
            self.assertEqual(results[0]["failure_reason"], "previous_edit_failed")
            self.assertEqual(results[1]["status"], "failed")
            self.assertEqual(results[1]["failure_reason"], "fallback_no_match")
            self.assertEqual(results[2]["status"], "success")
            self.assertEqual(results[2]["match_mode"], "line_range_exact")

    def test_line_range_noop_skipped_without_candidate_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_noop"
            _line_candidate(run_dir, edits=[])

            exit_code = _materialize(tmp_path, run_dir, base_source_root)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "skipped")
            self.assertEqual(materialization["patch_apply_strategy"], "not_run")

    def test_repo_internal_base_source_root_paths_are_portable_in_materialization(self) -> None:
        workspace_parent = REPO_ROOT / "workspace"
        workspace_parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=workspace_parent) as tmpdir:
            base_source_root = Path(tmpdir) / "current_best_source"
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = Path(tmpdir) / "candidate_portable_paths"
            _line_candidate(
                run_dir,
                edits=[
                    {
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
                    "--candidate-workspace-dir",
                    str(Path(tmpdir) / "workspaces" / run_dir.name),
                    "--base-source-root",
                    str(base_source_root),
                    "--overwrite",
                    "--allowed-file",
                    TARGET_FILE,
                    "--target-file",
                    TARGET_FILE,
                ]
            )

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["source_root"], materialization["base_source_root"])
            self.assertTrue(materialization["source_root"].startswith("workspace/"))
            self.assertNotIn(str(base_source_root.resolve()), json.dumps(materialization))

    def test_repo_relative_base_source_root_paths_are_portable_in_materialization(self) -> None:
        workspace_parent = REPO_ROOT / "workspace"
        workspace_parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=workspace_parent) as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path) / "current_best_source"
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_relative_portable_paths"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int value = 1;",
                        "replace": "int value = 2;",
                    }
                ],
            )
            relative_base_source_root = base_source_root.resolve().relative_to(REPO_ROOT).as_posix()

            exit_code = materialize_main(
                [
                    "--candidate-run",
                    str(run_dir),
                    "--candidate-workspace-dir",
                    str(tmp_path / "workspaces" / run_dir.name),
                    "--base-source-root",
                    relative_base_source_root,
                    "--overwrite",
                    "--allowed-file",
                    TARGET_FILE,
                    "--target-file",
                    TARGET_FILE,
                ]
            )

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["source_root"], relative_base_source_root)
            self.assertEqual(materialization["base_source_root"], relative_base_source_root)
            self.assertFalse(Path(materialization["source_root"]).is_absolute())
            self.assertFalse(Path(materialization["base_source_root"]).is_absolute())
            self.assertNotIn(str(base_source_root.resolve()), json.dumps(materialization))

    # --- New schema tests (--target-file, edits without file) ---

    def test_new_schema_exact_line_range_edit_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_new_exact"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "int value = 1;",
                        "replace": "int value = 2;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root, target_file=TARGET_FILE)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "success")
            self.assertEqual(materialization["target_files"], [TARGET_FILE])
            self.assertEqual(materialization["edit_files"], [TARGET_FILE])
            self.assertEqual(materialization["changed_files"], [TARGET_FILE])
            file_path = Path(materialization["workspace_path"]) / TARGET_FILE
            self.assertEqual(file_path.read_text(encoding="utf-8"), "int value = 2;\n")

    def test_new_schema_noop_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_new_noop"
            _line_candidate(run_dir, edits=[])

            exit_code = _materialize(tmp_path, run_dir, base_source_root, target_file=TARGET_FILE)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "skipped")
            self.assertEqual(materialization["target_files"], [TARGET_FILE])
            self.assertEqual(materialization["edit_files"], [])
            self.assertEqual(materialization["changed_files"], [])

    def test_new_schema_line_range_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_new_mismatch"
            _line_candidate(
                run_dir,
                edits=[
                    {
                        "start_line": 1,
                        "end_line": 1,
                        "original": "THIS DOES NOT MATCH",
                        "replace": "int value = 2;",
                    }
                ],
            )

            exit_code = _materialize(tmp_path, run_dir, base_source_root, target_file=TARGET_FILE)

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "failed")

    def test_new_schema_target_file_validated_against_allowed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            base_source_root = _source_dir(tmp_path)
            _write_source(base_source_root, "int value = 1;\n")
            run_dir = tmp_path / "candidate_new_scope"
            _line_candidate(
                run_dir,
                edits=[
                    {
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
                    "--candidate-workspace-dir",
                    str(tmp_path / "workspaces" / run_dir.name),
                    "--base-source-root",
                    str(base_source_root),
                    "--overwrite",
                    "--allowed-file",
                    "cpp/external/lambdatwist/p3p.cc",  # different from TARGET_FILE
                    "--target-file",
                    TARGET_FILE,
                ]
            )

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "failed")
            self.assertIn("outside allowed optimization scope", materialization["error_message"])

if __name__ == "__main__":
    unittest.main()
