from __future__ import annotations

import json
from pathlib import Path
import pytest

from orchestrator.experiments.closed_loop_state import (
    ClosedLoopIterationRecord,
    ClosedLoopPaths,
    ClosedLoopSummary,
    CurrentBestState,
    IterationStatus,
    append_closed_loop_iteration_record,
    count_iteration_statuses,
    read_current_best_state,
    to_plain_dict,
    write_closed_loop_summary,
    write_current_best_state,
)


def test_all_required_statuses_exist_and_serialize() -> None:
    assert [status.value for status in IterationStatus] == [
        "accepted_improvement",
        "valid_not_improved",
        "rejected",
        "materialization_failed",
        "verification_failed",
        "no_op",
        "generation_failed",
    ]
    assert to_plain_dict(IterationStatus.NO_OP) == "no_op"


def test_closed_loop_paths_build_expected_structure() -> None:
    paths = ClosedLoopPaths.from_roots(
        Path("workspace"),
        Path("results"),
        "exp_001",
    )

    assert paths.current_best_source_dir == Path(
        "workspace/experiments/exp_001/current_best_source"
    )
    assert paths.current_best_state_path == Path(
        "workspace/experiments/exp_001/current_best_state.json"
    )
    assert paths.final_optimized_source_dir == Path(
        "results/experiments/exp_001/final_optimized_source"
    )
    assert paths.final_optimized_source_diff_path == Path(
        "results/experiments/exp_001/final_optimized_source.diff"
    )
    assert paths.closed_loop_summary_path == Path(
        "results/experiments/exp_001/closed_loop_summary.json"
    )
    assert paths.closed_loop_iterations_path == Path(
        "results/experiments/exp_001/closed_loop_iterations.jsonl"
    )


def _baseline_state(root: Path) -> CurrentBestState:
    baseline_run_dir = root / "results" / "runs" / "baseline"
    return CurrentBestState(
        experiment_id="exp_001",
        target_file="cpp/external/lambdatwist/p3p.cc",
        original_baseline_run_dir=baseline_run_dir,
        original_baseline_metrics_path=baseline_run_dir / "metrics.json",
        current_best_iteration=0,
        current_best_is_baseline=True,
        current_best_source_dir=root / "workspace" / "experiments" / "exp_001" / "current_best_source",
        current_best_run_dir=baseline_run_dir,
        current_best_metrics_path=baseline_run_dir / "metrics.json",
        accepted_improvements=0,
        updated_at="2026-05-09T23:31:00+02:00",
    )


def _candidate_state(root: Path) -> CurrentBestState:
    candidate_run_dir = root / "results" / "runs" / "candidate_001"
    return CurrentBestState(
        experiment_id="exp_001",
        target_file="cpp/external/lambdatwist/p3p.cc",
        original_baseline_run_dir=root / "results" / "runs" / "baseline",
        original_baseline_metrics_path=root / "results" / "runs" / "baseline" / "metrics.json",
        current_best_iteration=1,
        current_best_is_baseline=False,
        current_best_source_dir=root / "workspace" / "experiments" / "exp_001" / "current_best_source",
        current_best_run_dir=candidate_run_dir,
        current_best_metrics_path=candidate_run_dir / "verification.json",
        accepted_improvements=1,
        updated_at="2026-05-09T23:31:00+02:00",
    )


def test_current_best_state_can_represent_baseline_iteration_zero(tmp_path: Path) -> None:
    state = _baseline_state(tmp_path)

    assert state.current_best_iteration == 0
    assert state.current_best_is_baseline is True
    assert state.accepted_improvements == 0


def test_current_best_state_can_represent_accepted_candidate(tmp_path: Path) -> None:
    state = _candidate_state(tmp_path)

    assert state.current_best_iteration == 1
    assert state.current_best_is_baseline is False
    assert state.accepted_improvements == 1


def test_current_best_state_rejects_negative_iteration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="current_best_iteration must be non-negative"):
        CurrentBestState(**{**_baseline_state(tmp_path).__dict__, "current_best_iteration": -1})


def test_current_best_state_rejects_negative_accepted_improvements(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="accepted_improvements must be non-negative"):
        CurrentBestState(**{**_baseline_state(tmp_path).__dict__, "accepted_improvements": -1})


def test_current_best_state_rejects_iteration_zero_non_baseline(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="iteration is 0"):
        CurrentBestState(**{**_baseline_state(tmp_path).__dict__, "current_best_is_baseline": False})


