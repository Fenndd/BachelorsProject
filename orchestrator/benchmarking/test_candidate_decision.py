"""Unit tests for pairwise baseline-vs-candidate decision logic."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.benchmarking.candidate_decision import (
    evaluate_candidate_against_baseline,
)


def _benchmark_payload(**overrides: Any) -> dict[str, Any]:
    benchmark = {
        "family": "absolute_pose_solvers",
        "solver": "lambdatwist_p3p",
        "runtime_unit": "ns",
        "build_type": "Release",
        "benchmark_options": {
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
        },
        "parse_success": True,
        "parsed_num_cases": 1000,
        "parsed_success_rate": 1.0,
        "parsed_mean_best_reprojection_error": 1.0e-12,
        "parsed_max_best_reprojection_error": 2.0e-12,
        "parsed_runtime_ns_total_median": 1_000_000.0,
        "parsed_runtime_ns_per_case_median": 1000.0,
        "parsed_correctness_passed": True,
    }
    benchmark.update(overrides)
    return {"benchmark": benchmark}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _evaluate(
    baseline_overrides: dict[str, Any] | None = None,
    candidate_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline_overrides = baseline_overrides or {}
    candidate_overrides = candidate_overrides or {}

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        baseline_run = root / "baseline"
        candidate_run = root / "candidate"
        baseline_run.mkdir()
        candidate_run.mkdir()

        _write_json(
            baseline_run / "metrics.json",
            _benchmark_payload(**baseline_overrides),
        )
        _write_json(
            candidate_run / "verification.json",
            _benchmark_payload(**candidate_overrides),
        )

        return evaluate_candidate_against_baseline(
            baseline_run,
            candidate_run,
        )


class CandidateDecisionTests(unittest.TestCase):
    def test_audit_failure_leads_to_rejected(self) -> None:
        decision = _evaluate(
            candidate_overrides={
                "family": "other_family",
                "solver": "other_solver",
                "build_type": "Debug",
                "parsed_num_cases": 999,
            }
        )

        self.assertEqual(decision["status"], "rejected")
        self.assertFalse(decision["audit"]["comparable"])
        self.assertIn("same_family", decision["audit"]["failed_checks"])
        self.assertIn("same_solver", decision["audit"]["failed_checks"])
        self.assertIn("same_num_cases", decision["audit"]["failed_checks"])
        self.assertIn("build_type_mismatch", decision["audit"]["failed_checks"])
        self.assertIn("audit_not_comparable", decision["rejection_reasons"])
        self.assertIsNone(decision["comparison"]["speedup"])
        self.assertIsNone(decision["comparison"]["runtime_reduction_percent"])

    def test_correctness_false_leads_to_rejected(self) -> None:
        decision = _evaluate(candidate_overrides={"parsed_correctness_passed": False})

        self.assertEqual(decision["status"], "rejected")
        self.assertTrue(decision["audit"]["comparable"])
        self.assertIn("candidate_correctness_not_true", decision["rejection_reasons"])
        self.assertIsNone(decision["comparison"]["speedup"])
        self.assertIsNone(decision["comparison"]["runtime_reduction_percent"])

    def test_slower_correct_candidate_is_valid_not_improved(self) -> None:
        decision = _evaluate(
            baseline_overrides={"parsed_runtime_ns_per_case_median": 1000.0},
            candidate_overrides={"parsed_runtime_ns_per_case_median": 1200.0},
        )

        self.assertEqual(decision["status"], "valid_not_improved")
        self.assertEqual(decision["rejection_reasons"], [])
        self.assertFalse(decision["comparison"]["candidate_runtime_lower"])
        self.assertAlmostEqual(decision["comparison"]["speedup"], 1000.0 / 1200.0)
        self.assertAlmostEqual(
            decision["comparison"]["runtime_reduction_percent"],
            ((1000.0 - 1200.0) / 1000.0) * 100.0,
        )

    def test_faster_correct_candidate_is_accepted_improvement(self) -> None:
        decision = _evaluate(
            baseline_overrides={"parsed_runtime_ns_per_case_median": 1000.0},
            candidate_overrides={"parsed_runtime_ns_per_case_median": 800.0},
        )

        self.assertEqual(decision["status"], "accepted_improvement")
        self.assertEqual(decision["rejection_reasons"], [])
        self.assertTrue(decision["comparison"]["candidate_runtime_lower"])
        self.assertAlmostEqual(decision["comparison"]["speedup"], 1.25)
        self.assertAlmostEqual(decision["comparison"]["runtime_reduction_percent"], 20.0)

    def test_success_rate_drop_leads_to_rejected(self) -> None:
        decision = _evaluate(candidate_overrides={"parsed_success_rate": 0.98})

        self.assertEqual(decision["status"], "rejected")
        self.assertTrue(
            any(
                reason.startswith("candidate_success_rate_below_minimum")
                for reason in decision["rejection_reasons"]
            )
        )
        self.assertIsNone(decision["comparison"]["speedup"])
        self.assertIsNone(decision["comparison"]["runtime_reduction_percent"])

    def test_reprojection_error_tolerance_violation_leads_to_rejected(self) -> None:
        decision = _evaluate(
            candidate_overrides={
                "parsed_mean_best_reprojection_error": 2.0e-12,
                "parsed_max_best_reprojection_error": 3.0e-12,
            }
        )

        self.assertEqual(decision["status"], "rejected")
        self.assertTrue(
            any(
                reason.startswith("candidate_mean_reprojection_error_exceeds_limit")
                for reason in decision["rejection_reasons"]
            )
        )
        self.assertTrue(
            any(
                reason.startswith("candidate_max_reprojection_error_exceeds_limit")
                for reason in decision["rejection_reasons"]
            )
        )
        self.assertIsNone(decision["comparison"]["speedup"])
        self.assertIsNone(decision["comparison"]["runtime_reduction_percent"])


if __name__ == "__main__":
    unittest.main()