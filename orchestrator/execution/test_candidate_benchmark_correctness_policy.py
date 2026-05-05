"""Tests for candidate benchmark correctness-check artifact policy."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator.benchmarking import parse_absolute_pose_benchmark_output
from orchestrator.execution.candidate_benchmark_verification import (
    BENCHMARK_CORRECTNESS_CHECK_STEP,
    _benchmark_from_parse,
    _build_benchmark_correctness_error_message,
    _complete_steps,
    _finalize,
    _step_status,
)


def _incorrect_benchmark_output() -> str:
    return "\n".join(
        [
            "solver_name: lambdatwist_p3p",
            "num_cases: 1000",
            "success_rate: 0.5",
            "mean_best_reprojection_error: 1e-3",
            "max_best_reprojection_error: 2e-3",
            "runtime_ns_total_median: 1000000",
            "runtime_ns_per_case_median: 1000",
            "correctness_passed: false",
        ]
    )


class CandidateBenchmarkCorrectnessPolicyTests(unittest.TestCase):
    def test_parse_success_correctness_false_fails_but_preserves_metrics(self) -> None:
        parse_result = parse_absolute_pose_benchmark_output(_incorrect_benchmark_output())
        benchmark = _benchmark_from_parse(_incorrect_benchmark_output(), parse_result, "Release")
        steps = [
            _step_status("run_absolute_pose_lambdatwist_benchmark", "success", 0, 0.1),
            _step_status("parse_absolute_pose_lambdatwist_benchmark", "success", None, 0.1),
            _step_status(BENCHMARK_CORRECTNESS_CHECK_STEP, "failed", None, 0.1),
        ]

        self.assertTrue(benchmark["parse_success"])
        self.assertIs(benchmark["parsed_correctness_passed"], False)
        self.assertEqual(benchmark["parsed_runtime_ns_per_case_median"], 1000.0)
        error_message = _build_benchmark_correctness_error_message(benchmark)
        self.assertIn("correctness_passed=false", error_message)
        completed = _complete_steps(steps)
        step_by_name = {step["name"]: step for step in completed}
        self.assertEqual(step_by_name[BENCHMARK_CORRECTNESS_CHECK_STEP]["status"], "failed")

    def test_finalize_preserves_metrics_when_correctness_check_fails(self) -> None:
        parse_result = parse_absolute_pose_benchmark_output(_incorrect_benchmark_output())
        benchmark = _benchmark_from_parse(_incorrect_benchmark_output(), parse_result, "Release")
        error_message = _build_benchmark_correctness_error_message(benchmark)

        with tempfile.TemporaryDirectory() as tmpdir:
            candidate_run_dir = Path(tmpdir) / "candidate"
            logs_dir = candidate_run_dir / "verification_logs"
            candidate_run_dir.mkdir()
            logs_dir.mkdir()

            exit_code = _finalize(
                candidate_run_dir,
                "candidate",
                None,
                None,
                None,
                None,
                "Release",
                logs_dir,
                [
                    _step_status(
                        "parse_absolute_pose_lambdatwist_benchmark", "success", None, 0.1
                    ),
                    _step_status(BENCHMARK_CORRECTNESS_CHECK_STEP, "failed", None, 0.1),
                ],
                BENCHMARK_CORRECTNESS_CHECK_STEP,
                error_message,
                benchmark,
            )

            self.assertEqual(exit_code, 1)
            verification = __import__("json").loads(
                (candidate_run_dir / "verification.json").read_text(encoding="utf-8")
            )
            self.assertEqual(verification["overall_status"], "failed")
            self.assertEqual(
                verification["failed_step"], BENCHMARK_CORRECTNESS_CHECK_STEP
            )
            self.assertTrue(verification["benchmark"]["parse_success"])
            self.assertIs(verification["benchmark"]["parsed_correctness_passed"], False)
            self.assertEqual(
                verification["benchmark"]["parsed_runtime_ns_per_case_median"], 1000.0
            )


if __name__ == "__main__":
    unittest.main()