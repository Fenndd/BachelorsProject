"""Tests for the single edits[] optimization candidate schema."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import json
import unittest
from typing import Any

from orchestrator.core.llm.response_parser import parse_optimization_candidate


SOURCE_CODE = "cpp/src/example.cpp"


def _parse(payload: dict[str, Any]):
    return parse_optimization_candidate(json.dumps(payload))


def _candidate_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "summary": "Avoid repeated temporary allocation in a hot helper.",
        "rationale": "Reusing a local value may reduce per-call overhead.",
        "correctness_notes": "The proposed change preserves arithmetic order.",
        "edits": [
            {
                "start_line": 1,
                "end_line": 1,
                "original": "double value = make_value();",
                "replace": "const double value = make_value();",
            }
        ],
    }
    payload.update(overrides)
    return payload


class ResponseParserLineRangeEditsTests(unittest.TestCase):
    def test_valid_edits_schema_parses(self) -> None:
        candidate = _parse(_candidate_payload())

        self.assertEqual(len(candidate.edits), 1)
        self.assertEqual(candidate.edits[0].start_line, 1)
        self.assertEqual(candidate.edits[0].end_line, 1)
        self.assertEqual(candidate.edits[0].original, "double value = make_value();")
        self.assertEqual(candidate.edits[0].replace, "const double value = make_value();")

    def test_empty_edits_is_accepted_as_noop(self) -> None:
        candidate = _parse(_candidate_payload(edits=[]))

        self.assertEqual(candidate.edits, [])

    def test_old_patch_payload_without_edits_is_rejected(self) -> None:
        payload = _candidate_payload()
        payload.pop("edits")
        payload["unified" + "_diff"] = "--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new\n"

        self._assert_rejected(payload)

    def test_start_line_less_than_one_is_rejected(self) -> None:
        self._assert_rejected_with_edit(start_line=0)

    def test_end_line_before_start_line_is_rejected(self) -> None:
        self._assert_rejected_with_edit(start_line=3, end_line=2)

    def test_bool_start_line_is_rejected(self) -> None:
        self._assert_rejected_with_edit(start_line=True)

    def test_empty_original_is_rejected(self) -> None:
        self._assert_rejected_with_edit(original="")

    def test_non_string_replace_is_rejected(self) -> None:
        self._assert_rejected_with_edit(replace=123)

    def test_parser_no_longer_requires_risk_level(self) -> None:
        candidate = _parse(_candidate_payload())

        self.assertFalse(hasattr(candidate, "risk_level"))

    def test_parser_no_longer_requires_expected_effect(self) -> None:
        candidate = _parse(_candidate_payload())

        self.assertFalse(hasattr(candidate, "expected_effect"))

    def test_parser_no_longer_requires_target_files(self) -> None:
        candidate = _parse(_candidate_payload())

        self.assertFalse(hasattr(candidate, "target_files"))

    def test_parser_no_longer_requires_requires_manual_review(self) -> None:
        candidate = _parse(_candidate_payload())

        self.assertFalse(hasattr(candidate, "requires_manual_review"))

    def test_parser_no_longer_requires_edit_file(self) -> None:
        candidate = _parse(_candidate_payload())

        self.assertFalse(hasattr(candidate.edits[0], "file"))

    def test_noop_accepted_with_empty_edits(self) -> None:
        candidate = _parse(
            _candidate_payload(
                summary="No safe local optimization found.",
                rationale="No change appears safe or useful.",
                correctness_notes="No code changes proposed.",
                edits=[],
            )
        )

        self.assertEqual(candidate.edits, [])
        self.assertEqual(candidate.summary, "No safe local optimization found.")

    def test_missing_summary_is_rejected(self) -> None:
        payload = _candidate_payload()
        payload.pop("summary")

        self._assert_rejected(payload)

    def test_missing_rationale_is_rejected(self) -> None:
        payload = _candidate_payload()
        payload.pop("rationale")

        self._assert_rejected(payload)

    def test_missing_correctness_notes_is_rejected(self) -> None:
        payload = _candidate_payload()
        payload.pop("correctness_notes")

        self._assert_rejected(payload)

    def _assert_rejected(self, payload: dict[str, Any]) -> None:
        with self.assertRaises(ValueError):
            _parse(payload)

    def _assert_rejected_with_edit(self, **edit_overrides: Any) -> None:
        payload = _candidate_payload()
        edit = dict(payload["edits"][0])
        edit.update(edit_overrides)
        payload["edits"] = [edit]

        self._assert_rejected(payload)


if __name__ == "__main__":
    unittest.main()
