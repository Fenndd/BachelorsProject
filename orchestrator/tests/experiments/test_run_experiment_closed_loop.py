"""Tests for closed-loop experiment orchestration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.experiments import run_experiment as runner
from orchestrator.experiments.closed_loop_state import (
    ClosedLoopIterationRecord,
    ClosedLoopPaths,
    CurrentBestState,
    IterationStatus,
    read_current_best_state,
)
from orchestrator.experiments.experiment_config import load_experiment_config


from orchestrator.tests.conftest import TARGET_FILE, write_json, make_benchmark_payload


def _fake_final_selection_report(**kwargs: Any) -> Path:
    experiment_dir = Path(kwargs["experiment_dir"])
    report_path = experiment_dir / "final_selection_report.json"
    final_best_is_baseline = kwargs.get("final_best_is_baseline", False)
    write_json(
        report_path,
        {
            "report_type": "single_run_final_selection_report",
            "metric_source": "single_run_final_best_vs_original_baseline",
            "final_best_is_baseline": final_best_is_baseline,
            "status": "skipped" if final_best_is_baseline else "completed",
            "comparison": {
                "speedup": 1.0,
                "runtime_reduction_percent": 0.0,
                "baseline_runtime_ns_per_problem_median": 1000.0,
                "final_runtime_ns_per_problem_median": 1000.0,
                "candidate_runtime_lower": False,
            },
        },
    )
    return report_path





def _config_payload(root: Path, *, iterations: int = 1) -> dict[str, Any]:
    return {
        "experiment_name": "closed loop test",
        "target_file": TARGET_FILE,
        "baseline_run_dir": str(root / "results" / "runs" / "baseline"),
        "candidate_generation": {"max_source_chars": 1000},
        "variants": [
            {
                "variant_id": "default",
                "llm_config": "configs/llm_mock_candidate.json",
                "iterations": iterations,
                "additional_context": "static additional context",
            }
        ],
    }


def _write_config(root: Path, *, iterations: int = 1) -> Path:
    path = root / "config.json"
    write_json(path, _config_payload(root, iterations=iterations))
    return path


def _create_repo_layout(root: Path, source_text: str = "baseline\n") -> None:
    (root / TARGET_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / TARGET_FILE).write_text(source_text, encoding="utf-8")
    baseline = root / "results" / "runs" / "baseline"
    baseline.mkdir(parents=True, exist_ok=True)
    write_json(baseline / "metrics.json", make_benchmark_payload(1000.0))


def _candidate_payload(*, expected_effect: str = "runtime", edits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
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
            write_json(candidate_dir / "status.json", {"overall_status": "success"})
            candidate = _candidate_payload(expected_effect="none" if status == "no_op" else "runtime")
            candidate["summary"] = f"candidate summary {variant_iteration}"
            if status != "no_op":
                candidate["edits"] = [
                    {"file": TARGET_FILE, "start_line": 1, "end_line": 1, "original": "baseline", "replace": f"candidate {variant_iteration}"}
                ]
            write_json(candidate_dir / "candidate.json", candidate)
            return {"exit_code": 0, "stdout": f"CANDIDATE_RUN_DIR={candidate_dir}\n", "stderr": "", "duration_seconds": 0.1}

        candidate_dir = self.root / "results" / "runs" / f"candidate_{variant_iteration}"
        if stage_name == "materialize_candidate":
            self.materialization_commands.append(command)
            if status == "materialization_failed":
                write_json(candidate_dir / "materialization.json", {
                    "overall_status": "failed",
                    "failed_step": "apply",
                    "error_message": "fallback_no_match: original text was not found by exact-search fallback",
                    "line_range_edit_count": 1,
                    "line_range_exact_matches": 0,
                    "line_range_trailing_whitespace_tolerant_matches": 0,
                    "line_range_surrounding_whitespace_tolerant_matches": 0,
                    "line_range_fallback_matches": 0,
                    "line_range_fallback_used": False,
                    "line_range_edit_results": [
                        {"index": 0, "status": "failed", "failure_reason": "fallback_no_match"}
                    ],
                })
                return {"exit_code": 1, "stdout": "", "stderr": "", "duration_seconds": 0.1}
            workspace = self.root / "workspace" / "candidates" / f"candidate_{variant_iteration}"
            (workspace / TARGET_FILE).parent.mkdir(parents=True, exist_ok=True)
            (workspace / TARGET_FILE).write_text(f"candidate {variant_iteration}\n", encoding="utf-8")
            write_json(candidate_dir / "materialization.json", {
                "overall_status": "success",
                "workspace_path": str(workspace),
                "changed_files": [TARGET_FILE],
                "line_range_edit_count": 1,
                "line_range_exact_matches": 1,
                "line_range_trailing_whitespace_tolerant_matches": 0,
                "line_range_surrounding_whitespace_tolerant_matches": 0,
                "line_range_fallback_matches": 0,
                "line_range_fallback_used": False,
                "line_range_edit_results": [
                    {"index": 0, "status": "success", "match_mode": "line_range_exact"}
                ],
            })
            return {"exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.1}

        if stage_name == "verify_candidate":
            if status == "verification_failed":
                write_json(candidate_dir / "verification.json", {"overall_status": "failed", "failed_step": "benchmark", "error_message": "bad benchmark"})
                return {"exit_code": 1, "stdout": "", "stderr": "", "duration_seconds": 0.1}
            write_json(candidate_dir / "verification.json", {"overall_status": "success", **make_benchmark_payload(900.0)})
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
            "non_acceptance_reasons": [],
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
        original_run_final_selection_report = runner.run_final_selection_report
        self.addCleanup(setattr, runner, "REPO_ROOT", original_repo_root)
        self.addCleanup(setattr, runner, "RESULTS_ROOT", original_results_root)
        self.addCleanup(setattr, runner, "EXPERIMENTS_ROOT", original_experiments_root)
        self.addCleanup(setattr, runner, "WORKSPACE_ROOT", original_workspace_root)
        self.addCleanup(setattr, runner, "_run_stage", original_run_stage)
        self.addCleanup(setattr, runner, "evaluate_candidate_against_reference", original_decision)
        self.addCleanup(setattr, runner, "_resolve_variant_llm_config", original_resolve_variant_llm_config)
        self.addCleanup(setattr, runner, "run_final_selection_report", original_run_final_selection_report)

        runner.REPO_ROOT = root
        runner.RESULTS_ROOT = root / "results"
        runner.EXPERIMENTS_ROOT = root / "results" / "experiments"
        runner.WORKSPACE_ROOT = root / "workspace"
        runner._run_stage = harness.fake_run_stage  # type: ignore[method-assign]
        runner.evaluate_candidate_against_reference = harness.fake_decision  # type: ignore[assignment]
        runner._resolve_variant_llm_config = lambda variant: {"provider": "mock", "model": "mock"}  # type: ignore[assignment]
        runner.run_final_selection_report = _fake_final_selection_report  # type: ignore[assignment]

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
        self.assertEqual(record["phase_timings"]["generation_seconds"], 0.1)
        self.assertEqual(record["phase_timings"]["materialization_seconds"], 0.1)
        self.assertEqual(record["phase_timings"]["verification_seconds"], 0.1)
        self.assertIsNone(record["phase_timings"]["benchmark_seconds"])
        self.assertIsInstance(record["phase_timings"]["total_iteration_seconds"], float)
        self.assertEqual(record["outcome_reason"]["category"], "decision")
        self.assertEqual(record["outcome_reason"]["code"], "accepted_improvement")
        self.assertTrue(record["history_included"])
        self.assertIn("already included in the current source", record["history_guidance"])
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
            self.assertTrue(record["history_included"])
            self.assertIsNotNone(record["history_guidance"])

    def test_each_non_promotion_status_does_not_update_current_best_source(self) -> None:
        for status in [
            "valid_not_improved",
            "rejected",
            "materialization_failed",
            "verification_failed",
            "no_op",
            "generation_failed",
        ]:
            root, _harness = self._run_with_statuses([status])
            experiment_dir = next((root / "results" / "experiments").iterdir())
            paths = ClosedLoopPaths.from_roots(root / "workspace", root / "results", experiment_dir.name)
            state = read_current_best_state(paths.current_best_state_path)
            record = json.loads(paths.closed_loop_iterations_path.read_text(encoding="utf-8").splitlines()[0])

            self.assertEqual(state.current_best_iteration, 0, status)
            self.assertTrue(state.current_best_is_baseline, status)
            self.assertEqual((paths.current_best_source_dir / TARGET_FILE).read_text(encoding="utf-8"), "baseline\n", status)
            self.assertFalse(record["current_best_updated"], status)
            self.assertEqual(record["current_best_iteration_after"], 0, status)

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
        self.assertNotIn("--allow-exact-search" + "-fallback", harness.materialization_commands[0])
        records = [json.loads(line) for line in paths.closed_loop_iterations_path.read_text(encoding="utf-8").splitlines()]
        self.assertFalse(records[0]["history_included"])
        self.assertIsNone(records[0]["history_guidance"])
        self.assertTrue(records[1]["history_included"])
        self.assertIn("original text was not found exactly", records[1]["history_guidance"])
        self.assertEqual(records[1]["materialization_match_summary"]["line_range_edit_count"], 1)
        self.assertFalse(records[1]["materialization_match_summary"]["invalid_line_range_fallback_used"])
        self.assertTrue(records[2]["history_included"])
        self.assertIn("break build", records[2]["history_guidance"])
        self.assertFalse(records[3]["history_included"])
        self.assertIsNone(records[3]["history_guidance"])
        self.assertTrue(records[4]["history_included"])

    def test_materialization_command_does_not_include_exact_search_fallback_flags(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        _create_repo_layout(root)
        config_path = _write_config(root)
        config = load_experiment_config(config_path)

        command = runner._build_materialization_command(
            "results/runs/candidate_1",
            config,
            base_source_root="workspace/experiments/exp/current_best_source",
        )

        self.assertIn("--base-source-root", command)
        self.assertNotIn("--allow-exact-search" + "-fallback", command)
        self.assertNotIn("--no-allow-exact-search" + "-fallback", command)

    def test_closed_loop_iteration_jsonl_uses_portable_paths_recursively(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        _create_repo_layout(root)
        original_repo_root = runner.REPO_ROOT
        original_results_root = runner.RESULTS_ROOT
        original_workspace_root = runner.WORKSPACE_ROOT
        self.addCleanup(setattr, runner, "REPO_ROOT", original_repo_root)
        self.addCleanup(setattr, runner, "RESULTS_ROOT", original_results_root)
        self.addCleanup(setattr, runner, "WORKSPACE_ROOT", original_workspace_root)
        runner.REPO_ROOT = root
        runner.RESULTS_ROOT = root / "results"
        runner.WORKSPACE_ROOT = root / "workspace"
        paths = ClosedLoopPaths.from_roots(root / "workspace", root / "results", "exp_001")
        baseline_run_dir = root / "results" / "runs" / "baseline"
        candidate_run_dir = root / "results" / "runs" / "candidate_1"
        candidate_run_dir.mkdir(parents=True, exist_ok=True)
        state = CurrentBestState(
            experiment_id="exp_001",
            target_file=TARGET_FILE,
            original_baseline_run_dir=baseline_run_dir,
            original_baseline_metrics_path=baseline_run_dir / "metrics.json",
            current_best_iteration=0,
            current_best_is_baseline=True,
            current_best_source_dir=paths.current_best_source_dir,
            current_best_run_dir=baseline_run_dir,
            current_best_metrics_path=baseline_run_dir / "metrics.json",
            accepted_improvements=0,
            updated_at="2026-05-10T05:00:00+02:00",
        )
        record = ClosedLoopIterationRecord(
            experiment_id="exp_001",
            iteration=1,
            status=IterationStatus.VALID_NOT_IMPROVED,
            base_source_kind="current_best",
            reference_best_iteration_before=0,
            reference_best_run_dir=baseline_run_dir,
            candidate_run_dir=candidate_run_dir,
            decision_vs_current_best={
                "status": "valid_not_improved",
                "candidate_run_dir": candidate_run_dir,
                "nested": {"metrics_path": candidate_run_dir / "metrics.json"},
            },
            current_best_iteration_after=0,
        )

        runner._append_closed_loop_record_and_state(paths, state, record)

        text = paths.closed_loop_iterations_path.read_text(encoding="utf-8")
        payload = json.loads(text)
        self.assertNotIn(str(root), text)
        self.assertNotIn(str(root / "workspace"), text)
        self.assertEqual(payload["candidate_run_dir"], "results/runs/candidate_1")
        self.assertEqual(payload["reference_best_run_dir"], "results/runs/baseline")
        self.assertEqual(
            payload["decision_vs_current_best"]["nested"]["metrics_path"],
            "results/runs/candidate_1/metrics.json",
        )

    def test_parse_candidate_run_dir_supports_canonical_and_narrow_fallbacks(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        original_repo_root = runner.REPO_ROOT
        self.addCleanup(setattr, runner, "REPO_ROOT", original_repo_root)
        runner.REPO_ROOT = root
        fallback_run = root / "results" / "runs" / "candidate_2"
        fallback_run.mkdir(parents=True)
        write_json(fallback_run / "candidate.json", _candidate_payload())
        fallback_request_run = root / "results" / "runs" / "candidate_3"
        fallback_request_run.mkdir(parents=True)
        write_json(fallback_request_run / "llm_request.json", {"ok": True})
        empty_run = root / "results" / "runs" / "empty"
        empty_run.mkdir(parents=True)
        baseline_like = root / "results" / "runs" / "baseline"
        baseline_like.mkdir(parents=True)
        write_json(baseline_like / "metrics.json", make_benchmark_payload())
        wrong_status = root / "results" / "runs" / "wrong_status"
        wrong_status.mkdir(parents=True)
        write_json(wrong_status / "candidate.json", _candidate_payload())
        write_json(wrong_status / "status.json", {"scenario": "baseline"})

        self.assertEqual(
            runner._parse_candidate_run_dir("CANDIDATE_RUN_DIR=results/runs/candidate_1\n"),
            "results/runs/candidate_1",
        )
        self.assertEqual(
            runner._parse_candidate_run_dir("Final status: success\nRun directory: results/runs/candidate_2\n"),
            "results/runs/candidate_2",
        )
        self.assertEqual(
            runner._parse_candidate_run_dir("Artifacts saved to: results/runs/candidate_3\n"),
            "results/runs/candidate_3",
        )
        self.assertIsNone(runner._parse_candidate_run_dir("Run directory: results/runs/missing\n"))
        self.assertIsNone(runner._parse_candidate_run_dir("Run directory: results/runs/empty\n"))
        self.assertIsNone(runner._parse_candidate_run_dir("Run directory: results/runs/baseline\n"))
        self.assertIsNone(runner._parse_candidate_run_dir("Run directory: results/runs/wrong_status\n"))
        self.assertIsNone(runner._parse_candidate_run_dir("Run directory: workspace/not_a_candidate\n"))

    def test_initialization_creates_current_best_source_and_state(self) -> None:
        root, _harness = self._run_with_statuses(["no_op"])
        experiment_dir = next((root / "results" / "experiments").iterdir())
        paths = ClosedLoopPaths.from_roots(root / "workspace", root / "results", experiment_dir.name)
        state = read_current_best_state(paths.current_best_state_path)

        self.assertTrue((paths.current_best_source_dir / TARGET_FILE).exists())
        self.assertEqual(state.current_best_iteration, 0)
        self.assertTrue(state.current_best_is_baseline)

    def test_closed_loop_history_context_is_passed_and_logged(self) -> None:
        root, harness = self._run_with_statuses([
            "accepted_improvement",
            "no_op",
            "valid_not_improved",
        ])
        experiment_dir = next((root / "results" / "experiments").iterdir())

        first_log = experiment_dir / "logs" / "iteration_001_closed_loop_history_context.txt"
        second_log = experiment_dir / "logs" / "iteration_002_closed_loop_history_context.txt"
        third_log = experiment_dir / "logs" / "iteration_003_closed_loop_history_context.txt"

        self.assertEqual(first_log.read_text(encoding="utf-8").strip(), "No meaningful closed-loop history yet.")
        second_history = second_log.read_text(encoding="utf-8")
        third_history = third_log.read_text(encoding="utf-8")
        self.assertIn("Iteration 1: accepted improvement.", second_history)
        self.assertIn("candidate summary 1", second_history)
        self.assertIn("already included in the current source", second_history)
        self.assertIn("Iteration 1: accepted improvement.", third_history)
        self.assertNotIn("Iteration 2: no_op", third_history)
        self.assertNotIn("candidate summary 2", third_history)

        first_command = harness.generated_commands[0]
        second_command = harness.generated_commands[1]
        third_command = harness.generated_commands[2]
        self.assertIn("--context", first_command)
        first_context = first_command[first_command.index("--context") + 1]
        self.assertEqual(first_context, "static additional context")
        self.assertNotIn("Closed-loop optimization history", first_context)
        self.assertIn("--context", second_command)
        second_context = second_command[second_command.index("--context") + 1]
        self.assertIn("static additional context", second_context)
        self.assertIn("Closed-loop optimization history", second_context)
        self.assertIn("already included in the current source", second_context)
        self.assertIn("--context", third_command)
        third_context = third_command[third_command.index("--context") + 1]
        self.assertIn("candidate summary 1", third_context)
        self.assertNotIn("candidate summary 2", third_context)

    def test_controlled_mock_closed_loop_promotes_only_accepted_iteration(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        _create_repo_layout(root, source_text="BASELINE_VALUE\n")
        config_path = _write_config(root, iterations=3)
        config = load_experiment_config(config_path)
        main_source_before = (root / TARGET_FILE).read_text(encoding="utf-8")

        stage_calls: list[tuple[str, int]] = []
        generated_commands: list[list[str]] = []

        def fake_run_stage(
            experiment_dir: Path,
            global_iteration: int,
            variant_id: str,
            variant_iteration: int,
            stage_name: str,
            command: list[str],
        ) -> dict[str, Any]:
            stage_calls.append((stage_name, variant_iteration))
            candidate_dir = root / "results" / "runs" / f"candidate_{variant_iteration}"
            if stage_name == "generate_candidate":
                generated_commands.append(command)
                candidate_dir.mkdir(parents=True, exist_ok=True)
                write_json(candidate_dir / "status.json", {"overall_status": "success"})
                if variant_iteration == 3:
                    candidate = _candidate_payload(expected_effect="none", edits=[])
                    candidate["summary"] = "No useful change"
                else:
                    replacement = "ACCEPTED_VALUE" if variant_iteration == 1 else "SLOWER_VALUE"
                    original = "BASELINE_VALUE" if variant_iteration == 1 else "ACCEPTED_VALUE"
                    candidate = _candidate_payload(
                        edits=[
                            {
                                "file": TARGET_FILE,
                                "start_line": 1,
                                "end_line": 1,
                                "original": original,
                                "replace": replacement,
                            }
                        ]
                    )
                    candidate["summary"] = f"Change marker to {replacement}"
                write_json(candidate_dir / "candidate.json", candidate)
                return {"exit_code": 0, "stdout": f"CANDIDATE_RUN_DIR={candidate_dir}\n", "stderr": "", "duration_seconds": 0.1}

            if stage_name == "materialize_candidate":
                replacement = "ACCEPTED_VALUE" if variant_iteration == 1 else "SLOWER_VALUE"
                workspace = root / "workspace" / "candidates" / f"candidate_{variant_iteration}"
                (workspace / TARGET_FILE).parent.mkdir(parents=True, exist_ok=True)
                (workspace / TARGET_FILE).write_text(f"{replacement}\n", encoding="utf-8")
                write_json(candidate_dir / "materialization.json", {"overall_status": "success", "workspace_path": str(workspace), "changed_files": [TARGET_FILE]})
                return {"exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.1}

            if stage_name == "verify_candidate":
                runtime = 800.0 if variant_iteration == 1 else 900.0
                write_json(candidate_dir / "verification.json", {"overall_status": "success", **make_benchmark_payload(runtime)})
                return {"exit_code": 0, "stdout": "", "stderr": "", "duration_seconds": 0.1}

            raise AssertionError(f"Unexpected stage {stage_name}")

        def fake_decision(reference_run_dir: Path, reference_kind: str, candidate_run_dir: Path) -> dict[str, Any]:
            iteration = int(candidate_run_dir.name.rsplit("_", 1)[1])
            status = "accepted_improvement" if iteration == 1 else "valid_not_improved"
            speedup = 1.25 if iteration == 1 else 0.95
            return {
                "status": status,
                "reference_kind": reference_kind,
                "reference_run_dir": str(reference_run_dir),
                "candidate_run_dir": str(candidate_run_dir),
                "comparison": {"speedup": speedup, "runtime_reduction_percent": 20.0 if iteration == 1 else -5.0},
                "rejection_reasons": [],
                "non_acceptance_reasons": [],
            }

        originals = {
            "REPO_ROOT": runner.REPO_ROOT,
            "RESULTS_ROOT": runner.RESULTS_ROOT,
            "EXPERIMENTS_ROOT": runner.EXPERIMENTS_ROOT,
            "WORKSPACE_ROOT": runner.WORKSPACE_ROOT,
            "_run_stage": runner._run_stage,
            "evaluate_candidate_against_reference": runner.evaluate_candidate_against_reference,
            "_resolve_variant_llm_config": runner._resolve_variant_llm_config,
            "run_final_selection_report": runner.run_final_selection_report,
        }
        for name, value in originals.items():
            self.addCleanup(setattr, runner, name, value)
        runner.REPO_ROOT = root
        runner.RESULTS_ROOT = root / "results"
        runner.EXPERIMENTS_ROOT = root / "results" / "experiments"
        runner.WORKSPACE_ROOT = root / "workspace"
        runner._run_stage = fake_run_stage  # type: ignore[assignment]
        runner.evaluate_candidate_against_reference = fake_decision  # type: ignore[assignment]
        runner._resolve_variant_llm_config = lambda variant: {"provider": "mock", "model": "mock"}  # type: ignore[assignment]
        runner.run_final_selection_report = _fake_final_selection_report  # type: ignore[assignment]

        exit_code = runner._run_experiment(config, _config_payload(root, iterations=3))

        self.assertEqual(exit_code, 0)
        experiment_dir = next((root / "results" / "experiments").iterdir())
        paths = ClosedLoopPaths.from_roots(root / "workspace", root / "results", experiment_dir.name)
        records = [json.loads(line) for line in paths.closed_loop_iterations_path.read_text(encoding="utf-8").splitlines()]
        summary = json.loads(paths.closed_loop_summary_path.read_text(encoding="utf-8"))

        self.assertEqual([call for call in stage_calls if call[0] == "generate_candidate"], [("generate_candidate", 1), ("generate_candidate", 2), ("generate_candidate", 3)])
        self.assertEqual([record["status"] for record in records], ["accepted_improvement", "valid_not_improved", "no_op"])
        self.assertEqual((paths.current_best_source_dir / TARGET_FILE).read_text(encoding="utf-8"), "ACCEPTED_VALUE\n")
        self.assertEqual((paths.final_optimized_source_dir / TARGET_FILE).read_text(encoding="utf-8"), "ACCEPTED_VALUE\n")
        diff_text = paths.final_optimized_source_diff_path.read_text(encoding="utf-8")
        self.assertIn("-BASELINE_VALUE", diff_text)
        self.assertIn("+ACCEPTED_VALUE", diff_text)
        self.assertEqual(summary["status_counts"]["accepted_improvement"], 1)
        self.assertEqual(summary["status_counts"]["valid_not_improved"], 1)
        self.assertEqual(summary["status_counts"]["no_op"], 1)
        selection_report = json.loads((experiment_dir / "closed_loop_selection_report.json").read_text(encoding="utf-8"))
        self.assertEqual(selection_report["control_decision"]["promotion_policy"], "decision_vs_current_best.accepted_improvement_only")
        self.assertEqual(selection_report["control_decision"]["final_best_iteration"], 1)
        self.assertEqual(selection_report["single_run_selection_analytics"]["metric_source"], "single_run_closed_loop_selection_analytics")
        self.assertEqual(selection_report["single_run_selection_analytics"]["status_counts"]["valid_not_improved"], 1)
        self.assertFalse(selection_report["safety"]["report_promotes_candidates"])
        self.assertFalse(selection_report["safety"]["report_updates_current_best_source"])
        self.assertFalse(selection_report["safety"]["report_updates_final_optimized_source"])
        self.assertFalse(selection_report["safety"]["report_modifies_main_cpp_tree"])
        self.assertEqual((root / TARGET_FILE).read_text(encoding="utf-8"), main_source_before)
        third_context = generated_commands[2][generated_commands[2].index("--context") + 1]
        self.assertIn("ACCEPTED_VALUE", third_context)
        self.assertIn("SLOWER_VALUE", third_context)
        self.assertNotIn("No useful change", third_context)


if __name__ == "__main__":
    unittest.main()
