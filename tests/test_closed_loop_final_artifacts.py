from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from orchestrator.experiments.closed_loop_state import (
    ClosedLoopIterationRecord,
    ClosedLoopPaths,
    ClosedLoopSummary,
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
        experiment_name="closed_loop_final_artifacts",
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


def _write_build_artifacts(root: Path) -> None:
    for relative in [
        "cpp/build/temp.obj",
        "cpp/build-codex/cache.txt",
        "cpp/build-pre-step-11-cleanup/cache.txt",
        "cpp/cmake-build-debug/cache.txt",
        "cpp/CMakeFiles/generated.txt",
        "cpp/Testing/test.xml",
    ]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")
    for relative in [
        "cpp/CMakeCache.txt",
        "cpp/build.ninja",
        "cpp/.ninja_log",
        "cpp/tool.exe",
        "cpp/libtemp.lib",
        "cpp/libtemp.a",
    ]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")


def _assert_build_artifacts_excluded(root: Path) -> None:
    for relative in [
        "cpp/build",
        "cpp/build-codex",
        "cpp/build-pre-step-11-cleanup",
        "cpp/cmake-build-debug",
        "cpp/CMakeFiles",
        "cpp/Testing",
        "cpp/CMakeCache.txt",
        "cpp/build.ninja",
        "cpp/.ninja_log",
        "cpp/tool.exe",
        "cpp/libtemp.lib",
        "cpp/libtemp.a",
    ]:
        assert not (root / relative).exists(), relative


def _json_text_without_timestamps(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ["created_at", "finished_at", "started_at", "updated_at"]:
        payload.pop(key, None)
    return json.dumps(payload, sort_keys=True)


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
    comparison_speedup = 1.1 if status == IterationStatus.ACCEPTED_IMPROVEMENT else 1.0
    comparison_runtime_reduction = 9.1 if status == IterationStatus.ACCEPTED_IMPROVEMENT else 0.0
    decision = {
        "status": status.value,
        "comparison": {
            "speedup": comparison_speedup,
            "runtime_reduction_percent": comparison_runtime_reduction,
        },
        "rejection_reasons": ["correctness_failed"] if status == IterationStatus.REJECTED else [],
        "non_acceptance_reasons": [],
    }
    return ClosedLoopIterationRecord(
        experiment_id="exp_001",
        iteration=iteration,
        status=status,
        base_source_kind="current_best",
        reference_best_iteration_before=max(0, iteration - 1),
        candidate_run_dir=Path(f"results/runs/candidate_{iteration:03d}") if status != IterationStatus.GENERATION_FAILED else None,
        decision_vs_current_best=decision if status in {IterationStatus.ACCEPTED_IMPROVEMENT, IterationStatus.VALID_NOT_IMPROVED, IterationStatus.REJECTED} else None,
        decision_vs_original_baseline=decision if status in {IterationStatus.ACCEPTED_IMPROVEMENT, IterationStatus.VALID_NOT_IMPROVED, IterationStatus.REJECTED} else None,
        speedup_vs_current_best=1.1 if status == IterationStatus.ACCEPTED_IMPROVEMENT else None,
        speedup_vs_original_baseline=1.2 if status == IterationStatus.ACCEPTED_IMPROVEMENT else None,
        current_best_updated=status == IterationStatus.ACCEPTED_IMPROVEMENT,
        current_best_iteration_after=max(0, iteration - 1),
        failure_stage="generation" if status == IterationStatus.GENERATION_FAILED else None,
        failure_reason="failed" if status == IterationStatus.GENERATION_FAILED else None,
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
    _write_build_artifacts(paths.current_best_source_dir)
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
    _assert_build_artifacts_excluded(paths.final_optimized_source_dir)
    assert repo_target.read_text(encoding="utf-8") == baseline_text
    assert paths.final_optimized_source_diff_path.exists()
    assert paths.final_optimized_source_diff_path.read_text(encoding="utf-8") == ""

    payload = json.loads(paths.closed_loop_summary_path.read_text(encoding="utf-8"))
    assert payload["experiment_id"] == "exp_001"
    assert payload["target_file"] == TARGET_FILE
    assert payload["total_iterations"] == 2
    assert payload["completed_iterations"] == 2
    assert payload["original_baseline_run_dir"] == "results/runs/baseline"
    assert payload["original_baseline_metrics_path"] == "results/runs/baseline/metrics.json"
    assert payload["final_best_iteration"] == 0
    assert payload["final_best_candidate_run_dir"] is None
    assert payload["final_optimized_source_dir"] == "results/experiments/exp_001/final_optimized_source"
    assert payload["final_optimized_source_diff_path"] == "results/experiments/exp_001/final_optimized_source.diff"
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
    results_state = json.loads(results_state_path.read_text(encoding="utf-8"))
    assert results_state["original_baseline_run_dir"] == "results/runs/baseline"
    assert results_state["current_best_source_dir"] == "workspace/experiments/exp_001/current_best_source"


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
    assert payload["final_best_candidate_run_dir"] == "results/runs/candidate_001"
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
    assert "Final speedup ratio vs original baseline: 1.25" in text
    assert "Final runtime reduction percent vs original baseline: 20.0" in text
    assert "final optimized source:" in text
    assert "final diff:" in text
    assert "closed-loop summary:" in text
    assert "closed-loop iterations:" in text
    assert "current best state:" in text


def test_current_best_initialization_promotion_and_final_copy_ignore_build_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    workspace_root = tmp_path / "workspace"
    _patch_roots(monkeypatch, repo_root, workspace_root)
    paths = ClosedLoopPaths.from_roots(workspace_root, repo_root / "results", "exp_001")
    config = _config(iterations=1)
    repo_target = _write_source(repo_root, "int repo = 1;\n")
    _write_build_artifacts(repo_root)

    run_experiment.initialize_current_best_source(paths, config)

    assert (paths.current_best_source_dir / TARGET_FILE).exists()
    _assert_build_artifacts_excluded(paths.current_best_source_dir)
    assert (repo_root / "cpp" / "build").exists()
    assert repo_target.read_text(encoding="utf-8") == "int repo = 1;\n"

    candidate_workspace = tmp_path / "candidate_workspace"
    _write_source(candidate_workspace, "int candidate = 2;\n")
    _write_build_artifacts(candidate_workspace)
    run_experiment.update_current_best_source_from_workspace(paths, candidate_workspace, config)

    assert (paths.current_best_source_dir / TARGET_FILE).read_text(encoding="utf-8") == "int candidate = 2;\n"
    _assert_build_artifacts_excluded(paths.current_best_source_dir)

    run_experiment.copy_final_optimized_source(paths, config)
    assert (paths.final_optimized_source_dir / TARGET_FILE).read_text(encoding="utf-8") == "int candidate = 2;\n"
    _assert_build_artifacts_excluded(paths.final_optimized_source_dir)
    assert repo_target.read_text(encoding="utf-8") == "int repo = 1;\n"


def test_closed_loop_selection_report_is_reporting_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    workspace_root = tmp_path / "workspace"
    _patch_roots(monkeypatch, repo_root, workspace_root)
    paths = ClosedLoopPaths.from_roots(workspace_root, repo_root / "results", "exp_001")
    repo_target = _write_source(repo_root, "int value = 1;\n")
    current_best_target = _write_source(paths.current_best_source_dir, "int value = 2;\n")
    final_target = _write_source(paths.final_optimized_source_dir, "int value = 2;\n")
    state = _state(
        root=repo_root,
        paths=paths,
        current_best_iteration=1,
        current_best_is_baseline=False,
        current_best_run_dir=repo_root / "results" / "runs" / "candidate_001",
        accepted_improvements=1,
    )
    summary = ClosedLoopSummary(
        experiment_id="exp_001",
        target_file=TARGET_FILE,
        total_iterations=2,
        completed_iterations=2,
        original_baseline_run_dir=state.original_baseline_run_dir,
        original_baseline_metrics_path=state.original_baseline_metrics_path,
        final_best_iteration=1,
        final_best_candidate_run_dir=state.current_best_run_dir,
        final_optimized_source_dir=paths.final_optimized_source_dir,
        final_optimized_source_diff_path=paths.final_optimized_source_diff_path,
        final_speedup_vs_original_baseline=1.25,
        final_runtime_reduction_percent=20.0,
        iterations_after_final_best=1,
        status_counts={status.value: 0 for status in IterationStatus},
        created_at="2026-05-10T05:00:00+02:00",
        finished_at="2026-05-10T05:10:00+02:00",
    )

    report_path = run_experiment.write_closed_loop_selection_report(
        repo_root / "results" / "experiments" / "exp_001",
        state,
        summary,
        [
            _record(1, IterationStatus.ACCEPTED_IMPROVEMENT),
            _record(2, IterationStatus.VALID_NOT_IMPROVED),
            _record(3, IterationStatus.REJECTED),
            _record(4, IterationStatus.NO_OP),
            _record(5, IterationStatus.GENERATION_FAILED),
        ],
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["control_decision"]["promotion_policy"] == "decision_vs_current_best.accepted_improvement_only"
    assert report["experiment_id"] == "exp_001"
    assert report["target_file"] == TARGET_FILE
    assert report["mode"] == "closed_loop"
    assert report["final_current_best"]["iteration"] == 1
    assert report["final_current_best"]["run_dir"] == "results/runs/candidate_001"
    assert report["final_current_best"]["source_dir"] == "workspace/experiments/exp_001/current_best_source"
    assert len(report["candidate_attempts"]) == 5
    assert [attempt["status"] for attempt in report["candidate_attempts"]] == [
        "accepted_improvement",
        "valid_not_improved",
        "rejected",
        "no_op",
        "generation_failed",
    ]
    assert "candidate_summary" not in report["candidate_attempts"][0]
    assert "audit" not in json.dumps(report["candidate_attempts"])
    assert "diff --git" not in json.dumps(report)
    assert report["status_counts"] == summary.status_counts
    assert report["control_decision"]["final_best_iteration"] == 1
    assert report["control_decision"]["final_best_run_dir"] == "results/runs/candidate_001"
    assert report["final_analysis"]["performance_reference"] == "original_baseline"
    assert report["final_analysis"]["final_speedup_vs_original_baseline"] == 1.25
    best = report["best_verified_candidate_vs_original_baseline"]
    assert best["iteration"] == 1
    assert best["candidate_run_dir"] == "results/runs/candidate_001"
    assert best["speedup"] == 1.1
    assert best["runtime_reduction_percent"] == 9.1
    assert best["matches_final_current_best"] is True
    assert best["status"] == "accepted_improvement"
    assert report["safety"] == {
        "report_promotes_candidates": False,
        "report_updates_current_best_source": False,
        "report_updates_final_optimized_source": False,
        "report_modifies_main_cpp_tree": False,
    }
    assert repo_target.read_text(encoding="utf-8") == "int value = 1;\n"
    assert current_best_target.read_text(encoding="utf-8") == "int value = 2;\n"
    assert final_target.read_text(encoding="utf-8") == "int value = 2;\n"


def test_selection_report_best_verified_match_false_and_none(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    workspace_root = tmp_path / "workspace"
    _patch_roots(monkeypatch, repo_root, workspace_root)
    paths = ClosedLoopPaths.from_roots(workspace_root, repo_root / "results", "exp_001")
    state = _state(
        root=repo_root,
        paths=paths,
        current_best_iteration=1,
        current_best_is_baseline=False,
        current_best_run_dir=repo_root / "results" / "runs" / "candidate_001",
        accepted_improvements=1,
    )
    summary = ClosedLoopSummary(
        experiment_id="exp_001",
        target_file=TARGET_FILE,
        total_iterations=2,
        completed_iterations=2,
        original_baseline_run_dir=state.original_baseline_run_dir,
        original_baseline_metrics_path=state.original_baseline_metrics_path,
        final_best_iteration=1,
        final_best_candidate_run_dir=state.current_best_run_dir,
        final_optimized_source_dir=paths.final_optimized_source_dir,
        final_optimized_source_diff_path=paths.final_optimized_source_diff_path,
        final_speedup_vs_original_baseline=1.1,
        final_runtime_reduction_percent=9.0,
        iterations_after_final_best=1,
        status_counts={status.value: 0 for status in IterationStatus},
        created_at="2026-05-10T05:00:00+02:00",
        finished_at="2026-05-10T05:10:00+02:00",
    )
    better_non_final = _record(2, IterationStatus.VALID_NOT_IMPROVED)
    better_non_final.decision_vs_current_best = {
        "status": "valid_not_improved",
        "comparison": {
            "speedup": 0.98,
            "runtime_reduction_percent": -2.0,
            "candidate_runtime_lower": False,
        },
        "rejection_reasons": [],
        "non_acceptance_reasons": [],
    }
    better_non_final.decision_vs_original_baseline = {
        "status": "accepted_improvement",
        "comparison": {
            "speedup": 1.5,
            "runtime_reduction_percent": 33.3,
        },
        "rejection_reasons": [],
        "non_acceptance_reasons": [],
    }
    better_non_final.speedup_vs_current_best = None
    better_non_final.speedup_vs_original_baseline = None
    report_path = run_experiment.write_closed_loop_selection_report(
        repo_root / "results" / "experiments" / "exp_001",
        state,
        summary,
        [_record(1, IterationStatus.ACCEPTED_IMPROVEMENT), better_non_final],
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["best_verified_candidate_vs_original_baseline"]["candidate_run_dir"] == "results/runs/candidate_002"
    assert report["best_verified_candidate_vs_original_baseline"]["runtime_reduction_percent"] == 33.3
    assert report["best_verified_candidate_vs_original_baseline"]["matches_final_current_best"] is False

    below_threshold = _record(3, IterationStatus.VALID_NOT_IMPROVED)
    below_threshold.decision_vs_original_baseline = {
        "status": "valid_not_improved",
        "comparison": {
            "speedup": 1.001,
            "runtime_reduction_percent": 0.1,
        },
        "rejection_reasons": [],
        "non_acceptance_reasons": ["runtime_improvement_below_minimum_threshold"],
    }
    below_threshold.speedup_vs_original_baseline = 1.001
    below_path = run_experiment.write_closed_loop_selection_report(
        repo_root / "results" / "experiments" / "exp_003",
        state,
        summary,
        [_record(1, IterationStatus.ACCEPTED_IMPROVEMENT), below_threshold],
    )
    below_report = json.loads(below_path.read_text(encoding="utf-8"))
    assert below_report["best_verified_candidate_vs_original_baseline"]["candidate_run_dir"] == "results/runs/candidate_001"
    assert below_report["best_verified_candidate_vs_original_baseline"]["status"] == "accepted_improvement"

    legacy = _record(4, IterationStatus.ACCEPTED_IMPROVEMENT)
    legacy.decision_vs_original_baseline = {
        "status": "accepted_improvement",
        "speedup": 1.4,
        "runtime_reduction_percent": 28.6,
    }
    legacy.speedup_vs_original_baseline = None
    legacy_path = run_experiment.write_closed_loop_selection_report(
        repo_root / "results" / "experiments" / "exp_004",
        state,
        summary,
        [legacy],
    )
    legacy_report = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert legacy_report["best_verified_candidate_vs_original_baseline"]["speedup"] == 1.4
    assert legacy_report["best_verified_candidate_vs_original_baseline"]["runtime_reduction_percent"] == 28.6

    no_best_path = run_experiment.write_closed_loop_selection_report(
        repo_root / "results" / "experiments" / "exp_002",
        state,
        summary,
        [_record(1, IterationStatus.NO_OP)],
    )
    no_best_report = json.loads(no_best_path.read_text(encoding="utf-8"))
    assert no_best_report["best_verified_candidate_vs_original_baseline"] is None


def test_result_side_closed_loop_json_paths_are_portable(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    workspace_root = tmp_path / "workspace"
    _patch_roots(monkeypatch, repo_root, workspace_root)
    paths = ClosedLoopPaths.from_roots(workspace_root, repo_root / "results", "exp_001")
    _write_source(repo_root, "int value = 1;\n")
    _write_source(paths.current_best_source_dir, "int value = 1;\n")
    state = _state(root=repo_root, paths=paths)
    write_current_best_state(paths.current_best_state_path, state)
    summary, results_state_path = run_experiment.finalize_closed_loop_artifacts(
        paths=paths,
        experiment_id="exp_001",
        config=_config(iterations=1),
        state=state,
        records=[_record(1, IterationStatus.NO_OP)],
        started_at=datetime.fromisoformat("2026-05-10T05:00:00+02:00"),
        finished_at="2026-05-10T05:10:00+02:00",
    )
    report_path = run_experiment.write_closed_loop_selection_report(
        repo_root / "results" / "experiments" / "exp_001",
        state,
        summary,
        [_record(1, IterationStatus.NO_OP)],
    )
    status = {
        "closed_loop": run_experiment._closed_loop_status_block(paths, summary, results_state_path, 0),
        "closed_loop_selection_report_path": run_experiment._display_path(report_path),
    }
    status_path = repo_root / "results" / "experiments" / "exp_001" / "experiment_status.json"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    for path in [paths.closed_loop_summary_path, report_path, results_state_path, status_path]:
        text = _json_text_without_timestamps(path)
        assert "C:\\" not in text
        assert str(repo_root) not in text
        assert str(workspace_root) not in text
