"""Tests for prompt builder line-range edit prompts."""

from __future__ import annotations

import unittest

from orchestrator.llm.prompt_builder import (
    build_optimization_prompt,
    format_source_line_numbered,
)


SOURCE_PATH = "cpp/external/lambdatwist/p3p.cc"
SOURCE_CODE = "int first = 1;\nint second = 2;\n"


class PromptBuilderTests(unittest.TestCase):
    def test_prompt_contains_single_edits_schema_and_numbered_source(self) -> None:
        _system_prompt, user_prompt = build_optimization_prompt(
            SOURCE_PATH,
            SOURCE_CODE,
        )

        self.assertIn("edits[]", user_prompt)
        self.assertIn('"edits": [', user_prompt)
        self.assertIn("0001 | int first = 1;", user_prompt)
        self.assertIn("0002 | int second = 2;", user_prompt)
        self.assertIn("Line numbers are the integer labels shown before the", user_prompt)
        self.assertIn("Use those exact shown line labels as start_line and end_line", user_prompt)
        self.assertNotIn("schema" + "_version", user_prompt)
        self.assertNotIn("candidate" + "_type", user_prompt)
        self.assertNotIn("unified" + "_diff", user_prompt)

    def test_format_source_line_numbered_preserves_empty_lines(self) -> None:
        formatted = format_source_line_numbered("first\n\nthird\n")

        self.assertEqual(formatted, "0001 | first\n0002 | \n0003 | third")


if __name__ == "__main__":
    unittest.main()
