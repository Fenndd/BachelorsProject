"""Unit tests for benchmark artifact audit helpers."""

from __future__ import annotations

import unittest

from orchestrator.benchmarking.benchmark_artifact_audit import (
    audit_comparable_benchmark_pair,
    audit_single_benchmark_artifact,
)


def _loaded_artifact(**benchmark_overrides: object) -> dict[str, object]:
    benchmark = {
        "family": "absolute_pose_solvers",
        "solver": "lambdatwist_p3p",
        "runtime_unit": "ns",
        "parse_success": True,
        "parsed_num_cases": 1000,
        "parsed_success_rate": 1.0,
        "parsed_mean_best_reprojection_error": 1.0e-12,
        "parsed_max_best_reprojection_error": 2.0e-12,
        "parsed_runtime_ns_total_median": 1000000.0,
        "parsed_runtime_ns_per_case_median": 1000.0,
        "parsed_correctness_passed": True,
    }
    benchmark.update(benchmark_overrides)
    return {
        "artifact_exists": True,
        "benchmark_section_exists": True,
        "load_error": None,
        "benchmark": benchmark,
        "artifact_path": "artifact.json",
    }


class BenchmarkArtifactAuditTests(unittest.TestCase):
    def test_valid_single_artifact_passes(self) -> None:
        audit = audit_single_benchmark_artifact(_loaded_artifact(), "baseline")

        self.assertTrue(audit["passed"])
        self.assertEqual(audit["failed_checks"], [])

    def test_valid_pair_is_comparable(self) -> None:
        audit = audit_comparable_benchmark_pair(
            _loaded_artifact(),
            _loaded_artifact(parsed_runtime_ns_per_case_median=1200.0),
        )

        self.assertTrue(audit["comparable"])
        self.assertEqual(audit["overall_status"], "passed")
        self.assertTrue(audit["checks"]["same_family"])
        self.assertTrue(audit["checks"]["same_solver"])

    def test_num_case_mismatch_fails_pair_without_ranking(self) -> None:
        audit = audit_comparable_benchmark_pair(
            _loaded_artifact(),
            _loaded_artifact(parsed_num_cases=999),
        )

        self.assertFalse(audit["comparable"])
        self.assertIn("same_num_cases", audit["failed_checks"])

    def test_parse_failure_fails_single_artifact(self) -> None:
        audit = audit_single_benchmark_artifact(
            _loaded_artifact(parse_success=False),
            "candidate",
        )

        self.assertFalse(audit["passed"])
        self.assertIn("parse_success_not_true", audit["failed_checks"])

    def test_missing_options_warns_without_failing_pair(self) -> None:
        audit = audit_comparable_benchmark_pair(_loaded_artifact(), _loaded_artifact())

        self.assertTrue(audit["comparable"])
        self.assertIn("benchmark_options_not_recorded", audit["warnings"])


if __name__ == "__main__":
    unittest.main()
