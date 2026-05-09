"""Unit tests for pairwise baseline-vs-candidate decision logic."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.benchmarking.candidate_decision import (
    evaluate_candidate_against_baseline,
    evaluate_candidate_against_reference,
    write_candidate_decision,
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


def _make_run_pair(
    root: Path,
    *,
    reference_kind: str = "baseline",
    reference_overrides: dict[str, Any] | None = None,
    candidate_overrides: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    reference_overrides = reference_overrides or {}
    candidate_overrides = candidate_overrides or {}

    reference_run = root / "reference"
    candidate_run = root / "candidate"
    reference_run.mkdir()
    candidate_run.mkdir()

    reference_artifact_name = (
        "metrics.json" if reference_kind == "baseline" else "verification.json"
    )
    _write_json(
        reference_run / reference_artifact_name,
        _benchmark_payload(**reference_overrides),
    )
    _write_json(
        candidate_run / "verification.json",
        _benchmark_payload(**candidate_overrides),
    )
    return reference_run, candidate_run


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

    def test_baseline_wrapper_preserves_legacy_keys(self) -> None:
        decision = _evaluate(
            baseline_overrides={"parsed_runtime_ns_per_case_median": 1000.0},
            candidate_overrides={"parsed_runtime_ns_per_case_median": 800.0},
        )

        self.assertEqual(decision["reference_kind"], "baseline")
        self.assertIn("baseline_run_dir", decision)
        self.assertIn("baseline_metrics", decision)
        self.assertIn("candidate_run_dir", decision)
        self.assertIn("candidate_metrics", decision)
        self.assertIn("comparison", decision)
        self.assertIn("status", decision)
        self.assertIn("rejection_reasons", decision)
        self.assertEqual(decision["baseline_run_dir"], decision["reference_run_dir"])
        self.assertEqual(decision["baseline_metrics"], decision["reference_metrics"])
        self.assertIn("baseline", decision["audit"])

    def test_generic_reference_baseline_loads_metrics_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reference_run, candidate_run = _make_run_pair(
                Path(tmpdir),
                reference_kind="baseline",
                reference_overrides={"parsed_runtime_ns_per_case_median": 1000.0},
                candidate_overrides={"parsed_runtime_ns_per_case_median": 750.0},
            )

            decision = evaluate_candidate_against_reference(
                reference_run,
                candidate_run,
                reference_kind="baseline",
            )

            self.assertEqual(decision["status"], "accepted_improvement")
            self.assertEqual(decision["reference_kind"], "baseline")
            self.assertEqual(
                decision["audit"]["reference"]["normalized_artifact"]["source_artifact"],
                str(reference_run / "metrics.json"),
            )
            self.assertNotIn("baseline_metrics", decision)

    def test_generic_reference_verified_candidate_loads_verification_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reference_run, candidate_run = _make_run_pair(
                Path(tmpdir),
                reference_kind="verified_candidate",
                reference_overrides={"parsed_runtime_ns_per_case_median": 900.0},
                candidate_overrides={"parsed_runtime_ns_per_case_median": 700.0},
            )

            decision = evaluate_candidate_against_reference(
                reference_run,
                candidate_run,
                reference_kind="verified_candidate",
            )

            self.assertEqual(decision["status"], "accepted_improvement")
            self.assertEqual(decision["reference_kind"], "verified_candidate")
            self.assertEqual(
                decision["audit"]["reference"]["normalized_artifact"]["source_artifact"],
                str(reference_run / "verification.json"),
            )

    def test_generic_reference_valid_not_improved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reference_run, candidate_run = _make_run_pair(
                Path(tmpdir),
                reference_kind="verified_candidate",
                reference_overrides={"parsed_runtime_ns_per_case_median": 800.0},
                candidate_overrides={"parsed_runtime_ns_per_case_median": 850.0},
            )

            decision = evaluate_candidate_against_reference(
                reference_run,
                candidate_run,
                reference_kind="verified_candidate",
            )

            self.assertEqual(decision["status"], "valid_not_improved")
            self.assertFalse(decision["comparison"]["candidate_runtime_lower"])

    def test_generic_reference_correctness_false_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reference_run, candidate_run = _make_run_pair(
                Path(tmpdir),
                reference_kind="verified_candidate",
                candidate_overrides={"parsed_correctness_passed": False},
            )

            decision = evaluate_candidate_against_reference(
                reference_run,
                candidate_run,
                reference_kind="verified_candidate",
            )

            self.assertEqual(decision["status"], "rejected")
            self.assertIn("candidate_correctness_not_true", decision["rejection_reasons"])

    def test_generic_reference_not_comparable_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reference_run, candidate_run = _make_run_pair(
                Path(tmpdir),
                reference_kind="verified_candidate",
                candidate_overrides={"solver": "other_solver"},
            )

            decision = evaluate_candidate_against_reference(
                reference_run,
                candidate_run,
                reference_kind="verified_candidate",
            )

            self.assertEqual(decision["status"], "rejected")
            self.assertFalse(decision["audit"]["comparable"])
            self.assertIn("same_solver", decision["audit"]["failed_checks"])

    def test_invalid_reference_kind_rejected_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reference_run, candidate_run = _make_run_pair(Path(tmpdir))

            with self.assertRaisesRegex(ValueError, "invalid reference_kind"):
                evaluate_candidate_against_reference(
                    reference_run,
                    candidate_run,
                    reference_kind="current_best",
                )

    def test_decision_writer_default_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            candidate_run = Path(tmpdir) / "candidate"
            candidate_run.mkdir()

            output = write_candidate_decision(candidate_run, {"status": "ok"})

            self.assertEqual(output, candidate_run / "candidate_decision.json")
            self.assertTrue(output.exists())

    def test_decision_writer_custom_safe_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            candidate_run = Path(tmpdir) / "candidate"
            candidate_run.mkdir()

            output = write_candidate_decision(
                candidate_run,
                {"status": "ok"},
                filename="decision_vs_current_best.json",
            )

            self.assertEqual(output, candidate_run / "decision_vs_current_best.json")
            self.assertTrue(output.exists())

    def test_decision_writer_rejects_unsafe_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            candidate_run = Path(tmpdir) / "candidate"
            candidate_run.mkdir()

            with self.assertRaisesRegex(ValueError, "unsafe decision filename"):
                write_candidate_decision(candidate_run, {}, filename="../x.json")

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