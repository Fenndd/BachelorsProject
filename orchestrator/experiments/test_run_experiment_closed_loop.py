"""Tests for Stage 5 closed-loop experiment orchestration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.experiments import run_experiment as runner
from orchestrator.experiments.closed_loop_state import (
    ClosedLoopPaths,
    read_current_best_state,
)
from orchestrator.experiments.experiment_config import load_experiment_config


TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _benchmark_payload(runtime: float = 1000.0) -> dict[str, Any]:
    return {
        "benchmark": {
            "family": "absolute_pose_solvers",
            "solver": "lambdatwist_p3p",
            "runtime_unit": "ns",
            "build_type": "Release",
            "benchmark_options": {"num_cases": 10, "runtime_unit": "ns", "build_type": "Release"},
            "parse_success": True,
            "parsed_num_cases": 10,
            "parsed_success_rate": 1.0,
            "parsed_mean_best_reprojection_error": 1.0e-12,
            "parsed_max_best_reprojection_error": 2.0e-12,
            "parsed_runtime_ns_per_case_median": runtime,
            "parsed_correctness_passed": True,
        }
    }


def _config_payload(root: Path, *, iterations: int = 1) -> dict[str, Any]:
    return {
        "experiment_name": "closed loop test",
        "target_file": TARGET_FILE,
        "pipeline": {
            "generate_candidate": True,
            "materialize_candidate": True,
            "verify_candidate": True,
        },
        "candidate_generation": {"max_source_chars": 1000},
        "candidate_format": {
            "type": "line_range_edits",
            "source_presentation": "line_numbered",
            "require_original_verification": True,
            "allow_exact_search_fallback": True,
        },
        "closed_loop": {"enabled": True},
        "selection": {
            "enabled": False,
            "baseline_run_dir": str(root / "results" / "runs" / "baseline"),
        },
        "llm_config": "configs/llm_mock_candidate.json",
        "iterations": iterations,
    }


def _write_config(root: Path, *, iterations: int = 1) -> Path:
    path = root / "config.json"
    _write_json(path, _config_payload(root, iterations=iterations))
    return path


def _create_repo_layout(root: Path, source_text: str = "baseline\n") -> None:
    (root / TARGET_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / TARGET_FILE).write_text(source_text, encoding="utf-8")
    baseline = root / "results" / "runs" / "baseline"
    baseline.mkdir(parents=True, exist_ok=True)
    _write_json(baseline / "metrics.json", _benchmark_payload(1000.0))


def _candidate_payload(*, expected_effect: str = "runtime", edits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "candidate_type": "line_range_edits",
        "summary": "candidate summary",
        "rationale": "candidate rationale",
        "risk_level": "low",
        "expected_effect": expected_effect,
        "target_files": [TARGET_FILE],
        "edits": [] if edits is None else edits,
        "requires_manual_review": False,
    }


class _ClosedLoopHarness:
    def __init__(self, test: unittest.TestCase, root: Path, statuses: list[str]) -> None:
        self.test = test
        self.root = root
        self.statuses = statuses
        self.generated_commands: list[list[str]] = []
        self.materialization_commands: list[list[str]] = []
        self.stage_calls: list[str] = []
        self.candidate_dirs: list[Path] = []

    def fake_run_stage(
        self,
        experiment_dir: Path,
        global_iteration: int,
        variant_id: str,
        variant_iteration: int,
        stage_name: str,
        command: list[str],
    ) -> dict[str, Any]:
        self.stage_calls.append(stage_name)
        status = self.statuses[variant_iteration - 1]
        if stage_name == "generate_candidate":
            self.generated_commands.append(command)
            candidate_dir = self.root / "results" / "runs" / f"candidate_{variant_iteration}"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            self.candidate_dirs.append(candidate_dir)
            if status == "generation_failed":
                return {"exit_code": 1, "stdout": f"CANDIDATE_RUN_DIR={candidate_dir}\n", "stderr": "", "duration_seconds": 0.1}
            _write_json(candidate_dir / "status.json", {"overall_status": "success"})
            candidate = _candidate_payload(expected_effect="none" if status == "no_op" else "runtime")
            if status != "no_op":
                candidate["edits"] = [
                    {"file": TARGET_FILE, "start_line": 1, "end_line": 1, "original": "baseline", "replace": f"candidate {variant_iteration}"}
                ]
            _write_json(candidate_dir / "candidate.json", candidate)
            return {"exit_code": 0, "stdout": f"CANDIDATE_RUN_DIR={candidate_dir}\n", "stderr": "", "duration_seconds": 0.1}

        candidate_dir = self.root / "results" / "runs" / f"candidate_{variant_iteration}"
        if stage_name == "materialize_candidate":
            self.materialization_commands.append(command)
            if status == "materialization_failed":
                _write_json(candidate_dir / "materialization.json", {"overall_status": "failed", "failed_step": "apply", "error_message": "bad patch"})
                return {"exit_code": 1, "stdout": "", "stderr": "", "duration_seconds": 0.1}
            workspace = self.root / "workspace" / "candidates" / f"candidate_{variant_iteration}"
            (workspace / TARGET_FILE).parent.mkdir(parents=True, exist_ok=True)
            (workspace / TARGET_FILE).write_text(f"candidate {variant_iteration}\n", encoding="utf-8")
            _write_json(candidate_dir / "materialization.json", {"overall_status": "success", "workspace_path": str(workspace), "changed_files": [TARGET_FILE]})
            return {"exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.1}

        if stage_name == "verify_candidate":
            if status == "verification_failed":
                _write_json(candidate_dir / "verification.json", {"overall_status": "failed", "failed_step": "benchmark", "error_message": "bad benchmark"})
                return {"exit_code": 1, "stdout": "", "stderr": "", "duration_seconds": 0.1}
            _write_json(candidate_dir / "verification.json", {"overall_status": "success", **_benchmark_payload(900.0)})
            return {"exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.1}

        raise AssertionError(f"Unexpected stage {stage_name}")

    def fake_decision(self, reference_run_dir: Path, reference_kind: str, candidate_run_dir: Path) -> dict[str, Any]:
        index = int(candidate_run_dir.name.rsplit("_", 1)[1]) - 1
        status = self.statuses[index]
        decision_status = status if status in {"accepted_improvement", "valid_not_improved", "rejected"} else "rejected"
        return {
            "status": decision_status,
            "reference_kind": reference_kind,
            "reference_run_dir": str(reference_run_dir),
            "candidate_run_dir": str(candidate_run_dir),
            "comparison": {"speedup": 1.1 if decision_status == "accepted_improvement" else 1.0, "runtime_reduction_percent": 10.0},
            "rejection_reasons": [] if decision_status != "rejected" else ["not safe"],
        }


class RunExperimentClosedLoopTests(unittest.TestCase):
    def _run_with_statuses(self, statuses: list[str]) -> tuple[Path, _ClosedLoopHarness]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        _create_repo_layout(root)
        config_path = _write_config(root, iterations=len(statuses))
        config = load_experiment_config(config_path)
        harness = _ClosedLoopHarness(self, root, statuses)

        original_repo_root = runner.REPO_ROOT
        original_results_root = runner.RESULTS_ROOT
        original_experiments_root = runner.EXPERIMENTS_ROOT
        original_workspace_root = runner.WORKSPACE_ROOT
        original_run_stage = runner._run_stage
        original_decision = runner.evaluate_candidate_against_reference
        original_resolve_variant_llm_config = runner._resolve_variant_llm_config
        self.addCleanup(setattr, runner, "REPO_ROOT", original_repo_root)
        self.addCleanup(setattr, runner, "RESULTS_ROOT", original_results_root)
        self.addCleanup(setattr, runner, "EXPERIMENTS_ROOT", original_experiments_root)
        self.addCleanup(setattr, runner, "WORKSPACE_ROOT", original_workspace_root)
        self.addCleanup(setattr, runner, "_run_stage", original_run_stage)
        self.addCleanup(setattr, runner, "evaluate_candidate_against_reference", original_decision)
        self.addCleanup(setattr, runner, "_resolve_variant_llm_config", original_resolve_variant_llm_config)

        runner.REPO_ROOT = root
        runner.RESULTS_ROOT = root / "results"
        runner.EXPERIMENTS_ROOT = root / "results" / "experiments"
        runner.WORKSPACE_ROOT = root / "workspace"
        runner._run_stage = harness.fake_run_stage  # type: ignore[method-assign]
        runner.evaluate_candidate_against_reference = harness.fake_decision  # type: ignore[assignment]
        runner._resolve_variant_llm_config = lambda variant: {"provider": "mock", "model": "mock"}  # type: ignore[assignment]

        exit_code = runner._run_experiment(config, _config_payload(root, iterations=len(statuses)))
        self.assertEqual(exit_code, 0)
        return root, harness

    def test_accepted_improvement_updates_current_best_and_writes_artifacts(self) -> None:
        root, harness = self._run_with_statuses(["accepted_improvement"])
        experiment_dir = next((root / "results" / "experiments").iterdir())
        paths = ClosedLoopPaths.from_roots(root / "workspace", root / "results", experiment_dir.name)

        state = read_current_best_state(paths.current_best_state_path)
        self.assertEqual(state.current_best_iteration, 1)
        self.assertFalse(state.current_best_is_baseline)
        self.assertEqual((paths.current_best_source_dir / TARGET_FILE).read_text(encoding="utf-8"), "candidate 1\n")
        self.assertTrue((harness.candidate_dirs[0] / "decision_vs_current_best.json").exists())
        self.assertTrue((harness.candidate_dirs[0] / "decision_vs_original_baseline.json").exists())
        record = json.loads(paths.closed_loop_iterations_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(record["status"], "accepted_improvement")
        self.assertTrue(record["current_best_updated"])
        self.assertEqual((root / TARGET_FILE).read_text(encoding="utf-8"), "baseline\n")

    def test_valid_not_improved_and_rejected_do_not_update_source(self) -> None:
        for status in ["valid_not_improved", "rejected"]:
            root, _harness = self._run_with_statuses([status])
            experiment_dir = next((root / "results" / "experiments").iterdir())
            paths = ClosedLoopPaths.from_roots(root / "workspace", root / "results", experiment_dir.name)
            state = read_current_best_state(paths.current_best_state_path)
            self.assertEqual(state.current_best_iteration, 0)
            self.assertTrue(state.current_best_is_baseline)
            self.assertEqual((paths.current_best_source_dir / TARGET_FILE).read_text(encoding="utf-8"), "baseline\n")
            record = json.loads(paths.closed_loop_iterations_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(record["status"], status)

    def test_failure_stages_and_no_op_write_records_and_continue(self) -> None:
        root, harness = self._run_with_statuses([
            "generation_failed",
            "materialization_failed",
            "verification_failed",
            "no_op",
            "valid_not_improved",
        ])
        experiment_dir = next((root / "results" / "experiments").iterdir())
        paths = ClosedLoopPaths.from_roots(root / "workspace", root / "results", experiment_dir.name)
        statuses = [json.loads(line)["status"] for line in paths.closed_loop_iterations_path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(statuses, [
            "generation_failed",
            "materialization_failed",
            "verification_failed",
            "no_op",
            "valid_not_improved",
        ])
        self.assertEqual(harness.stage_calls.count("generate_candidate"), 5)
        self.assertIn("--source-root", harness.generated_commands[0])
        self.assertIn("--base-source-root", harness.materialization_commands[0])

    def test_initialization_creates_current_best_source_and_state(self) -> None:
        root, _harness = self._run_with_statuses(["no_op"])
        experiment_dir = next((root / "results" / "experiments").iterdir())
        paths = ClosedLoopPaths.from_roots(root / "workspace", root / "results", experiment_dir.name)
        state = read_current_best_state(paths.current_best_state_path)

        self.assertTrue((paths.current_best_source_dir / TARGET_FILE).exists())
        self.assertEqual(state.current_best_iteration, 0)
        self.assertTrue(state.current_best_is_baseline)


if __name__ == "__main__":
    unittest.main()