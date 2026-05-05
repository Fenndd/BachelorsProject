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

    def test_matching_benchmark_options_passes(self) -> None:
        opts = {
            "num_cases": 1000,
            "points_per_case": 3,
            "warmup_iterations": 3,
            "timed_iterations": 10,
            "random_seed": 42,
            "reprojection_error_threshold": 1e-6,
            "min_success_rate": 0.99,
            "require_all_cases_valid": False,
            "use_max_reprojection_error_as_hard_gate": False,
            "runtime_unit": "ns",
            "build_type": "Release",
        }
        audit = audit_comparable_benchmark_pair(
            _loaded_artifact(benchmark_options=opts),
            _loaded_artifact(benchmark_options=opts),
        )

        self.assertTrue(audit["comparable"])
        self.assertTrue(audit["checks"]["same_benchmark_options"])

    def test_mismatched_benchmark_options_fails(self) -> None:
        opts_a = {
            "num_cases": 1000,
            "points_per_case": 3,
            "warmup_iterations": 3,
            "timed_iterations": 10,
            "random_seed": 42,
            "reprojection_error_threshold": 1e-6,
            "min_success_rate": 0.99,
            "require_all_cases_valid": False,
            "use_max_reprojection_error_as_hard_gate": False,
            "runtime_unit": "ns",
            "build_type": "Release",
        }
        opts_b = dict(opts_a)
        opts_b["num_cases"] = 500
        audit = audit_comparable_benchmark_pair(
            _loaded_artifact(benchmark_options=opts_a),
            _loaded_artifact(benchmark_options=opts_b),
        )

        self.assertFalse(audit["comparable"])
        self.assertFalse(audit["checks"]["same_benchmark_options"])
        self.assertIn("benchmark_options_mismatch", audit["failed_checks"])

    def test_matching_build_type_passes(self) -> None:
        audit = audit_comparable_benchmark_pair(
            _loaded_artifact(build_type="Release"),
            _loaded_artifact(build_type="Release"),
        )

        self.assertTrue(audit["comparable"])
        self.assertTrue(audit["checks"]["same_build_type"])

    def test_build_type_mismatch_fails_pair(self) -> None:
        audit = audit_comparable_benchmark_pair(
            _loaded_artifact(build_type="Release"),
            _loaded_artifact(build_type="Debug"),
        )

        self.assertFalse(audit["comparable"])
        self.assertFalse(audit["checks"]["same_build_type"])
        self.assertIn("build_type_mismatch", audit["failed_checks"])

    def test_missing_build_type_warns_backward_compatible(self) -> None:
        """Old artifacts without build_type should warn but not fail."""
        audit = audit_comparable_benchmark_pair(
            _loaded_artifact(),  # no build_type key
            _loaded_artifact(),  # no build_type key
        )

        self.assertTrue(audit["comparable"])
        self.assertIsNone(audit["checks"]["same_build_type"])
        self.assertIn("build_type_not_recorded", audit["warnings"])
        self.assertNotIn("build_type_mismatch", audit["failed_checks"])

    def test_one_sided_missing_build_type_warns(self) -> None:
        """If only baseline has build_type, warn but don't fail."""
        audit = audit_comparable_benchmark_pair(
            _loaded_artifact(build_type="Release"),
            _loaded_artifact(),  # no build_type
        )

        self.assertTrue(audit["comparable"])
        self.assertIsNone(audit["checks"]["same_build_type"])
        self.assertIn("build_type_not_recorded", audit["warnings"])


if __name__ == "__main__":
    unittest.main()
