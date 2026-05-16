"""Tests for generate_candidate candidate format args and artifacts."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from orchestrator.llm import generate_candidate as generate_candidate_module
from orchestrator.llm.generate_candidate import (
    _build_index_record,
    _build_metadata,
    _build_status,
    _build_summary,
    _parse_args,
    _print_final_summary,
    _llm_usage_metadata,
    _save_candidate_artifacts,
)
from orchestrator.llm.base import LLMResponse
from orchestrator.llm.response_parser import LineRangeEdit, OptimizationCandidate


TARGET_FILE = "cpp/src/example.cpp"
UNIFIED_FORMAT = {"type": "unified_diff", "source_presentation": "plain"}
LINE_RANGE_FORMAT = {
    "type": "line_range_edits",
    "source_presentation": "line_numbered",
}


def _candidate(candidate_type: str) -> OptimizationCandidate:
    edits = []
    unified_diff = ""
    schema_version = "1.1"
    if candidate_type == "unified_diff":
        schema_version = "1.0"
        unified_diff = (
            "diff --git a/cpp/src/example.cpp b/cpp/src/example.cpp\n"
            "--- a/cpp/src/example.cpp\n"
            "+++ b/cpp/src/example.cpp\n"
            "@@ -1,3 +1,3 @@\n"
            "-double value = make_value();\n"
            "+const double value = make_value();\n"
        )
    else:
        edits = [
            LineRangeEdit(
                file=TARGET_FILE,
                start_line=1,
                end_line=1,
                original="double value = make_value();",
                replace="const double value = make_value();",
            )
        ]

    return OptimizationCandidate(
        schema_version=schema_version,
        candidate_type=candidate_type,
        summary="summary",
        rationale="rationale",
        risk_level="low",
        expected_effect="runtime",
        target_files=[TARGET_FILE],
        correctness_notes="correctness",
        unified_diff=unified_diff,
        edits=edits,
        requires_manual_review=True,
    )


class GenerateCandidateCandidateFormatTests(unittest.TestCase):
    def test_parse_args_defaults_to_unified_diff_plain(self) -> None:
        args = _parse_args(["--config", "llm.json", "--source", TARGET_FILE])

        self.assertEqual(args.candidate_type, "unified_diff")
        self.assertEqual(args.source_presentation, "plain")

    def test_parse_args_accepts_line_range_edits_line_numbered(self) -> None:
        args = _parse_args(
            [
                "--config",
                "llm.json",
                "--source",
                TARGET_FILE,
                "--candidate-type",
                "line_range_edits",
                "--source-presentation",
                "line_numbered",
            ]
        )

        self.assertEqual(args.candidate_type, "line_range_edits")
        self.assertEqual(args.source_presentation, "line_numbered")

    def test_unified_diff_artifacts_write_candidate_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _save_candidate_artifacts(run_dir, _candidate("unified_diff"))

            self.assertTrue((run_dir / "candidate.json").exists())
            self.assertTrue((run_dir / "candidate.diff").exists())
            self.assertFalse((run_dir / "candidate.edits.json").exists())

    def test_line_range_artifacts_write_candidate_edits_json_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _save_candidate_artifacts(run_dir, _candidate("line_range_edits"))

            edits_payload = json.loads((run_dir / "candidate.edits.json").read_text(encoding="utf-8"))
            self.assertTrue((run_dir / "candidate.json").exists())
            self.assertFalse((run_dir / "candidate.diff").exists())
            self.assertEqual(edits_payload["edits"][0]["file"], TARGET_FILE)

    def test_metadata_status_and_summary_include_candidate_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            metadata = _build_metadata(
                "run-id",
                TARGET_FILE,
                ".",
                TARGET_FILE,
                None,
                datetime(2026, 1, 1),
                LINE_RANGE_FORMAT,
            )
            metadata["finished_at"] = metadata["started_at"]
            status = _build_status("success", None, None, LINE_RANGE_FORMAT)
            summary = _build_summary(run_dir, metadata, status, _candidate("line_range_edits"))

        self.assertEqual(metadata["candidate_format"], LINE_RANGE_FORMAT)
        self.assertEqual(status["candidate_format"], LINE_RANGE_FORMAT)
        self.assertIn("Candidate format: line_range_edits", summary)
        self.assertIn("Source presentation: line_numbered", summary)
        self.assertIn("Candidate type: line_range_edits", summary)
        self.assertIn("Structured edits count: 1", summary)
        self.assertIn("Candidate edits present: True", summary)
        self.assertNotIn("Unified diff present", summary)

    def test_line_range_index_record_uses_candidate_edits_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            metadata = _build_metadata(
                "run-id",
                TARGET_FILE,
                ".",
                TARGET_FILE,
                None,
                datetime(2026, 1, 1),
                LINE_RANGE_FORMAT,
            )
            status = _build_status("success", None, None, LINE_RANGE_FORMAT)

            record = _build_index_record(metadata, status, _candidate("line_range_edits"), run_dir)

        self.assertEqual(record["candidate_type"], "line_range_edits")
        self.assertEqual(record["structured_edit_count"], 1)
        self.assertTrue(record["candidate_edits_present"])
        self.assertFalse(record["unified_diff_present"])

    def test_unified_diff_summary_keeps_unified_diff_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            metadata = _build_metadata(
                "run-id",
                TARGET_FILE,
                ".",
                TARGET_FILE,
                None,
                datetime(2026, 1, 1),
                UNIFIED_FORMAT,
            )
            metadata["finished_at"] = metadata["started_at"]
            status = _build_status("success", None, None, UNIFIED_FORMAT)
            summary = _build_summary(run_dir, metadata, status, _candidate("unified_diff"))

        self.assertIn("Candidate type: unified_diff", summary)
        self.assertIn("Unified diff present: True", summary)
        self.assertNotIn("Structured edits count", summary)

    def test_final_summary_prints_run_dir_before_unicode_candidate_summary(self) -> None:
        class StrictAsciiStdout:
            encoding = "ascii"

            def __init__(self) -> None:
                self.lines: list[str] = []

            def write(self, text: str) -> int:
                text.encode("ascii")
                self.lines.append(text)
                return len(text)

            def flush(self) -> None:
                pass

        stdout = StrictAsciiStdout()
        original_stdout = sys.stdout
        try:
            sys.stdout = stdout  # type: ignore[assignment]
            _print_final_summary(
                _build_status("success", None, None, LINE_RANGE_FORMAT),
                Path("results/runs/llm_candidate_unicode"),
                OptimizationCandidate(
                    schema_version="1.1",
                    candidate_type="line_range_edits",
                    summary="well‑optimized no-op candidate",
                    rationale="rationale",
                    risk_level="low",
                    expected_effect="none",
                    target_files=[TARGET_FILE],
                    correctness_notes="correctness",
                    unified_diff="",
                    edits=[],
                    requires_manual_review=False,
                ),
            )
        finally:
            sys.stdout = original_stdout

        output = "".join(stdout.lines)
        self.assertTrue(output.startswith("CANDIDATE_RUN_DIR="))
        self.assertIn("well?optimized", output)
        self.assertIn("Candidate type: line_range_edits", output)
        self.assertIn("Structured edits count: 0", output)
        self.assertIn("Candidate edits present: False", output)
        self.assertNotIn("Unified diff present", output)

    def test_llm_usage_metadata_extracts_openai_compatible_fields(self) -> None:
        response = LLMResponse(
            provider="deepseek",
            model="config-model",
            content="{}",
            reasoning_content=None,
            raw_response={
                "model": "response-model",
                "choices": [{"finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 22,
                    "total_tokens": 33,
                },
            },
        )

        usage = _llm_usage_metadata(response, 0.123)

        self.assertEqual(usage["prompt_tokens"], 11)
        self.assertEqual(usage["completion_tokens"], 22)
        self.assertEqual(usage["total_tokens"], 33)
        self.assertEqual(usage["api_latency_seconds"], 0.123)
        self.assertEqual(usage["finish_reason"], "stop")
        self.assertEqual(usage["model"], "response-model")

    def test_generate_candidate_writes_llm_usage_for_mock_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / TARGET_FILE
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text("double value = 1.0;\n", encoding="utf-8")
            response_file = root / "mock_response.json"
            response_file.write_text(
                json.dumps(
                    {
                        "schema_version": "1.1",
                        "candidate_type": "line_range_edits",
                        "summary": "no-op",
                        "rationale": "safe",
                        "risk_level": "low",
                        "expected_effect": "none",
                        "target_files": [TARGET_FILE],
                        "correctness_notes": "none",
                        "unified_diff": "",
                        "edits": [],
                        "requires_manual_review": False,
                    }
                ),
                encoding="utf-8",
            )
            config_path = root / "llm_mock.json"
            config_path.write_text(
                json.dumps(
                    {
                        "provider": "mock",
                        "model": "mock-model",
                        "mock_response_file": str(response_file),
                    }
                ),
                encoding="utf-8",
            )
            original_root = generate_candidate_module.REPO_ROOT
            try:
                generate_candidate_module.REPO_ROOT = root
                exit_code = generate_candidate_module.main(
                    [
                        "--config",
                        str(config_path),
                        "--source",
                        TARGET_FILE,
                        "--candidate-type",
                        "line_range_edits",
                        "--source-presentation",
                        "line_numbered",
                    ]
                )
            finally:
                generate_candidate_module.REPO_ROOT = original_root

            self.assertEqual(exit_code, 0)
            run_dir = next((root / "results" / "runs").iterdir())
            payload = json.loads((run_dir / "llm_response.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["llm_usage"]["model"], "mock-model")
            self.assertEqual(payload["llm_usage"]["finish_reason"], "stop")
            self.assertIsNone(payload["llm_usage"]["prompt_tokens"])
            self.assertIsInstance(payload["llm_usage"]["api_latency_seconds"], float)


if __name__ == "__main__":
    unittest.main()
