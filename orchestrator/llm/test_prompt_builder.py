"""Tests for prompt builder candidate format modes."""

from __future__ import annotations

import unittest

from orchestrator.llm.prompt_builder import (
    build_optimization_prompt,
    format_source_line_numbered,
)


SOURCE_PATH = "cpp/external/lambdatwist/p3p.cc"
SOURCE_CODE = "int first = 1;\nint second = 2;\n"


class PromptBuilderTests(unittest.TestCase):
    def test_default_prompt_produces_unified_diff_prompt(self) -> None:
        _system_prompt, user_prompt = build_optimization_prompt(
            SOURCE_PATH,
            SOURCE_CODE,
        )

        self.assertIn('"schema_version": "1.0"', user_prompt)
        self.assertIn('"candidate_type": "unified_diff"', user_prompt)
        self.assertIn('"unified_diff"', user_prompt)
        self.assertIn(SOURCE_CODE, user_prompt)
        self.assertNotIn("0001 |", user_prompt)

    def test_line_range_edits_prompt_contains_schema_and_numbered_source(self) -> None:
        _system_prompt, user_prompt = build_optimization_prompt(
            SOURCE_PATH,
            SOURCE_CODE,
            candidate_type="line_range_edits",
            source_presentation="line_numbered",
        )

        self.assertIn('"schema_version": "1.1"', user_prompt)
        self.assertIn('"candidate_type": "line_range_edits"', user_prompt)
        self.assertIn("edits[]", user_prompt)
        self.assertIn('"edits": [', user_prompt)
        self.assertIn("0001 | int first = 1;", user_prompt)
        self.assertIn("0002 | int second = 2;", user_prompt)
        self.assertIn("Line numbers are the integer labels shown before the", user_prompt)
        self.assertIn("Use those exact shown line labels as start_line and end_line", user_prompt)
        self.assertIn("Do not offset, expand, infer, or transform line numbers", user_prompt)
        self.assertIn("include enough original lines to make the edit unambiguous", user_prompt)

    def test_format_source_line_numbered_preserves_empty_lines(self) -> None:
        formatted = format_source_line_numbered("first\n\nthird\n")

        self.assertEqual(formatted, "0001 | first\n0002 | \n0003 | third")

    def test_invalid_candidate_type_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            build_optimization_prompt(
                SOURCE_PATH,
                SOURCE_CODE,
                candidate_type="json_patch",
            )

    def test_invalid_source_presentation_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            build_optimization_prompt(
                SOURCE_PATH,
                SOURCE_CODE,
                source_presentation="annotated",
            )

    def test_unified_diff_with_line_numbered_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            build_optimization_prompt(
                SOURCE_PATH,
                SOURCE_CODE,
                candidate_type="unified_diff",
                source_presentation="line_numbered",
            )

    def test_line_range_edits_with_plain_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            build_optimization_prompt(
                SOURCE_PATH,
                SOURCE_CODE,
                candidate_type="line_range_edits",
                source_presentation="plain",
            )


if __name__ == "__main__":
    unittest.main()