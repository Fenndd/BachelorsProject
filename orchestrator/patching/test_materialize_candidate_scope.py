"""Focused tests for materialize_candidate scope enforcement artifacts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.patching.materialize_candidate import main as materialize_main


def _write_candidate(
    run_dir: Path,
    *,
    target_files: list[str],
    diff_text: str = "",
    expected_effect: str = "none",
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "candidate.json").write_text(
        json.dumps(
            {
                "summary": "test candidate",
                "target_files": target_files,
                "expected_effect": expected_effect,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "candidate.diff").write_text(diff_text, encoding="utf-8")


def _noop_materialize(run_dir: Path, allowed_files: list[str] | None = None) -> int:
    argv = [
        "--candidate-run",
        str(run_dir),
        "--workspace-root",
        str(run_dir.parent / "workspaces"),
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
            _write_candidate(
                run_dir,
                target_files=[r"cpp\external\lambdatwist\p3p.cc"],
            )

            exit_code = _noop_materialize(
                run_dir,
                allowed_files=["cpp/external/lambdatwist/p3p.cc"],
            )

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "skipped")
            self.assertEqual(
                materialization["scope_enforcement"], "external_allowed_files"
            )
            self.assertTrue(materialization["external_allowed_files_used"])
            self.assertEqual(
                materialization["allowed_files"], ["cpp/external/lambdatwist/p3p.cc"]
            )
            self.assertEqual(
                materialization["target_files"], ["cpp/external/lambdatwist/p3p.cc"]
            )

    def test_target_outside_external_allowed_file_fails_and_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "candidate_target_outside"
            _write_candidate(
                run_dir,
                target_files=["cpp/external/lambdatwist/other.cc"],
            )

            exit_code = _noop_materialize(
                run_dir,
                allowed_files=["cpp/external/lambdatwist/p3p.cc"],
            )

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertEqual(materialization["overall_status"], "failed")
            self.assertEqual(materialization["failed_step"], "validate_patch_scope")
            self.assertEqual(
                materialization["scope_enforcement"], "external_allowed_files"
            )
            self.assertTrue(materialization["external_allowed_files_used"])
            self.assertEqual(
                materialization["allowed_files"], ["cpp/external/lambdatwist/p3p.cc"]
            )
            self.assertIn("outside allowed optimization scope", materialization["error_message"])

    def test_patched_file_outside_candidate_target_files_fails(self) -> None:
        diff_text = "\n".join(
            [
                "--- a/cpp/external/lambdatwist/other.cc",
                "+++ b/cpp/external/lambdatwist/other.cc",
                "@@ -1 +1 @@",
                "-old",
                "+new",
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "candidate_patch_outside_target"
            _write_candidate(
                run_dir,
                target_files=["cpp/external/lambdatwist/p3p.cc"],
                diff_text=diff_text,
                expected_effect="faster runtime",
            )

            exit_code = _noop_materialize(
                run_dir,
                allowed_files=[
                    "cpp/external/lambdatwist/p3p.cc",
                    "cpp/external/lambdatwist/other.cc",
                ],
            )

            self.assertEqual(exit_code, 1)
            materialization = _read_materialization(run_dir)
            self.assertIn("not listed in", materialization["error_message"])
            self.assertEqual(
                materialization["patched_files"], ["cpp/external/lambdatwist/other.cc"]
            )

    def test_legacy_mode_uses_candidate_target_files_as_allowed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "candidate_legacy"
            _write_candidate(run_dir, target_files=["cpp/external/lambdatwist/p3p.cc"])

            exit_code = _noop_materialize(run_dir)

            self.assertEqual(exit_code, 0)
            materialization = _read_materialization(run_dir)
            self.assertEqual(
                materialization["scope_enforcement"],
                "legacy_candidate_declared_target_files",
            )
            self.assertFalse(materialization["external_allowed_files_used"])
            self.assertEqual(
                materialization["allowed_files"], ["cpp/external/lambdatwist/p3p.cc"]
            )


if __name__ == "__main__":
    unittest.main()