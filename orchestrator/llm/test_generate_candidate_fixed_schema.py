"""Tests for generate_candidate fixed schema artifacts."""

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
    _llm_usage_metadata,
    _parse_args,
    _print_final_summary,
    _save_candidate_artifacts,
)
from orchestrator.llm.base import LLMResponse
from orchestrator.llm.response_parser import LineRangeEdit, OptimizationCandidate


TARGET_FILE = "cpp/src/example.cpp"


def _candidate() -> OptimizationCandidate:
    return OptimizationCandidate(
        summary="summary",
        rationale="rationale",
        risk_level="low",
        expected_effect="runtime",
        target_files=[TARGET_FILE],
        correctness_notes="correctness",
        edits=[
            LineRangeEdit(
                file=TARGET_FILE,
                start_line=1,
                end_line=1,
                original="double value = make_value();",
                replace="const double value = make_value();",
            )
        ],
        requires_manual_review=True,
    )


class GenerateCandidateFixedSchemaTests(unittest.TestCase):
    def test_parse_args_has_no_format_attributes(self) -> None:
        args = _parse_args(["--config", "llm.json", "--source", TARGET_FILE])

        self.assertFalse(hasattr(args, "candidate" + "_type"))
        self.assertFalse(hasattr(args, "source" + "_presentation"))

    def test_artifacts_write_candidate_edits_json_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _save_candidate_artifacts(run_dir, _candidate())

            edits_payload = json.loads((run_dir / "candidate.edits.json").read_text(encoding="utf-8"))
            self.assertTrue((run_dir / "candidate.json").exists())
            self.assertFalse((run_dir / ("candidate" + ".diff")).exists())
            self.assertEqual(edits_payload["edits"][0]["file"], TARGET_FILE)

    def test_metadata_status_and_summary_do_not_include_removed_format_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            metadata = _build_metadata(
                "run-id",
                TARGET_FILE,
                ".",
                TARGET_FILE,
                None,
                datetime(2026, 1, 1),
            )
            metadata["finished_at"] = metadata["started_at"]
            status = _build_status("success", None, None)
            summary = _build_summary(run_dir, metadata, status, _candidate())

        self.assertNotIn("candidate" + "_format", metadata)
        self.assertNotIn("candidate" + "_format", status)
        self.assertIn("Edit count: 1", summary)
        self.assertNotIn("Candidate format", summary)
        self.assertNotIn("Candidate type", summary)

    def test_index_record_uses_edit_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            metadata = _build_metadata(
                "run-id",
                TARGET_FILE,
                ".",
                TARGET_FILE,
                None,
                datetime(2026, 1, 1),
            )
            status = _build_status("success", None, None)

            record = _build_index_record(metadata, status, _candidate(), run_dir)

        self.assertEqual(record["edit_count"], 1)
        self.assertFalse(record["is_noop"])
        self.assertNotIn("candidate" + "_type", record)

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
                _build_status("success", None, None),
                Path("results/runs/llm_candidate_unicode"),
                OptimizationCandidate(
                    summary="well-optimized no-op candidate",
                    rationale="rationale",
                    risk_level="low",
                    expected_effect="none",
                    target_files=[TARGET_FILE],
                    correctness_notes="correctness",
                    edits=[],
                    requires_manual_review=False,
                ),
            )
        finally:
            sys.stdout = original_stdout

        output = "".join(stdout.lines)
        self.assertTrue(output.startswith("CANDIDATE_RUN_DIR="))
        self.assertIn("well-optimized", output)
        self.assertIn("Edit count: 0", output)
        self.assertIn("No-op: True", output)

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
                        "summary": "no-op",
                        "rationale": "safe",
                        "risk_level": "low",
                        "expected_effect": "none",
                        "target_files": [TARGET_FILE],
                        "correctness_notes": "none",
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
                    ["--config", str(config_path), "--source", TARGET_FILE]
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
