"""Focused tests for materialize_candidate git apply --recount fallback."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.patching.materialize_candidate import main as materialize_main


def _write_candidate(run_dir: Path, diff_text: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "candidate.json").write_text(
        json.dumps(
            {
                "summary": "test recount candidate",
                "target_files": ["cpp/example.cpp"],
                "expected_effect": "faster runtime",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "candidate.diff").write_text(diff_text, encoding="utf-8")


class MaterializeCandidateRecountTests(unittest.TestCase):
    def test_wrong_hunk_count_patch_uses_recount_fallback(self) -> None:
        diff_text = "\n".join(
            [
                "--- a/cpp/example.cpp",
                "+++ b/cpp/example.cpp",
                "@@ -1,2 +1,2 @@",
                "-int value = 1;",
                "+int value = 2;",
                "",
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_root = tmp_path / "cpp"
            source_root.mkdir(parents=True)
            (source_root / "example.cpp").write_text(
                "int value = 1;\n", encoding="utf-8"
            )

            run_dir = tmp_path / "candidate_recount"
            _write_candidate(run_dir, diff_text)

            exit_code = materialize_main(
                [
                    "--candidate-run",
                    str(run_dir),
                    "--workspace-root",
                    str(tmp_path / "workspaces"),
                    "--source-root",
                    str(source_root),
                    "--overwrite",
                    "--allowed-file",
                    "cpp/example.cpp",
                ]
            )

            self.assertEqual(exit_code, 0)
            materialization = json.loads(
                (run_dir / "materialization.json").read_text(encoding="utf-8")
            )
            self.assertEqual(materialization["overall_status"], "success")
            self.assertEqual(
                materialization["patch_apply_strategy"], "git_apply_recount"
            )
            self.assertTrue(materialization["git_apply_recount_used"])
            self.assertTrue(materialization["git_apply_initial_check_failed"])
            self.assertIn("cpp/example.cpp", materialization["changed_files"])

            log_text = (run_dir / "apply_candidate.log").read_text(encoding="utf-8")
            self.assertIn("--recount", log_text)


if __name__ == "__main__":
    unittest.main()