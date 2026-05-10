from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from orchestrator.experiments.closed_loop_state import (
    ClosedLoopIterationRecord,
    ClosedLoopPaths,
    CurrentBestState,
    IterationStatus,
    write_current_best_state,
)
from orchestrator.experiments.experiment_config import (
    CandidateFormatConfig,
    CandidateGenerationConfig,
    ClosedLoopConfig,
    ExperimentConfig,
    ExperimentPipelineConfig,
    ExperimentVariantConfig,
    HistoryPolicyConfig,
    OptimizationScopeConfig,
    SelectionConfig,
)
from orchestrator.experiments import run_experiment


TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


def _config(iterations: int = 2) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="Stage 7 final artifacts",
        description=None,
        target_file=TARGET_FILE,
        pipeline=ExperimentPipelineConfig(
            generate_candidate=True,
            materialize_candidate=True,
            verify_candidate=True,
        ),
        candidate_generation=CandidateGenerationConfig(max_source_chars=1000),
        candidate_format=CandidateFormatConfig(
            type="line_range_edits",
            source_presentation="line_numbered",
            require_original_verification=True,
            allow_exact_search_fallback=True,
        ),
        history_policy=HistoryPolicyConfig(
            enabled=False,
            scope="variant",
            max_previous_iterations=0,
            include_failed_iterations=False,
            include_materialization_results=True,
            include_verification_results=True,
        ),
        selection=SelectionConfig(
            enabled=False,
            baseline_run_dir="results/runs/baseline",
            write_candidate_decisions=True,
        ),
        closed_loop=ClosedLoopConfig(enabled=True),
        optimization_scope=OptimizationScopeConfig(allowed_files=[TARGET_FILE]),
        variants=[
            ExperimentVariantConfig(
                variant_id="mock",
                description=None,
                llm_config="configs/llm_mock_candidate.json",
                llm_overrides=None,
                iterations=iterations,
                additional_context=None,
            )
        ],
    )


def _write_source(root: Path, text: str) -> Path:
    path = root / TARGET_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _state(
    *,
    root: Path,
    paths: ClosedLoopPaths,
    current_best_iteration: int = 0,
    current_best_is_baseline: bool = True,
    current_best_run_dir: Path | None = None,
    accepted_improvements: int = 0,
) -> CurrentBestState:
    baseline_run_dir = root / "results" / "runs" / "baseline"
    baseline_run_dir.mkdir(parents=True, exist_ok=True)
    (baseline_run_dir / "metrics.json").write_text("{}\n", encoding="utf-8")
    run_dir = current_best_run_dir or baseline_run_dir
    return CurrentBestState(
        experiment_id=paths.experiment_id,
        target_file=TARGET_FILE,
        original_baseline_run_dir=baseline_run_dir,
        original_baseline_metrics_path=baseline_run_dir / "metrics.json",
        current_best_iteration=current_best_iteration,
        current_best_is_baseline=current_best_is_baseline,
        current_best_source_dir=paths.current_best_source_dir,
        current_best_run_dir=run_dir,
        current_best_metrics_path=(
            baseline_run_dir / "metrics.json"
            if current_best_is_baseline
            else run_dir / "verification.json"
        ),
        accepted_improvements=accepted_improvements,
        updated_at="2026-05-10T05:00:00+02:00",
    )


def _record(iteration: int, status: IterationStatus) -> ClosedLoopIterationRecord:
    return ClosedLoopIterationRecord(
        experiment_id="exp_001",
        iteration=iteration,
        status=status,
        base_source_kind="current_best",
        reference_best_iteration_before=max(0, iteration - 1),
        current_best_iteration_after=max(0, iteration - 1),
    )


