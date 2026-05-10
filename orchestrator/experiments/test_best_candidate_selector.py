"""Unit tests for experiment-level multi-candidate best selector."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.experiments.best_candidate_selector import select_best_candidate


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


def _create_baseline(root: Path, **overrides: Any) -> Path:
    baseline_run = root / "baseline"
    baseline_run.mkdir()
    _write_json(baseline_run / "metrics.json", _benchmark_payload(**overrides))
    return baseline_run


def _create_candidate(root: Path, name: str, **overrides: Any) -> Path:
    candidate_run = root / name
    candidate_run.mkdir()
    _write_json(candidate_run / "verification.json", _benchmark_payload(**overrides))
    return candidate_run


class BestCandidateSelectorTests(unittest.TestCase):
    def test_no_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root)

            result = select_best_candidate(baseline, [])

            self.assertEqual(result["overall_status"], "no_candidates")
            self.assertEqual(result["counts"]["total"], 0)
            self.assertIsNone(result["best_candidate_run_dir"])
            self.assertEqual(result["decisions"], [])

    def test_all_candidates_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root)
            candidate_a = _create_candidate(root, "candidate_a", parsed_correctness_passed=False)
            candidate_b = _create_candidate(root, "candidate_b", parsed_success_rate=0.98)

            result = select_best_candidate(baseline, [candidate_a, candidate_b])

            self.assertEqual(result["overall_status"], "all_candidates_rejected")
            self.assertEqual(result["counts"]["total"], 2)
            self.assertEqual(result["counts"]["rejected"], 2)
            self.assertEqual(result["counts"]["valid_not_improved"], 0)
            self.assertEqual(result["counts"]["accepted_improvement"], 0)
            self.assertIsNone(result["best_candidate_run_dir"])

    def test_only_valid_not_improved_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate_a = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=999.0,
            )
            candidate_b = _create_candidate(
                root,
                "candidate_b",
                parsed_runtime_ns_per_case_median=1300.0,
            )

            result = select_best_candidate(baseline, [candidate_a, candidate_b])

            self.assertEqual(result["overall_status"], "no_improvement_found")
            self.assertEqual(result["counts"]["rejected"], 0)
            self.assertEqual(result["counts"]["valid_not_improved"], 2)
            self.assertEqual(result["counts"]["accepted_improvement"], 0)
            self.assertIsNone(result["best_candidate_run_dir"])
            below_threshold = result["decisions"][0]
            self.assertEqual(below_threshold["status"], "valid_not_improved")
            self.assertEqual(below_threshold["rejection_reasons"], [])
            self.assertIn(
                "runtime_improvement_below_minimum_threshold",
                below_threshold["non_acceptance_reasons"],
            )

    def test_one_accepted_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=800.0,
            )

            result = select_best_candidate(baseline, [candidate])

            self.assertEqual(result["overall_status"], "best_candidate_found")
            self.assertEqual(result["counts"]["accepted_improvement"], 1)
            self.assertEqual(result["best_candidate_run_dir"], str(candidate))
            self.assertAlmostEqual(result["best_metrics"]["runtime_ns_per_case_median"], 800.0)
            self.assertAlmostEqual(result["best_metrics"]["speedup"], 1.25)
            self.assertAlmostEqual(result["best_metrics"]["runtime_reduction_percent"], 20.0)

    def test_multiple_accepted_selects_lowest_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate_a = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=900.0,
            )
            candidate_b = _create_candidate(
                root,
                "candidate_b",
                parsed_runtime_ns_per_case_median=850.0,
            )

            result = select_best_candidate(baseline, [candidate_a, candidate_b])

            self.assertEqual(result["overall_status"], "best_candidate_found")
            self.assertEqual(result["best_candidate_run_dir"], str(candidate_b))

    def test_tie_breaker_higher_success_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate_a = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=800.0,
                parsed_success_rate=0.995,
            )
            candidate_b = _create_candidate(
                root,
                "candidate_b",
                parsed_runtime_ns_per_case_median=800.0,
                parsed_success_rate=1.0,
            )

            result = select_best_candidate(baseline, [candidate_a, candidate_b])

            self.assertEqual(result["best_candidate_run_dir"], str(candidate_b))

    def test_tie_breaker_lower_mean_reprojection_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate_a = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=800.0,
                parsed_success_rate=1.0,
                parsed_mean_best_reprojection_error=1.00e-12,
            )
            candidate_b = _create_candidate(
                root,
                "candidate_b",
                parsed_runtime_ns_per_case_median=800.0,
                parsed_success_rate=1.0,
                parsed_mean_best_reprojection_error=0.95e-12,
            )

            result = select_best_candidate(baseline, [candidate_a, candidate_b])

            self.assertEqual(result["best_candidate_run_dir"], str(candidate_b))

    def test_tie_breaker_lower_max_reprojection_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate_a = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=800.0,
                parsed_success_rate=1.0,
                parsed_mean_best_reprojection_error=1.0e-12,
                parsed_max_best_reprojection_error=2.0e-12,
            )
            candidate_b = _create_candidate(
                root,
                "candidate_b",
                parsed_runtime_ns_per_case_median=800.0,
                parsed_success_rate=1.0,
                parsed_mean_best_reprojection_error=1.0e-12,
                parsed_max_best_reprojection_error=1.8e-12,
            )

            result = select_best_candidate(baseline, [candidate_a, candidate_b])

            self.assertEqual(result["best_candidate_run_dir"], str(candidate_b))

    def test_writes_candidate_decisions_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=800.0,
            )

            result = select_best_candidate(baseline, [candidate])

            decision_path = candidate / "candidate_decision.json"
            self.assertTrue(decision_path.exists())
            self.assertEqual(result["decisions"][0]["candidate_decision_path"], str(decision_path))
            self.assertEqual(result["best_candidate_decision_path"], str(decision_path))

    def test_can_disable_candidate_decision_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=800.0,
            )

            result = select_best_candidate(
                baseline,
                [candidate],
                write_candidate_decisions=False,
            )

            self.assertFalse((candidate / "candidate_decision.json").exists())
            self.assertIsNone(result["decisions"][0]["candidate_decision_path"])
            self.assertIsNone(result["best_candidate_decision_path"])

    def test_missing_candidate_directory_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root)

            missing = root / "nonexistent_candidate"
            # Do not create the directory

            result = select_best_candidate(baseline, [missing])

            self.assertEqual(result["overall_status"], "all_candidates_rejected")
            self.assertEqual(result["counts"]["total"], 1)
            self.assertEqual(result["counts"]["rejected"], 1)
            self.assertIsNone(result["best_candidate_run_dir"])
            self.assertIsNone(result["best_candidate_decision_path"])
            # candidate_decision_path should be null for missing directory
            self.assertIsNone(result["decisions"][0]["candidate_decision_path"])

    def test_deterministic_tie_breaker_earlier_input_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate_a = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=800.0,
                parsed_success_rate=1.0,
                parsed_mean_best_reprojection_error=1.0e-12,
                parsed_max_best_reprojection_error=2.0e-12,
            )
            candidate_b = _create_candidate(
                root,
                "candidate_b",
                parsed_runtime_ns_per_case_median=800.0,
                parsed_success_rate=1.0,
                parsed_mean_best_reprojection_error=1.0e-12,
                parsed_max_best_reprojection_error=2.0e-12,
            )

            result = select_best_candidate(baseline, [candidate_a, candidate_b])

            self.assertEqual(result["best_candidate_run_dir"], str(candidate_a))


if __name__ == "__main__":
    unittest.main()
