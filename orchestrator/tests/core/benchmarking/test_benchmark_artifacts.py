"""Tests for benchmark artifact builders."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import unittest

from orchestrator.core.benchmarking.benchmark_artifacts import (
    benchmark_artifact_from_parse,
    benchmark_required_fields,
    build_benchmark_correctness_error_message,
    empty_benchmark_artifact,
)
from orchestrator.core.benchmarking.family_benchmark_parser import parse_absolute_pose_benchmark_output
from orchestrator.core.benchmarking.solver_registry import default_solver_descriptor


_DESCRIPTOR = default_solver_descriptor()


def _valid_benchmark_output() -> str:
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
            "runtime_ns_total_median: 1000000",
            "runtime_ns_per_problem_median: 1000",
            "tolerance: 1e-6",
            "camera_fov: 75",
            "n_point_point: 3",
            "n_point_line: 0",
            "timed_iterations: 10",
            "runtime_unit: ns",
            "correctness_passed: true",
        ]
    )


class BenchmarkRequiredFieldsTests(unittest.TestCase):
    def test_returns_required_fields(self) -> None:
        fields = benchmark_required_fields()
        self.assertIn("solver_name", fields)
        self.assertIn("num_problems", fields)
        self.assertIn("correctness_passed", fields)
        self.assertEqual(len(fields), 11)


class EmptyBenchmarkArtifactTests(unittest.TestCase):
    def test_uses_descriptor_fields(self) -> None:
        artifact = empty_benchmark_artifact(_DESCRIPTOR, build_type="Release")
        self.assertEqual(artifact["family"], "absolute_pose_solvers")
        self.assertEqual(artifact["solver"], "lambdatwist_p3p")
        self.assertEqual(artifact["runtime_unit"], "ns")
        self.assertEqual(artifact["build_type"], "Release")
        self.assertFalse(artifact["parse_success"])
        self.assertFalse(artifact["raw_output_available"])
        self.assertEqual(len(artifact["missing_fields"]), 11)
        self.assertIsNone(artifact["parsed_solver_name"])
        self.assertIsNone(artifact["benchmark_options"])

    def test_raw_output_available_flag(self) -> None:
        artifact = empty_benchmark_artifact(_DESCRIPTOR, raw_output_available=True)
        self.assertTrue(artifact["raw_output_available"])

    def test_default_build_type(self) -> None:
        artifact = empty_benchmark_artifact(_DESCRIPTOR)
        self.assertEqual(artifact["build_type"], "Release")


class BenchmarkArtifactFromParseTests(unittest.TestCase):
    def test_builds_complete_artifact(self) -> None:
        stdout = _valid_benchmark_output()
        parse_result = parse_absolute_pose_benchmark_output(stdout)
        artifact = benchmark_artifact_from_parse(parse_result, _DESCRIPTOR, "Release")

        self.assertEqual(artifact["family"], "absolute_pose_solvers")
        self.assertEqual(artifact["solver"], "lambdatwist_p3p")
        self.assertEqual(artifact["runtime_unit"], "ns")
        self.assertEqual(artifact["build_type"], "Release")
        self.assertTrue(artifact["parse_success"])
        self.assertTrue(artifact["raw_output_available"])
        self.assertEqual(artifact["parsed_solver_name"], "lambdatwist_p3p")
        self.assertEqual(artifact["parsed_num_problems"], 1000)
        self.assertEqual(artifact["parsed_runtime_ns_per_problem_median"], 1000.0)
        self.assertTrue(artifact["parsed_correctness_passed"])

    def test_benchmark_options_present(self) -> None:
        stdout = _valid_benchmark_output()
        parse_result = parse_absolute_pose_benchmark_output(stdout)
        artifact = benchmark_artifact_from_parse(parse_result, _DESCRIPTOR, "Release")
        options = artifact["benchmark_options"]
        self.assertIsNotNone(options)
        self.assertEqual(options["num_problems"], 1000)
        self.assertEqual(options["tolerance"], 1e-6)
        self.assertEqual(options["camera_fov"], 75.0)

    def test_parse_failure_preserves_errors(self) -> None:
        parse_result = parse_absolute_pose_benchmark_output("garbage output")
        artifact = benchmark_artifact_from_parse(parse_result, _DESCRIPTOR, "Release")
        self.assertFalse(artifact["parse_success"])
        self.assertTrue(len(artifact["missing_fields"]) > 0)


class BuildCorrectnessErrorMessageTests(unittest.TestCase):
    def test_includes_metrics(self) -> None:
        benchmark = {
            "parsed_gt_found_percent": 50.0,
            "parsed_valid_solutions_percent": 100.0,
            "parsed_runtime_ns_per_problem_median": 1000.0,
        }
        msg = build_benchmark_correctness_error_message(benchmark)
        self.assertIn("gt_found_percent=50.0", msg)
        self.assertIn("valid_solutions_percent=100.0", msg)
        self.assertIn("runtime_ns_per_problem_median=1000.0", msg)
        self.assertIn("correctness_passed=false", msg)


if __name__ == "__main__":
    unittest.main()