def test_current_best_state_rejects_candidate_iteration_marked_baseline(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        CurrentBestState(**{**_candidate_state(tmp_path).__dict__, "current_best_is_baseline": True})


def test_current_best_state_rejects_baseline_with_accepted_improvements(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="accepted_improvements must be 0"):
        CurrentBestState(**{**_baseline_state(tmp_path).__dict__, "accepted_improvements": 1})


def test_current_best_state_rejects_candidate_without_accepted_improvement(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        CurrentBestState(**{**_candidate_state(tmp_path).__dict__, "accepted_improvements": 0})


def test_current_best_state_serializes_path_fields_to_strings(tmp_path: Path) -> None:
    payload = to_plain_dict(_baseline_state(tmp_path))

    assert isinstance(payload["original_baseline_run_dir"], str)
    assert isinstance(payload["original_baseline_metrics_path"], str)
    assert isinstance(payload["current_best_source_dir"], str)
    assert payload["current_best_iteration"] == 0


def test_iteration_record_serializes_as_jsonl_compatible_dict(tmp_path: Path) -> None:
    record = ClosedLoopIterationRecord(
        experiment_id="exp_001",
        iteration=1,
        status=IterationStatus.ACCEPTED_IMPROVEMENT,
        base_source_kind="baseline",
        reference_best_iteration_before=0,
        reference_best_run_dir=tmp_path / "baseline",
        candidate_run_dir=tmp_path / "candidate_1",
        candidate_summary={"changed_files": ["cpp/external/lambdatwist/p3p.cc"]},
        candidate_rationale="Simplify arithmetic.",
        candidate_expected_effect="faster",
        candidate_risk_level="low",
        decision_vs_current_best={"accepted": True},
        decision_vs_original_baseline={"accepted": True},
        speedup_vs_current_best=1.05,
        speedup_vs_original_baseline=1.05,
        current_best_updated=True,
        current_best_iteration_after=1,
        history_included=True,
        history_guidance="Avoid previous failed edit.",
        created_at="2026-05-09T23:31:00+02:00",
    )

    payload = to_plain_dict(record)

    assert payload["status"] == "accepted_improvement"
    assert isinstance(payload["candidate_run_dir"], str)
    json.dumps(payload)


def test_append_iteration_record_writes_exactly_one_json_object_per_line(tmp_path: Path) -> None:
    path = tmp_path / "closed_loop_iterations.jsonl"
    record = ClosedLoopIterationRecord(
        experiment_id="exp_001",
        iteration=1,
        status=IterationStatus.NO_OP,
        base_source_kind="current_best",
        reference_best_iteration_before=0,
        current_best_iteration_after=0,
    )

    append_closed_loop_iteration_record(path, record)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "no_op"
    assert payload["iteration"] == 1


def test_closed_loop_summary_serializes_correctly(tmp_path: Path) -> None:
    summary = ClosedLoopSummary(
        experiment_id="exp_001",
        target_file="cpp/external/lambdatwist/p3p.cc",
        total_iterations=5,
        completed_iterations=5,
        original_baseline_run_dir=tmp_path / "results" / "runs" / "baseline",
        original_baseline_metrics_path=tmp_path / "results" / "runs" / "baseline" / "metrics.json",
        final_best_iteration=2,
        final_best_candidate_run_dir=tmp_path / "results" / "runs" / "candidate_2",
        final_optimized_source_dir=tmp_path / "results" / "experiments" / "exp_001" / "final_optimized_source",
        final_optimized_source_diff_path=tmp_path
        / "results"
        / "experiments"
        / "exp_001"
        / "final_optimized_source.diff",
        iterations_after_final_best=3,
        status_counts={status.value: 0 for status in IterationStatus},
        created_at="2026-05-09T23:31:00+02:00",
        finished_at="2026-05-09T23:40:00+02:00",
    )

    payload = to_plain_dict(summary)
    assert payload["final_best_iteration"] == 2
    assert isinstance(payload["final_optimized_source_dir"], str)

    output_path = write_closed_loop_summary(tmp_path / "summary.json", summary)
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert "final_speedup_vs_original_baseline" not in saved
    assert "final_runtime_reduction_percent" not in saved


def test_status_counting_includes_all_statuses_with_zero_counts() -> None:
    records = [
        ClosedLoopIterationRecord(
            experiment_id="exp_001",
            iteration=1,
            status=IterationStatus.ACCEPTED_IMPROVEMENT,
            base_source_kind="baseline",
            reference_best_iteration_before=0,
        ),
        {"status": "valid_not_improved"},
        {"status": IterationStatus.VERIFICATION_FAILED},
        {"status": "valid_not_improved"},
    ]

    counts = count_iteration_statuses(records)

    assert counts == {
        "accepted_improvement": 1,
        "valid_not_improved": 2,
        "rejected": 0,
        "materialization_failed": 0,
        "verification_failed": 1,
        "no_op": 0,
        "generation_failed": 0,
    }


def test_current_best_state_read_write_round_trips_basic_fields(tmp_path: Path) -> None:
    state = _baseline_state(tmp_path)
    path = tmp_path / "workspace" / "experiments" / "exp_001" / "current_best_state.json"

    write_current_best_state(path, state)
    loaded = read_current_best_state(path)

    assert loaded.experiment_id == state.experiment_id
    assert loaded.target_file == state.target_file
    assert loaded.current_best_iteration == 0
    assert loaded.current_best_is_baseline is True
    assert loaded.current_best_source_dir == state.current_best_source_dir
    assert loaded.current_best_metrics_path == state.current_best_metrics_path
