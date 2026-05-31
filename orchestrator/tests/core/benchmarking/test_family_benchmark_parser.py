from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import unittest

from orchestrator.core.benchmarking.family_benchmark_parser import (
    parse_poselib_native_benchmark_output,
)


class PoseLibNativeBenchmarkParserTests(unittest.TestCase):
    def test_prefixed_json_output_maps_to_common_metrics(self) -> None:
        parsed = parse_poselib_native_benchmark_output(
            'progress\nPOSELIB_BENCHMARK_JSON={"solver_key":"p3p","benchmark_kind":"absolute_pose",'
            '"instances":100,"solutions_total":200,"solutions_per_problem":2.0,'
            '"valid_solutions":200,"valid_solutions_percent":100.0,'
            '"gt_found":100,"gt_found_percent":100.0,'
            '"runtime_ns_total_median":5000,"runtime_ns_per_problem_median":50.0,'
            '"tolerance":1e-6,"correctness_passed":true}\n'
        )

        self.assertTrue(parsed["parse_success"])
        self.assertEqual(parsed["metrics"]["solver_name"], "p3p")
        self.assertEqual(parsed["metrics"]["solver_key"], "p3p")
        self.assertEqual(parsed["metrics"]["benchmark_kind"], "absolute_pose")
        self.assertEqual(parsed["metrics"]["num_problems"], 100)
        self.assertEqual(parsed["metrics"]["total_solutions"], 200)
        self.assertEqual(parsed["metrics"]["parsed_runtime_ns_per_problem_median"], 50.0)
        self.assertIs(parsed["metrics"]["correctness_passed"], True)

    def test_low_gt_found_does_not_override_cpp_correctness_flag(self) -> None:
        parsed = parse_poselib_native_benchmark_output(
            'POSELIB_BENCHMARK_JSON={"solver_key":"p3p","benchmark_kind":"absolute_pose",'
            '"instances":100,"solutions_total":200,"solutions_per_problem":2.0,'
            '"valid_solutions":198,"valid_solutions_percent":99.0,'
            '"gt_found":98,"gt_found_percent":98.0,'
            '"runtime_ns_total_median":5000,"runtime_ns_per_problem_median":50.0,'
            '"tolerance":1e-6,"correctness_passed":true}'
        )

        self.assertTrue(parsed["parse_success"])
        self.assertIs(parsed["metrics"]["correctness_passed"], True)
        self.assertIs(parsed["metrics"]["parsed_correctness_passed"], True)

    def test_missing_cpp_correctness_flag_defaults_true_when_metrics_parse(self) -> None:
        parsed = parse_poselib_native_benchmark_output(
            'POSELIB_BENCHMARK_JSON={"solver_key":"p3p","benchmark_kind":"absolute_pose",'
            '"instances":100,"solutions_total":200,"solutions_per_problem":2.0,'
            '"valid_solutions":198,"valid_solutions_percent":99.0,'
            '"gt_found":50,"gt_found_percent":50.0,'
            '"runtime_ns_total_median":5000,"runtime_ns_per_problem_median":50.0,'
            '"tolerance":1e-6}'
        )

        self.assertTrue(parsed["parse_success"])
        self.assertIs(parsed["metrics"]["correctness_passed"], True)

    def test_malformed_poselib_json_fails(self) -> None:
        parsed = parse_poselib_native_benchmark_output(
            'POSELIB_BENCHMARK_JSON={"solver_key":"p3p",'
        )

        self.assertFalse(parsed["parse_success"])
        self.assertTrue(parsed["parse_errors"])


if __name__ == "__main__":
    unittest.main()
