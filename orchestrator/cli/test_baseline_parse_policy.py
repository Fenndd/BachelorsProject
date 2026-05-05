"""Tests for baseline family benchmark parse-failure policy."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator.cli.main import (
    BENCHMARK_CORRECTNESS_CHECK_STEP,
    PARSE_FAMILY_BENCHMARK_STEP,
    _benchmark_parse_result_from_output,
    _build_benchmark_correctness_error_message,
    _build_index_record,
    _build_metrics,
    _build_status,
    _build_summary,
)


def _step(name: str, status: str) -> dict[str, object]:
    return {
        "name": name,
        "status": status,
        "exit_code": 0 if status == "success" else None,
        "duration_seconds": 0.001,
    }


def _successful_steps() -> list[dict[str, object]]:
    return [
        _step("configure_cmake", "success"),
        _step("build_baseline_smoke_test", "success"),
        _step("build_baseline_runner", "success"),
        _step("build_absolute_pose_lambdatwist_adapter_validator", "success"),
        _step("build_absolute_pose_lambdatwist_benchmark", "success"),
        _step("run_baseline_smoke_test", "success"),
        _step("run_baseline_runner", "success"),
        _step("run_absolute_pose_lambdatwist_adapter_validator", "success"),
        _step("run_absolute_pose_lambdatwist_benchmark", "success"),
    ]


def _metadata() -> dict[str, object]:
    return {
        "run_id": "test_baseline",
        "scenario": "baseline",
        "case_study": "p3p_solver",
        "baseline": "lambda_twist",
        "started_at": "2026-05-05T00:00:00+02:00",
        "finished_at": "2026-05-05T00:00:01+02:00",
        "repository": {
            "git_commit": "abc123",
            "git_branch": "main",
            "dirty_worktree": False,
        },
    }


class BaselineParsePolicyTests(unittest.TestCase):
    def test_parse_success_keeps_status_success(self) -> None:
        parse_result = _benchmark_parse_result_from_output(
            "\n".join(
                [
                    "solver_name: lambdatwist_p3p",
                    "num_cases: 1000",
                    "success_rate: 1.0",
                    "mean_best_reprojection_error: 1e-12",
                    "max_best_reprojection_error: 2e-12",
                    "runtime_ns_total_median: 1000000",
                    "runtime_ns_per_case_median: 1000",
                    "correctness_passed: true",
                ]
            )
        )
        steps = [*_successful_steps(), _step(PARSE_FAMILY_BENCHMARK_STEP, "success")]

        status = _build_status(steps, None, None)
        metrics = _build_metrics(steps, "Release", parse_result)

        self.assertEqual(status["overall_status"], "success")
        self.assertIsNone(status["failed_step"])
        self.assertTrue(metrics["benchmark"]["parse_success"])
        self.assertEqual(metrics["benchmark"]["parsed_runtime_ns_per_case_median"], 1000.0)
        self.assertTrue(metrics["benchmark"]["parsed_correctness_passed"])

    def test_parse_success_correctness_false_fails_but_preserves_metrics(self) -> None:
        parse_result = _benchmark_parse_result_from_output(
            "\n".join(
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
        )
        steps = [
            *_successful_steps(),
            _step(PARSE_FAMILY_BENCHMARK_STEP, "success"),
            _step(BENCHMARK_CORRECTNESS_CHECK_STEP, "failed"),
        ]
        error_message = _build_benchmark_correctness_error_message(parse_result)

        status = _build_status(steps, BENCHMARK_CORRECTNESS_CHECK_STEP, error_message)
        metrics = _build_metrics(steps, "Release", parse_result)

        self.assertEqual(status["overall_status"], "failed")
        self.assertEqual(status["failed_step"], BENCHMARK_CORRECTNESS_CHECK_STEP)
        self.assertTrue(metrics["benchmark"]["parse_success"])
        self.assertIs(metrics["benchmark"]["parsed_correctness_passed"], False)
        self.assertEqual(metrics["benchmark"]["parsed_runtime_ns_per_case_median"], 1000.0)
        self.assertIn("correctness_passed=false", error_message)

    def test_correctness_failure_index_and_summary_preserve_metrics(self) -> None:
        parse_result = _benchmark_parse_result_from_output(
            "\n".join(
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
        )
        steps = [
            *_successful_steps(),
            _step(PARSE_FAMILY_BENCHMARK_STEP, "success"),
            _step(BENCHMARK_CORRECTNESS_CHECK_STEP, "failed"),
        ]
        status = _build_status(
            steps,
            BENCHMARK_CORRECTNESS_CHECK_STEP,
            _build_benchmark_correctness_error_message(parse_result),
        )
        metrics = _build_metrics(steps, "Release", parse_result)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "test_baseline"
            index_record = _build_index_record(
                _metadata(), status, metrics, run_dir, Path(tmpdir)
            )
            summary = _build_summary(run_dir, _metadata(), status, metrics, "Release")

        self.assertEqual(index_record["overall_status"], "failed")
        self.assertEqual(index_record["failed_step"], BENCHMARK_CORRECTNESS_CHECK_STEP)
        self.assertTrue(index_record["family_benchmark_parse_success"])
        self.assertIs(index_record["family_benchmark_correctness_passed"], False)
        self.assertEqual(index_record["family_benchmark_runtime_ns_per_case_median"], 1000.0)
        self.assertIn(f"Failed step: {BENCHMARK_CORRECTNESS_CHECK_STEP}", summary)
        self.assertIn("- correctness passed: false", summary)

    def test_parse_failure_fails_status_and_preserves_partial_metrics(self) -> None:
        parse_result = _benchmark_parse_result_from_output(
            "\n".join(
                [
                    "solver_name: lambdatwist_p3p",
                    "num_cases: 1000",
                    "success_rate: 1.0",
                ]
            )
        )
        steps = [*_successful_steps(), _step(PARSE_FAMILY_BENCHMARK_STEP, "failed")]
        error_message = "Could not parse family benchmark output."

        status = _build_status(steps, PARSE_FAMILY_BENCHMARK_STEP, error_message)
        metrics = _build_metrics(steps, "Release", parse_result)

        self.assertEqual(status["overall_status"], "failed")
        self.assertEqual(status["failed_step"], PARSE_FAMILY_BENCHMARK_STEP)
        self.assertFalse(metrics["benchmark"]["parse_success"])
        self.assertIn(
            "runtime_ns_per_case_median", metrics["benchmark"]["missing_fields"]
        )
        self.assertEqual(metrics["benchmark"]["parsed_solver_name"], "lambdatwist_p3p")
        self.assertEqual(metrics["benchmark"]["parsed_num_cases"], 1000)
        self.assertIsNone(metrics["benchmark"]["parsed_runtime_ns_per_case_median"])
        self.assertIsNone(metrics["benchmark"]["parsed_correctness_passed"])

    def test_parse_failure_index_and_summary_reflect_failed_run(self) -> None:
        parse_result = _benchmark_parse_result_from_output("solver_name: lambdatwist_p3p\n")
        steps = [*_successful_steps(), _step(PARSE_FAMILY_BENCHMARK_STEP, "failed")]
        error_message = "Could not parse family benchmark output."
        status = _build_status(steps, PARSE_FAMILY_BENCHMARK_STEP, error_message)
        metrics = _build_metrics(steps, "Release", parse_result)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "test_baseline"
            index_record = _build_index_record(
                _metadata(), status, metrics, run_dir, Path(tmpdir)
            )
            summary = _build_summary(run_dir, _metadata(), status, metrics, "Release")

        self.assertEqual(index_record["overall_status"], "failed")
        self.assertEqual(index_record["failed_step"], PARSE_FAMILY_BENCHMARK_STEP)
        self.assertFalse(index_record["family_benchmark_parse_success"])
        self.assertIsNone(index_record["family_benchmark_runtime_ns_per_case_median"])
        self.assertIsNone(index_record["family_benchmark_success_rate"])
        self.assertIsNone(index_record["family_benchmark_correctness_passed"])
        self.assertIn("Benchmark parse status: false", summary)
        self.assertIn(f"Failed step: {PARSE_FAMILY_BENCHMARK_STEP}", summary)
        self.assertIn("missing fields:", summary)

    def test_prior_benchmark_failure_skips_parse_step(self) -> None:
        steps = [
            _step("configure_cmake", "success"),
            _step("build_baseline_smoke_test", "success"),
            _step("build_baseline_runner", "success"),
            _step("build_absolute_pose_lambdatwist_adapter_validator", "success"),
            _step("build_absolute_pose_lambdatwist_benchmark", "failed"),
        ]

        status = _build_status(
            steps,
            "build_absolute_pose_lambdatwist_benchmark",
            "benchmark build failed",
        )
        step_by_name = {step["name"]: step for step in status["steps"]}

        self.assertEqual(
            status["failed_step"], "build_absolute_pose_lambdatwist_benchmark"
        )
        self.assertEqual(step_by_name[PARSE_FAMILY_BENCHMARK_STEP]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()