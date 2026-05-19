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
            "num_problems": 1000,
            "tolerance": 1e-6,
            "camera_fov": 75.0,
            "n_point_point": 3,
            "n_point_line": 0,
            "timed_iterations": 10,
            "runtime_unit": "ns",
            "build_type": "Release",
        },
        "parse_success": True,
        "parsed_num_problems": 1000,
        "parsed_total_solutions": 3000,
        "parsed_solutions_per_problem": 3.0,
        "parsed_valid_solutions": 3000,
        "parsed_valid_solutions_percent": 100.0,
        "parsed_gt_found": 1000,
        "parsed_gt_found_percent": 100.0,
        "parsed_runtime_ns_total_median": 1_000_000.0,
        "parsed_runtime_ns_per_problem_median": 1000.0,
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
            candidate = _create_candidate(root, "candidate", parsed_correctness_passed=False)

            result = select_best_candidate(baseline, [candidate])

            self.assertEqual(result["overall_status"], "all_candidates_rejected")
            self.assertEqual(result["counts"]["rejected"], 1)

    def test_selects_fastest_accepted_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_problem_median=1000.0)
            slower = _create_candidate(root, "slower", parsed_runtime_ns_per_problem_median=900.0)
            faster = _create_candidate(root, "faster", parsed_runtime_ns_per_problem_median=800.0)

            result = select_best_candidate(baseline, [slower, faster])

            self.assertEqual(result["overall_status"], "best_candidate_found")
            self.assertEqual(result["best_candidate_run_dir"], str(faster))
            self.assertAlmostEqual(
                result["best_metrics"]["runtime_ns_per_problem_median"], 800.0
            )

    def test_valid_not_improved_when_candidate_is_slower(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_problem_median=1000.0)
            candidate = _create_candidate(root, "candidate", parsed_runtime_ns_per_problem_median=1200.0)

            result = select_best_candidate(baseline, [candidate])

            self.assertEqual(result["overall_status"], "no_improvement_found")
            self.assertEqual(result["counts"]["valid_not_improved"], 1)

    def test_tie_breaker_prefers_higher_gt_found_percent_then_valid_percent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_problem_median=1000.0)
            candidate_a = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_problem_median=800.0,
                parsed_gt_found_percent=99.0,
                parsed_valid_solutions_percent=100.0,
            )
            candidate_b = _create_candidate(
                root,
                "candidate_b",
                parsed_runtime_ns_per_problem_median=800.0,
                parsed_gt_found_percent=100.0,
                parsed_valid_solutions_percent=99.0,
            )

            result = select_best_candidate(baseline, [candidate_a, candidate_b])

            self.assertEqual(result["best_candidate_run_dir"], str(candidate_b))

    def test_writes_candidate_decision_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_problem_median=1000.0)
            candidate = _create_candidate(root, "candidate", parsed_runtime_ns_per_problem_median=800.0)

            select_best_candidate(baseline, [candidate])

            self.assertTrue((candidate / "candidate_decision.json").exists())


if __name__ == "__main__":
    unittest.main()
