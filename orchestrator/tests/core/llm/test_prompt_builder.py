"""Tests for prompt builder line-range edit prompts."""

from __future__ import annotations

import pytest
import unittest

pytestmark = pytest.mark.unit

from orchestrator.core.llm.prompt_builder import (
    PROMPT_VERSION,
    build_optimization_prompt,
    format_source_line_numbered,
)


SOURCE_CODE = "int first = 1;\nint second = 2;\n"


class PromptBuilderTests(unittest.TestCase):
    def test_returns_both_system_and_user_prompts(self) -> None:
        system, user, sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)
        self.assertIsInstance(sections, dict)
        self.assertGreater(len(system), 0)
        self.assertGreater(len(user), 0)

    def test_prompt_does_not_contain_target_file_path(self) -> None:
        _system, user, _sections = build_optimization_prompt(
            SOURCE_CODE,
            additional_context="some guidance",
        )

        self.assertNotIn("Target file path", user)
        self.assertNotIn("p3p.cc", user)

    def test_prompt_does_not_contain_allowed_files(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertNotIn("Allowed files", user)
        self.assertNotIn("Hard rule", user)
        self.assertNotIn("Do not modify benchmark", user)

    def test_prompt_does_not_contain_p3p_or_lambdatwist_text(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertNotIn("P3P", user)
        self.assertNotIn("Lambda Twist", user)

    def test_prompt_does_not_contain_hard_rule_about_other_files(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertNotIn("Do not modify benchmark", user)
        self.assertNotIn("tests, adapters", user)
        self.assertNotIn("CMake", user)
        self.assertNotIn("orchestrator", user)

    def test_prompt_contains_task_section(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn("Task:", user)
        self.assertIn("Improve computational efficiency", user)
        self.assertIn("If no safe improvement is available, return edits = [].", user)

    def test_prompt_contains_additional_context_section(self) -> None:
        _system, user, _sections = build_optimization_prompt(
            SOURCE_CODE,
            additional_context="Use constexpr where possible.",
        )

        self.assertIn("User guidance:", user)
        self.assertIn("Use constexpr where possible.", user)
        self.assertNotIn("User guidance / additional context:", user)

    def test_prompt_contains_no_additional_guidance_fallback(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn("No additional user guidance.", user)

    def test_prompt_contains_history_context_section(self) -> None:
        _system, user, _sections = build_optimization_prompt(
            SOURCE_CODE,
            history_context="Iteration 1: accepted improvement.\nIdea: use constexpr.",
        )

        self.assertIn("Previous attempts:", user)
        self.assertIn("Iteration 1: accepted improvement.", user)
        self.assertIn("use constexpr.", user)

    def test_prompt_contains_no_previous_attempts_fallback(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn("No previous attempts.", user)

    def test_prompt_sections_are_returned(self) -> None:
        _system, _user, sections = build_optimization_prompt(
            SOURCE_CODE,
            additional_context="guidance",
            history_context="history",
        )

        expected_keys = {
            "task",
            "user_guidance",
            "previous_attempts",
            "source_code",
            "safety_constraints",
            "line_edit_rules",
            "output_schema",
        }
        self.assertEqual(set(sections.keys()), expected_keys)
        self.assertIn("guidance", sections["user_guidance"])
        self.assertIn("history", sections["previous_attempts"])

    def test_prompt_contains_source_code_with_line_numbers(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn("Source code with 1-based line numbers", user)
        self.assertIn("0001 | int first = 1;", user)
        self.assertIn("0002 | int second = 2;", user)
        self.assertIn("<source_code>", user)
        self.assertIn("</source_code>", user)

    def test_prompt_contains_safety_constraints(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn("Safety constraints:", user)
        self.assertIn("Preserve solver semantics", user)
        self.assertIn("Treat Eigen expressions as lazy", user)
        self.assertIn("Do not reorder floating-point computations", user)

    def test_prompt_contains_line_edit_rules(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn("Line edit rules:", user)
        self.assertIn("start_line and end_line must use the line numbers", user)
        self.assertIn('before the "|" separator', user)
        self.assertIn("original must exactly match", user)
        self.assertIn("replace must contain only replacement", user)
        self.assertIn("Return edits = [] if no safe optimization is available.", user)

    def test_prompt_contains_minimal_schema(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn("Required JSON output schema:", user)
        self.assertIn('"summary"', user)
        self.assertIn('"rationale"', user)
        self.assertIn('"correctness_notes"', user)
        self.assertIn('"edits"', user)
        self.assertIn('"start_line"', user)
        self.assertIn('"end_line"', user)
        self.assertIn('"original"', user)
        self.assertIn('"replace"', user)

    def test_prompt_includes_no_op_example(self) -> None:
        _system, user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn('"edits": []', user)

    def test_system_prompt_is_minimal(self) -> None:
        system, _user, _sections = build_optimization_prompt(SOURCE_CODE)

        self.assertIn("numerical optimization assistant", system)
        self.assertIn("Return only valid JSON", system)
        self.assertNotIn("Eigen aliasing", system)

    def test_format_source_line_numbered_preserves_empty_lines(self) -> None:
        formatted = format_source_line_numbered("first\n\nthird\n")

        self.assertEqual(formatted, "0001 | first\n0002 | \n0003 | third")


if __name__ == "__main__":
    unittest.main()