def _patch_roots(monkeypatch, repo_root: Path, workspace_root: Path) -> None:
    monkeypatch.setattr(run_experiment, "REPO_ROOT", repo_root)
    monkeypatch.setattr(run_experiment, "WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(run_experiment, "RESULTS_ROOT", repo_root / "results")


def test_final_source_copy_diff_summary_and_state_for_baseline_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    workspace_root = tmp_path / "workspace"
    _patch_roots(monkeypatch, repo_root, workspace_root)
    paths = ClosedLoopPaths.from_roots(workspace_root, repo_root / "results", "exp_001")
    baseline_text = "int baseline = 1;\n"
    repo_target = _write_source(repo_root, baseline_text)
    _write_source(paths.current_best_source_dir, baseline_text)
    state = _state(root=repo_root, paths=paths)
    write_current_best_state(paths.current_best_state_path, state)

    summary, results_state_path = run_experiment.finalize_closed_loop_artifacts(
        paths=paths,
        experiment_id="exp_001",
        config=_config(iterations=2),
        state=state,
        records=[_record(1, IterationStatus.NO_OP), _record(2, IterationStatus.GENERATION_FAILED)],
        started_at=datetime.fromisoformat("2026-05-10T05:00:00+02:00"),
        finished_at="2026-05-10T05:10:00+02:00",
    )

    final_target = paths.final_optimized_source_dir / TARGET_FILE
    assert final_target.exists()
    assert final_target.read_text(encoding="utf-8") == baseline_text
    assert repo_target.read_text(encoding="utf-8") == baseline_text
    assert paths.final_optimized_source_diff_path.exists()
    assert paths.final_optimized_source_diff_path.read_text(encoding="utf-8") == ""

    payload = json.loads(paths.closed_loop_summary_path.read_text(encoding="utf-8"))
    assert payload["experiment_id"] == "exp_001"
    assert payload["target_file"] == TARGET_FILE
    assert payload["total_iterations"] == 2
    assert payload["completed_iterations"] == 2
    assert payload["original_baseline_run_dir"] == str(state.original_baseline_run_dir)
    assert payload["original_baseline_metrics_path"] == str(state.original_baseline_metrics_path)
    assert payload["final_best_iteration"] == 0
    assert payload["final_best_candidate_run_dir"] is None
    assert payload["final_optimized_source_dir"] == str(paths.final_optimized_source_dir)
    assert payload["final_optimized_source_diff_path"] == str(paths.final_optimized_source_diff_path)
    assert payload["final_speedup_vs_original_baseline"] == 1.0
    assert payload["final_runtime_reduction_percent"] == 0.0
    assert payload["iterations_after_final_best"] == 2
    assert payload["created_at"] == "2026-05-10T05:00:00+02:00"
    assert payload["finished_at"] == "2026-05-10T05:10:00+02:00"
    assert payload["status_counts"] == {
        "accepted_improvement": 0,
        "valid_not_improved": 0,
        "rejected": 0,
        "materialization_failed": 0,
        "verification_failed": 0,
        "no_op": 1,
        "generation_failed": 1,
    }
    assert summary.final_speedup_vs_original_baseline == 1.0
    assert results_state_path == repo_root / "results" / "experiments" / "exp_001" / "current_best_state.json"
    assert json.loads(results_state_path.read_text(encoding="utf-8")) == json.loads(
        paths.current_best_state_path.read_text(encoding="utf-8")
    )


def test_final_diff_and_summary_use_accepted_candidate_decision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    workspace_root = tmp_path / "workspace"
    _patch_roots(monkeypatch, repo_root, workspace_root)
    paths = ClosedLoopPaths.from_roots(workspace_root, repo_root / "results", "exp_001")
    _write_source(repo_root, "int value = 1;\n")
    _write_source(paths.current_best_source_dir, "int value = 2;\n")
    candidate_run_dir = repo_root / "results" / "runs" / "candidate_001"
    candidate_run_dir.mkdir(parents=True, exist_ok=True)
    (candidate_run_dir / "verification.json").write_text("{}\n", encoding="utf-8")
    (candidate_run_dir / "decision_vs_original_baseline.json").write_text(
        json.dumps(
            {
                "status": "accepted_improvement",
                "comparison": {
                    "speedup": 1.25,
                    "runtime_reduction_percent": 20.0,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    state = _state(
        root=repo_root,
        paths=paths,
        current_best_iteration=1,
        current_best_is_baseline=False,
        current_best_run_dir=candidate_run_dir,
        accepted_improvements=1,
    )
    write_current_best_state(paths.current_best_state_path, state)

    summary, results_state_path = run_experiment.finalize_closed_loop_artifacts(
        paths=paths,
        experiment_id="exp_001",
        config=_config(iterations=3),
        state=state,
        records=[
            _record(1, IterationStatus.ACCEPTED_IMPROVEMENT),
            _record(2, IterationStatus.VALID_NOT_IMPROVED),
            _record(3, IterationStatus.REJECTED),
        ],
        started_at=datetime.fromisoformat("2026-05-10T05:00:00+02:00"),
        finished_at="2026-05-10T05:10:00+02:00",
    )

    diff_text = paths.final_optimized_source_diff_path.read_text(encoding="utf-8")
    assert f"--- a/{TARGET_FILE}" in diff_text
    assert f"+++ b/{TARGET_FILE}" in diff_text
    assert "-int value = 1;" in diff_text
    assert "+int value = 2;" in diff_text
    payload = json.loads(paths.closed_loop_summary_path.read_text(encoding="utf-8"))
    assert payload["final_best_iteration"] == 1
    assert payload["final_best_candidate_run_dir"] == str(candidate_run_dir)
    assert payload["final_speedup_vs_original_baseline"] == 1.25
    assert payload["final_runtime_reduction_percent"] == 20.0
    assert payload["iterations_after_final_best"] == 2
    assert payload["status_counts"]["accepted_improvement"] == 1
    assert payload["status_counts"]["verification_failed"] == 0
    assert summary.final_speedup_vs_original_baseline == 1.25

    status_block = run_experiment._closed_loop_status_block(
        paths,
        summary,
        results_state_path,
        accepted_improvements=1,
    )
    assert status_block["enabled"] is True
    assert status_block["final_optimized_source_dir"].endswith("final_optimized_source")
    assert status_block["final_optimized_source_diff_path"].endswith("final_optimized_source.diff")
    assert status_block["closed_loop_summary_path"].endswith("closed_loop_summary.json")
    assert status_block["closed_loop_iterations_path"].endswith("closed_loop_iterations.jsonl")
    assert status_block["current_best_state_path"].endswith("current_best_state.json")

    text = run_experiment._build_closed_loop_summary_text(
        experiment_id="exp_001",
        config=_config(iterations=3),
        summary=summary,
        results_state_path=results_state_path,
        accepted_improvements=1,
    )
    assert "Closed-loop mode: enabled" in text
    assert "Final speedup vs original baseline: 1.25" in text
    assert "final optimized source:" in text
    assert "final diff:" in text
    assert "closed-loop summary:" in text
    assert "closed-loop iterations:" in text
    assert "current best state:" in text
