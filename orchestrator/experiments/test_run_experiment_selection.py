"""Minimal tests for experiment-runner best candidate selection integration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.experiments.experiment_config import (
    ExperimentConfigError,
    load_experiment_config,
)
from orchestrator.experiments.run_experiment import _run_selection


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


def _base_config_payload(selection: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "experiment_name": "selection integration test",
        "target_file": "cpp/external/lambdatwist/p3p.cc",
        "pipeline": {
            "generate_candidate": True,
            "materialize_candidate": True,
            "verify_candidate": True,
        },
        "candidate_generation": {"max_source_chars": 1000},
        "llm_config": "configs/llm_mock_candidate.json",
        "iterations": 1,
    }
    if selection is not None:
        payload["selection"] = selection
    return payload


def _write_config(root: Path, selection: dict[str, Any] | None = None) -> Path:
    config_path = root / "experiment_config.json"
    _write_json(config_path, _base_config_payload(selection))
    return config_path


def _create_baseline(root: Path, **overrides: Any) -> Path:
    baseline = root / "baseline"
    baseline.mkdir()
    _write_json(baseline / "metrics.json", _benchmark_payload(**overrides))
    return baseline


def _create_candidate(
    root: Path,
    name: str,
    *,
    write_verification: bool = True,
    **overrides: Any,
) -> Path:
    candidate = root / name
    candidate.mkdir()
    if write_verification:
        _write_json(candidate / "verification.json", _benchmark_payload(**overrides))
    return candidate


def _record(candidate_run_dir: Path) -> dict[str, Any]:
    return {"candidate_run_dir": str(candidate_run_dir)}


class RunExperimentSelectionTests(unittest.TestCase):
    def test_selection_disabled_returns_no_artifact_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = load_experiment_config(_write_config(root))
            experiment_dir = root / "experiment"
            experiment_dir.mkdir()

            summary = _run_selection(experiment_dir, config, [])

            self.assertIsNone(summary)
            self.assertFalse((experiment_dir / "best_candidate_selection.json").exists())

    def test_selection_enabled_without_baseline_run_dir_is_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = _write_config(root, {"enabled": True})

            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(config_path)

            self.assertIn("selection.baseline_run_dir", str(ctx.exception))

    def test_selection_enabled_with_verified_candidate_creates_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root, parsed_runtime_ns_per_case_median=1000.0)
            candidate = _create_candidate(
                root,
                "candidate_a",
                parsed_runtime_ns_per_case_median=800.0,
            )
            config = load_experiment_config(
                _write_config(
                    root,
                    {
                        "enabled": True,
                        "baseline_run_dir": str(baseline),
                        "write_candidate_decisions": True,
                    },
                )
            )
            experiment_dir = root / "experiment"
            experiment_dir.mkdir()

            summary = _run_selection(experiment_dir, config, [_record(candidate)])
            selection_path = experiment_dir / "best_candidate_selection.json"
            selection = json.loads(selection_path.read_text(encoding="utf-8"))

            self.assertTrue(selection_path.exists())
            self.assertEqual(summary["overall_status"], "best_candidate_found")
            self.assertEqual(selection["best_candidate_run_dir"], str(candidate.resolve()))
            self.assertEqual(selection["counts"]["accepted_improvement"], 1)
            self.assertTrue((candidate / "candidate_decision.json").exists())

    def test_selection_enabled_includes_rejected_verified_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root)
            candidate = _create_candidate(
                root,
                "candidate_rejected",
                parsed_correctness_passed=False,
            )
            config = load_experiment_config(
                _write_config(
                    root,
                    {
                        "enabled": True,
                        "baseline_run_dir": str(baseline),
                        "write_candidate_decisions": False,
                    },
                )
            )
            experiment_dir = root / "experiment"
            experiment_dir.mkdir()

            _run_selection(experiment_dir, config, [_record(candidate)])
            selection = json.loads(
                (experiment_dir / "best_candidate_selection.json").read_text(encoding="utf-8")
            )

            self.assertEqual(selection["overall_status"], "all_candidates_rejected")
            self.assertEqual(selection["counts"]["total"], 1)
            self.assertEqual(selection["decisions"][0]["candidate_run_dir"], str(candidate.resolve()))
            self.assertEqual(selection["decisions"][0]["status"], "rejected")
            self.assertIn(
                "candidate_correctness_not_true",
                selection["decisions"][0]["rejection_reasons"],
            )

    def test_selection_enabled_with_no_verified_candidate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline = _create_baseline(root)
            candidate = _create_candidate(root, "candidate_without_verification", write_verification=False)
            config = load_experiment_config(
                _write_config(
                    root,
                    {
                        "enabled": True,
                        "baseline_run_dir": str(baseline),
                    },
                )
            )
            experiment_dir = root / "experiment"
            experiment_dir.mkdir()

            summary = _run_selection(experiment_dir, config, [_record(candidate)])
            selection = json.loads(
                (experiment_dir / "best_candidate_selection.json").read_text(encoding="utf-8")
            )

            self.assertEqual(summary["overall_status"], "no_candidates")
            self.assertEqual(selection["overall_status"], "no_candidates")
            self.assertEqual(selection["candidate_run_dirs"], [])
            self.assertEqual(selection["decisions"], [])


if __name__ == "__main__":
    unittest.main()