"""Tests for the single edits[] optimization candidate schema."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import json
import unittest
from typing import Any

from orchestrator.core.llm.response_parser import parse_optimization_candidate


TARGET_FILE = "cpp/src/example.cpp"


def _parse(payload: dict[str, Any]):
    return parse_optimization_candidate(json.dumps(payload))


def _candidate_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
    def test_valid_edits_schema_parses_without_format_fields(self) -> None:
        candidate = _parse(_candidate_payload())

        self.assertEqual(len(candidate.edits), 1)
        self.assertEqual(candidate.edits[0].file, TARGET_FILE)

    def test_runtime_with_empty_edits_is_rejected(self) -> None:
        self._assert_rejected(_candidate_payload(edits=[]))

    def test_none_with_empty_edits_is_accepted(self) -> None:
        candidate = _parse(_candidate_payload(expected_effect="none", edits=[]))

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

    def test_file_not_in_target_files_is_rejected(self) -> None:
        self._assert_rejected_with_edit(file="cpp/src/other.cpp")

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
