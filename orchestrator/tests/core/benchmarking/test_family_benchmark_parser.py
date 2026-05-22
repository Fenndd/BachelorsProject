from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import unittest

from orchestrator.core.benchmarking.family_benchmark_parser import (
    parse_absolute_pose_benchmark_output,
)


def _valid_output() -> str:
    return "\n".join(
        [
            "solver_name: lambdatwist_p3p",
            "num_problems: 1000",
            "total_solutions: 3000",
            "solutions_per_problem: 3.0",
            "valid_solutions: 3000",
            "valid_solutions_percent: 100.0",
            "gt_found: 1000",
            "gt_found_percent: 100.0",
            "runtime_ns_total_median: 1234567",
            "runtime_ns_per_problem_median: 1234.567",
            "tolerance: 1e-6",
            "camera_fov: 75",
            "n_point_point: 3",
            "n_point_line: 0",
            "timed_iterations: 10",
            "runtime_unit: ns",
            "correctness_passed: true",
        ]
    )


class AbsolutePoseBenchmarkParserTests(unittest.TestCase):
    def test_valid_output(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(_valid_output())

        self.assertTrue(parsed["parse_success"])
        self.assertEqual(parsed["missing_fields"], [])
        self.assertEqual(parsed["metrics"]["solver_name"], "lambdatwist_p3p")
        self.assertEqual(parsed["metrics"]["num_problems"], 1000)
        self.assertEqual(parsed["metrics"]["total_solutions"], 3000)
        self.assertEqual(parsed["metrics"]["valid_solutions"], 3000)
        self.assertEqual(parsed["metrics"]["gt_found"], 1000)
        self.assertEqual(parsed["metrics"]["runtime_ns_per_problem_median"], 1234.567)
        self.assertIs(parsed["metrics"]["correctness_passed"], True)

    def test_extra_unrelated_lines_are_ignored(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            f"""
            hello benchmark
            C:\\some\\path
            {_valid_output()}
            done
            """
        )

        self.assertTrue(parsed["parse_success"])
        self.assertEqual(parsed["metrics"]["camera_fov"], 75.0)
        self.assertIs(parsed["metrics"]["correctness_passed"], True)

    def test_scientific_notation_floats(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            _valid_output()
            .replace("solutions_per_problem: 3.0", "solutions_per_problem: 3e+0")
            .replace("runtime_ns_total_median: 1234567", "runtime_ns_total_median: 3.267385e+07")
            .replace("runtime_ns_per_problem_median: 1234.567", "runtime_ns_per_problem_median: 3.267385e+04")
            .replace("correctness_passed: true", "correctness_passed: false")
        )

        self.assertTrue(parsed["parse_success"])
        self.assertEqual(parsed["metrics"]["solutions_per_problem"], 3.0)
        self.assertIs(parsed["metrics"]["correctness_passed"], False)

    def test_boolean_parsing_is_case_insensitive(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            _valid_output().replace("correctness_passed: true", "correctness_passed: FALSE")
        )

        self.assertTrue(parsed["parse_success"])
        self.assertIs(parsed["metrics"]["correctness_passed"], False)

    def test_missing_required_fields(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            """
            solver_name: lambdatwist_p3p
            gt_found_percent: 100.0
            correctness_passed: true
            """
        )

        self.assertFalse(parsed["parse_success"])
        self.assertIn("num_problems", parsed["missing_fields"])
        self.assertIn("runtime_ns_per_problem_median", parsed["missing_fields"])
        self.assertEqual(parsed["metrics"]["solver_name"], "lambdatwist_p3p")

    def test_old_reprojection_fields_do_not_satisfy_new_schema(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            """
            solver_name: lambdatwist_p3p
            num_cases: 1000
            success_rate: 1.0
            mean_best_reprojection_error: 1e-12
            max_best_reprojection_error: 2e-12
            runtime_ns_total_median: 1234567
            runtime_ns_per_case_median: 1234.567
            correctness_passed: true
            """
        )

        self.assertFalse(parsed["parse_success"])
        self.assertIn("num_problems", parsed["missing_fields"])
        self.assertIn("runtime_ns_per_problem_median", parsed["missing_fields"])
        self.assertNotIn("success_rate", parsed["metrics"])


if __name__ == "__main__":
    unittest.main()
