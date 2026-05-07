"""Tests for response parser support for line_range_edits candidates."""

from __future__ import annotations

import json
import unittest
from typing import Any

from orchestrator.llm.response_parser import parse_optimization_candidate


TARGET_FILE = "cpp/src/example.cpp"
VALID_DIFF = (
    "diff --git a/cpp/src/example.cpp b/cpp/src/example.cpp\n"
    "--- a/cpp/src/example.cpp\n"
    "+++ b/cpp/src/example.cpp\n"
    "@@ -1,3 +1,3 @@\n"
    "-double value = make_value();\n"
    "+const double value = make_value();\n"
)


def _parse(payload: dict[str, Any]):
    return parse_optimization_candidate(json.dumps(payload))


def _unified_diff_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "candidate_type": "unified_diff",
        "summary": "Avoid repeated temporary allocation in a hot helper.",
        "rationale": "Reusing a local value may reduce per-call overhead.",
        "risk_level": "low",
        "expected_effect": "runtime",
        "target_files": [TARGET_FILE],
        "correctness_notes": "The proposed change preserves arithmetic order.",
        "unified_diff": VALID_DIFF,
        "requires_manual_review": True,
    }
    payload.update(overrides)
    return payload


def _line_range_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.1",
        "candidate_type": "line_range_edits",
        "summary": "Avoid repeated temporary allocation in a hot helper.",
        "rationale": "Reusing a local value may reduce per-call overhead.",
        "risk_level": "low",
        "expected_effect": "runtime",
        "target_files": [TARGET_FILE],
        "correctness_notes": "The proposed change preserves arithmetic order.",
        "edits": [
            {
                "file": TARGET_FILE,
                "start_line": 1,
                "end_line": 1,
                "original": "double value = make_value();",
                "replace": "const double value = make_value();",
            }
        ],
        "requires_manual_review": True,
    }
    payload.update(overrides)
    return payload


class ResponseParserLineRangeEditsTests(unittest.TestCase):
    def test_valid_unified_diff_still_parses(self) -> None:
        candidate = _parse(_unified_diff_payload())

        self.assertEqual(candidate.candidate_type, "unified_diff")
        self.assertEqual(candidate.unified_diff, VALID_DIFF)

    def test_valid_unified_diff_candidate_has_empty_edits(self) -> None:
        candidate = _parse(_unified_diff_payload())

        self.assertEqual(candidate.edits, [])

    def test_valid_line_range_edits_parses(self) -> None:
        candidate = _parse(_line_range_payload())

        self.assertEqual(candidate.candidate_type, "line_range_edits")
        self.assertEqual(len(candidate.edits), 1)
        self.assertEqual(candidate.edits[0].file, TARGET_FILE)

    def test_valid_line_range_edits_has_empty_unified_diff(self) -> None:
        candidate = _parse(_line_range_payload())

        self.assertEqual(candidate.unified_diff, "")

    def test_line_range_edits_runtime_with_empty_edits_is_rejected(self) -> None:
        self._assert_rejected(_line_range_payload(edits=[]))

    def test_line_range_edits_none_with_empty_edits_is_accepted(self) -> None:
        candidate = _parse(_line_range_payload(expected_effect="none", edits=[]))

        self.assertEqual(candidate.edits, [])

    def test_line_range_edits_unknown_schema_version_is_rejected(self) -> None:
        self._assert_rejected(_line_range_payload(schema_version="9.9"))

    def test_line_range_edits_start_line_less_than_one_is_rejected(self) -> None:
        self._assert_rejected_with_edit(start_line=0)

    def test_line_range_edits_end_line_before_start_line_is_rejected(self) -> None:
        self._assert_rejected_with_edit(start_line=3, end_line=2)

    def test_line_range_edits_bool_start_line_is_rejected(self) -> None:
        self._assert_rejected_with_edit(start_line=True)

    def test_line_range_edits_empty_original_is_rejected(self) -> None:
        self._assert_rejected_with_edit(original="")

    def test_line_range_edits_non_string_replace_is_rejected(self) -> None:
        self._assert_rejected_with_edit(replace=123)

    def test_line_range_edits_file_not_in_target_files_is_rejected(self) -> None:
        self._assert_rejected_with_edit(file="cpp/src/other.cpp")

    def test_unified_diff_with_schema_version_1_1_is_rejected(self) -> None:
        self._assert_rejected(_unified_diff_payload(schema_version="1.1"))

    def test_line_range_edits_with_non_empty_unified_diff_is_rejected(self) -> None:
        self._assert_rejected(_line_range_payload(unified_diff=VALID_DIFF))

    def _assert_rejected(self, payload: dict[str, Any]) -> None:
        with self.assertRaises(ValueError):
            _parse(payload)

    def _assert_rejected_with_edit(self, **edit_overrides: Any) -> None:
        payload = _line_range_payload()
        edit = dict(payload["edits"][0])
        edit.update(edit_overrides)
        payload["edits"] = [edit]

        self._assert_rejected(payload)


if __name__ == "__main__":
    unittest.main()