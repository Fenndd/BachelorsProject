"""Unit tests for pairwise baseline-vs-candidate decision logic."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.core.benchmarking.candidate_decision import (
    evaluate_candidate_against_baseline,
    evaluate_candidate_against_reference,
    write_candidate_decision,
)


from orchestrator.tests.conftest import write_json, make_benchmark_payload


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

        write_json(baseline_run / "metrics.json", make_benchmark_payload(**baseline_overrides))
        write_json(candidate_run / "verification.json", make_benchmark_payload(**candidate_overrides))

        return evaluate_candidate_against_baseline(baseline_run, candidate_run)


class CandidateDecisionTests(unittest.TestCase):
    def test_audit_failure_leads_to_rejected(self) -> None:
        decision = _evaluate(
            candidate_overrides={
                "family": "other_family",
                "solver": "other_solver",
                "build_type": "Debug",
                "parsed_num_problems": 999,
            }
        )

        self.assertEqual(decision["status"], "rejected")
        self.assertIn("audit_not_comparable", decision["rejection_reasons"])
        self.assertIn("audit_failed_check:same_num_problems", decision["rejection_reasons"])

    def test_candidate_correctness_false_rejected(self) -> None:
        decision = _evaluate(candidate_overrides={"parsed_correctness_passed": False})

        self.assertEqual(decision["status"], "rejected")
        self.assertIn("candidate_correctness_not_true", decision["rejection_reasons"])

    def test_slower_candidate_valid_not_improved(self) -> None:
        decision = _evaluate(
            baseline_overrides={"parsed_runtime_ns_per_problem_median": 1000.0},
            candidate_overrides={"parsed_runtime_ns_per_problem_median": 1200.0},
        )

        self.assertEqual(decision["status"], "valid_not_improved")
        self.assertFalse(decision["comparison"]["candidate_runtime_lower"])

    def test_small_runtime_improvement_below_threshold_is_valid_not_improved(self) -> None:
        decision = _evaluate(
            baseline_overrides={"parsed_runtime_ns_per_problem_median": 1000.0},
            candidate_overrides={"parsed_runtime_ns_per_problem_median": 999.0},
        )

        self.assertEqual(decision["status"], "valid_not_improved")
        self.assertIn(
            "runtime_improvement_below_minimum_threshold",
            decision["non_acceptance_reasons"],
        )

    def test_large_runtime_improvement_accepted(self) -> None:
        decision = _evaluate(
            baseline_overrides={"parsed_runtime_ns_per_problem_median": 1000.0},
            candidate_overrides={"parsed_runtime_ns_per_problem_median": 800.0},
        )

        self.assertEqual(decision["status"], "accepted_improvement")
        self.assertAlmostEqual(decision["comparison"]["speedup"], 1.25)

    def test_reference_kind_verified_candidate_loads_verification_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reference_run = root / "reference"
            candidate_run = root / "candidate"
            reference_run.mkdir()
            candidate_run.mkdir()
            write_json(reference_run / "verification.json", make_benchmark_payload())
            write_json(
                candidate_run / "verification.json",
                make_benchmark_payload(parsed_runtime_ns_per_problem_median=750.0),
            )

            decision = evaluate_candidate_against_reference(
                reference_run,
                candidate_run,
                reference_kind="verified_candidate",
            )

        self.assertEqual(decision["status"], "accepted_improvement")
        self.assertEqual(decision["reference_kind"], "verified_candidate")

    def test_write_candidate_decision_rejects_path_traversal_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                write_candidate_decision(Path(tmpdir), {"status": "ok"}, filename="../x.json")

    def test_metrics_summary_uses_new_metric_names(self) -> None:
        decision = _evaluate(
            candidate_overrides={"parsed_runtime_ns_per_problem_median": 800.0}
        )

        self.assertEqual(
            decision["candidate_metrics"]["runtime_ns_per_problem_median"], 800.0
        )
        self.assertEqual(decision["candidate_metrics"]["gt_found_percent"], 100.0)
        self.assertNotIn("runtime_ns_per_case_median", decision["candidate_metrics"])
        self.assertNotIn("mean_best_reprojection_error", decision["candidate_metrics"])


if __name__ == "__main__":
    unittest.main()
