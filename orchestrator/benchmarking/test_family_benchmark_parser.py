from __future__ import annotations

import unittest

from orchestrator.benchmarking.family_benchmark_parser import (
    parse_absolute_pose_benchmark_output,
)


class AbsolutePoseBenchmarkParserTests(unittest.TestCase):
    def test_valid_output(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            "\n".join(
                [
                    "solver_name: lambdatwist_p3p",
                    "num_cases: 1000",
                    "success_rate: 1.0",
                    "mean_best_reprojection_error: 1.23e-10",
                    "max_best_reprojection_error: 4.56e-9",
                    "runtime_ns_total_median: 1234567",
                    "runtime_ns_per_case_median: 1234.567",
                    "correctness_passed: true",
                ]
            )
        )

        self.assertTrue(parsed["parse_success"])
        self.assertEqual(parsed["missing_fields"], [])
        self.assertEqual(parsed["metrics"]["solver_name"], "lambdatwist_p3p")
        self.assertEqual(parsed["metrics"]["num_cases"], 1000)
        self.assertEqual(parsed["metrics"]["correctness_passed"], True)

    def test_extra_unrelated_lines_are_ignored(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            """
            hello benchmark
            C:\\some\\path
            solver_name: lambdatwist_p3p
            num_cases: 5
            success_rate: 0.99
            mean_best_reprojection_error: 1e-12
            max_best_reprojection_error: 2e-12
            runtime_ns_total_median: 10
            runtime_ns_per_case_median: 2
            correctness_passed: TRUE
            done
            """
        )

        self.assertTrue(parsed["parse_success"])
        self.assertEqual(parsed["metrics"]["success_rate"], 0.99)
        self.assertIs(parsed["metrics"]["correctness_passed"], True)

    def test_scientific_notation_floats(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            """
            solver_name: lambdatwist_p3p
            num_cases: 1
            success_rate: 1e+0
            mean_best_reprojection_error: 7.63051755092e-14
            max_best_reprojection_error: 1.09586485003e-12
            runtime_ns_total_median: 3.267385e+07
            runtime_ns_per_case_median: 3.267385e+04
            correctness_passed: false
            """
        )

        self.assertTrue(parsed["parse_success"])
        self.assertEqual(parsed["metrics"]["success_rate"], 1.0)
        self.assertIs(parsed["metrics"]["correctness_passed"], False)

    def test_boolean_parsing_is_case_insensitive(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            """
            solver_name: lambdatwist_p3p
            num_cases: 1
            success_rate: 1
            mean_best_reprojection_error: 0
            max_best_reprojection_error: 0
            runtime_ns_total_median: 1
            runtime_ns_per_case_median: 1
            correctness_passed: FALSE
            """
        )

        self.assertTrue(parsed["parse_success"])
        self.assertIs(parsed["metrics"]["correctness_passed"], False)

    def test_missing_required_fields(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            """
            solver_name: lambdatwist_p3p
            success_rate: 1.0
            correctness_passed: true
            """
        )

        self.assertFalse(parsed["parse_success"])
        self.assertIn("num_cases", parsed["missing_fields"])
        self.assertIn("runtime_ns_per_case_median", parsed["missing_fields"])
        self.assertEqual(parsed["metrics"]["solver_name"], "lambdatwist_p3p")

    def test_valid_cases_and_total_solutions_parsed_when_present(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            "\n".join(
                [
                    "solver_name: lambdatwist_p3p",
                    "num_cases: 1000",
                    "valid_cases: 1000",
                    "total_solutions: 3000",
                    "success_rate: 1.0",
                    "mean_best_reprojection_error: 1.0e-12",
                    "max_best_reprojection_error: 2.0e-12",
                    "runtime_ns_total_median: 1234567",
                    "runtime_ns_per_case_median: 1234.567",
                    "correctness_passed: true",
                ]
            )
        )

        self.assertTrue(parsed["parse_success"])
        self.assertEqual(parsed["metrics"]["valid_cases"], 1000)
        self.assertEqual(parsed["metrics"]["total_solutions"], 3000)
        self.assertIsInstance(parsed["metrics"]["valid_cases"], int)
        self.assertIsInstance(parsed["metrics"]["total_solutions"], int)

    def test_valid_cases_and_total_solutions_missing_still_parses(self) -> None:
        parsed = parse_absolute_pose_benchmark_output(
            "\n".join(
                [
                    "solver_name: lambdatwist_p3p",
                    "num_cases: 1000",
                    "success_rate: 1.0",
                    "mean_best_reprojection_error: 1.0e-12",
                    "max_best_reprojection_error: 2.0e-12",
                    "runtime_ns_total_median: 1234567",
                    "runtime_ns_per_case_median: 1234.567",
                    "correctness_passed: true",
                ]
            )
        )

        self.assertTrue(parsed["parse_success"])
        self.assertNotIn("valid_cases", parsed["metrics"])
        self.assertNotIn("total_solutions", parsed["metrics"])


if __name__ == "__main__":
    unittest.main()
