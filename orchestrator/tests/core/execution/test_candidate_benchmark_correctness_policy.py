"""Tests for candidate benchmark correctness-check artifact policy."""

from __future__ import annotations

import pytest
import tempfile

pytestmark = pytest.mark.unit
import unittest
from pathlib import Path

from orchestrator.core.benchmarking import parse_absolute_pose_benchmark_output
from orchestrator.core.benchmarking.benchmark_artifacts import (
    benchmark_artifact_from_parse,
    build_benchmark_correctness_error_message,
    empty_benchmark_artifact,
)
from orchestrator.core.benchmarking.solver_registry import default_solver_descriptor
from orchestrator.core.execution.candidate_benchmark_verification import (
    BENCHMARK_CORRECTNESS_CHECK_STEP,
    _complete_steps,
    _finalize,
    _path_length_diagnostics,
    _step_status,
)

_DESCRIPTOR = default_solver_descriptor()


def _incorrect_benchmark_output() -> str:
    return "\n".join(
        [
            "solver_name: lambdatwist_p3p",
            "num_problems: 1000",
            "total_solutions: 3000",
            "solutions_per_problem: 3.0",
            "valid_solutions: 3000",
            "valid_solutions_percent: 100.0",
            "gt_found: 500",
            "gt_found_percent: 50.0",
            "runtime_ns_total_median: 1000000",
            "runtime_ns_per_problem_median: 1000",
            "tolerance: 1e-6",
            "camera_fov: 75",
            "n_point_point: 3",
            "n_point_line: 0",
            "timed_iterations: 10",
            "runtime_unit: ns",
            "correctness_passed: false",
        ]
    )


class CandidateBenchmarkCorrectnessPolicyTests(unittest.TestCase):
    def test_parse_success_correctness_false_fails_but_preserves_metrics(self) -> None:
        parse_result = parse_absolute_pose_benchmark_output(_incorrect_benchmark_output())
        benchmark = benchmark_artifact_from_parse(parse_result, _DESCRIPTOR, "Release")
        steps = [
            _step_status("run_absolute_pose_lambdatwist_benchmark", "success", 0, 0.1),
            _step_status("parse_absolute_pose_lambdatwist_benchmark", "success", None, 0.1),
            _step_status(BENCHMARK_CORRECTNESS_CHECK_STEP, "failed", None, 0.1),
        ]

        self.assertTrue(benchmark["parse_success"])
        self.assertIs(benchmark["parsed_correctness_passed"], False)
        self.assertEqual(benchmark["parsed_runtime_ns_per_problem_median"], 1000.0)
        error_message = build_benchmark_correctness_error_message(benchmark)
        self.assertIn("gt_found_percent=50.0", error_message)
        completed = _complete_steps(steps)
        step_by_name = {step["name"]: step for step in completed}
        self.assertEqual(step_by_name[BENCHMARK_CORRECTNESS_CHECK_STEP]["status"], "failed")

    def test_finalize_preserves_metrics_when_correctness_check_fails(self) -> None:
        parse_result = parse_absolute_pose_benchmark_output(_incorrect_benchmark_output())
        benchmark = benchmark_artifact_from_parse(parse_result, _DESCRIPTOR, "Release")
        error_message = build_benchmark_correctness_error_message(benchmark)

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
                verification["benchmark"]["parsed_runtime_ns_per_problem_median"], 1000.0
            )

    def test_path_length_diagnostics_are_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / ("s" * 80)
            nested = source_dir / ("nested" * 20)
            nested.mkdir(parents=True)
            (nested / ("candidate" * 20 + ".cpp")).write_text("int main() { return 0; }\n", encoding="utf-8")
            build_dir = source_dir / "build"
            candidate_run_dir = root / "candidate"
            logs_dir = candidate_run_dir / "verification_logs"
            candidate_run_dir.mkdir()
            logs_dir.mkdir()

            diagnostics = _path_length_diagnostics(source_dir, build_dir)
            exit_code = _finalize(
                candidate_run_dir,
                "candidate",
                root,
                source_dir,
                build_dir,
                None,
                "Release",
                logs_dir,
                [],
                None,
                None,
                empty_benchmark_artifact(_DESCRIPTOR, build_type="Release"),
                diagnostics,
            )

            self.assertEqual(exit_code, 0)
            verification = __import__("json").loads(
                (candidate_run_dir / "verification.json").read_text(encoding="utf-8")
            )
            self.assertIs(verification["diagnostics"]["path_length"]["warning"], True)
            self.assertEqual(verification["overall_status"], "success")
            summary = (candidate_run_dir / "verification_summary.txt").read_text(encoding="utf-8")
            self.assertIn("path length warning", summary)


if __name__ == "__main__":
    unittest.main()
