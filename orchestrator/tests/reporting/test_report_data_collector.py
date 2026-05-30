from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

import json
from pathlib import Path

import pytest

from orchestrator.experiments.closed_loop_state import IterationStatus
from orchestrator.reporting import (
    collect_and_write_report_data,
    collect_report_data,
)


from orchestrator.tests.conftest import TARGET_FILE, write_json, write_jsonl


def _summary(**overrides: object) -> dict:
    payload = {
        "experiment_id": "exp_001",
        "target_file": TARGET_FILE,
        "total_iterations": 2,
        "completed_iterations": 2,
        "original_baseline_metrics_path": "missing_metrics.json",
        "final_best_iteration": 1,
        "final_optimized_source_dir": "results/experiments/exp_001/final_optimized_source",
        "final_optimized_source_diff_path": "results/experiments/exp_001/final_optimized_source.diff",
        "status_counts": {
            "accepted_improvement": 1,
            "materialization_failed": 1,
        },
    }
    payload.update(overrides)
    return payload


def _experiment_dir(tmp_path: Path) -> Path:
    return tmp_path / "results" / "experiments" / "exp_001"


def test_collect_report_data_maps_minimal_closed_loop_summary(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    write_json(experiment_dir / "experiment_config_snapshot.json", {"raw": True})
    write_json(experiment_dir / "experiment_config_effective.json", {"effective": True})

    report_data = collect_report_data(experiment_dir)

    assert report_data.experiment.experiment_id == "exp_001"
    assert report_data.experiment.target_file == TARGET_FILE
    assert report_data.experiment.total_iterations == 2
    assert report_data.experiment.completed_iterations == 2
    assert report_data.experiment.experiment_mode == "closed_loop"
    assert report_data.final_result.final_speedup_vs_baseline is None
    assert report_data.final_result.final_runtime_reduction_percent is None
    assert report_data.final_result.accepted_improvements == 1
    assert str(report_data.artifacts.experiment_config_snapshot).replace("\\", "/").endswith(
        "results/experiments/exp_001/experiment_config_snapshot.json"
    )
    assert str(report_data.artifacts.experiment_config_effective).replace("\\", "/").endswith(
        "results/experiments/exp_001/experiment_config_effective.json"
    )


def test_collect_report_data_does_not_apply_overrides_when_final_selection_failed(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    write_json(
        experiment_dir / "final_selection_report.json",
        {
            "report_type": "repeated_median_final_selection_report",
            "status": "failed",
            "failed_step": "benchmark",
            "comparison": {
                "speedup": None,
                "runtime_reduction_percent": None,
            },
        },
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.final_result.final_speedup_vs_baseline is None
    assert report_data.final_result.final_runtime_reduction_percent is None
    assert report_data.final_best_candidate.speedup_vs_baseline is None
    assert report_data.final_best_candidate.runtime_reduction_percent is None
    assert report_data.final_result.correctness_preserved is None


def test_collect_report_data_uses_final_selection_metrics_when_available(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    write_json(
        experiment_dir / "final_selection_report.json",
        {
            "report_type": "repeated_median_final_selection_report",
            "metric_source": "existing_repeated_median_final_best_vs_original_baseline",
            "final_best_is_baseline": False,
            "status": "completed",
            "final_benchmark": {
                "parsed_correctness_passed": True,
                "parsed_runtime_ns_per_problem_median": 80.0,
            },
            "comparison": {
                "speedup": 1.25,
                "runtime_reduction_percent": 20.0,
                "baseline_runtime_ns_per_problem_median": 100.0,
                "final_runtime_ns_per_problem_median": 80.0,
                "candidate_runtime_lower": True,
            },
        },
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.final_selection.status == "completed"
    assert report_data.final_selection.final_best_is_baseline is False
    assert report_data.final_selection.speedup_vs_original_baseline == 1.25
    assert report_data.final_selection.runtime_reduction_percent == 20.0
    assert report_data.final_selection.baseline_runtime_ns_per_problem_median == 100.0
    assert report_data.final_selection.final_runtime_ns_per_problem_median == 80.0
    assert report_data.final_selection.final_correctness_passed is True
    assert report_data.final_result.final_speedup_vs_baseline == 1.25
    assert report_data.final_result.final_runtime_reduction_percent == 20.0
    assert report_data.final_best_candidate.runtime_ns_per_problem_median == 80.0
    assert report_data.final_best_candidate.baseline_runtime_ns_per_problem_median == 100.0
    assert report_data.final_best_candidate.absolute_runtime_difference_ns_per_problem == 20.0
    assert report_data.final_best_candidate.speedup_vs_baseline == 1.25
    assert report_data.final_best_candidate.runtime_reduction_percent == 20.0
    assert report_data.final_result.correctness_preserved is True
    assert report_data.artifacts.final_selection_report is not None


def test_report_data_includes_gt_found_deltas_and_selection_policy(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_json(
        experiment_dir / "experiment_config_snapshot.json",
        {"selection": {"gt_found_max_drop_points": 2.0}},
    )
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": "results/runs/candidate_001",
                "decision_vs_current_best": {
                    "comparison": {
                        "candidate_gt_found_percent": 98.5,
                        "gt_found_delta_points": -1.5,
                    }
                },
                "decision_vs_original_baseline": {
                    "comparison": {
                        "candidate_gt_found_percent": 98.5,
                        "gt_found_delta_points": -1.5,
                    }
                },
            }
        ],
    )
    write_json(
        experiment_dir / "final_selection_report.json",
        {
            "report_type": "repeated_median_final_selection_report",
            "final_best_is_baseline": False,
            "status": "completed",
            "final_benchmark": {"parsed_correctness_passed": True},
            "comparison": {
                "speedup": 1.25,
                "runtime_reduction_percent": 20.0,
                "baseline_runtime_ns_per_problem_median": 100.0,
                "final_runtime_ns_per_problem_median": 80.0,
                "baseline_gt_found_percent": 100.0,
                "final_gt_found_percent": 98.5,
                "final_gt_found_delta_points": -1.5,
            },
        },
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.selection_policy.gt_found_gate_enabled is True
    assert report_data.selection_policy.gt_found_max_drop_points == 2.0
    assert report_data.final_selection.baseline_gt_found_percent == 100.0
    assert report_data.final_selection.final_gt_found_percent == 98.5
    assert report_data.final_selection.final_gt_found_delta_points == -1.5
    assert report_data.final_best_candidate.gt_found_delta_points == -1.5
    assert report_data.iterations[0].gt_found_percent == 98.5
    assert report_data.iterations[0].gt_found_delta_points_vs_original_baseline == -1.5
    assert report_data.iterations[0].gt_found_delta_points_vs_current_best == -1.5


def test_collect_report_data_maps_iteration_records(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_summary": "Simplify arithmetic.",
                "candidate_expected_effect": "faster",
                "candidate_risk_level": "low",
                "speedup_vs_current_best": 1.1,
                "speedup_vs_original_baseline": 1.25,
                "current_best_updated": True,
                "candidate_run_dir": "results/runs/candidate_001",
            },
            {
                "iteration": 2,
                "status": "materialization_failed",
                "failure_reason": "Patch could not be applied.",
                "runtime_ns_per_problem_median": None,
            },
        ],
    )

    report_data = collect_report_data(experiment_dir)

    assert len(report_data.iterations) == 2
    accepted = report_data.iterations[0]
    assert accepted.status == "accepted_improvement"
    assert accepted.promoted is True
    assert accepted.expected_effect == "faster"
    assert accepted.risk_level == "low"
    assert accepted.speedup_vs_baseline == 1.25
    failed = report_data.iterations[1]
    assert failed.status == "materialization_failed"
    assert failed.runtime_ns_per_problem_median is None
    assert failed.reason == "Patch could not be applied."


def test_collect_report_data_reads_existing_outcome_reason(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "generation_failed",
                "outcome_reason": {
                    "category": "generation",
                    "code": "llm_response_parse_failed",
                    "severity": "error",
                    "message": "LLM response could not be parsed as a valid candidate.",
                    "source_artifact": "results/runs/candidate_001/status.json",
                },
            }
        ],
    )

    report_data = collect_report_data(experiment_dir)

    reason = report_data.iterations[0].outcome_reason
    assert reason.category == "generation"
    assert reason.code == "llm_response_parse_failed"
    assert report_data.reason_code_counts[0].category == "generation"
    assert report_data.reason_code_counts[0].code == "llm_response_parse_failed"


def test_collect_report_data_reconstructs_missing_outcome_reason(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "verification_failed",
                "candidate_run_dir": str(candidate_dir),
            }
        ],
    )
    write_json(
        candidate_dir / "verification.json",
        {
            "overall_status": "failed",
            "failed_step": "benchmark_correctness_check",
            "error_message": "correctness failed",
        },
    )

    report_data = collect_report_data(experiment_dir)

    reason = report_data.iterations[0].outcome_reason
    assert reason.category == "verification"
    assert reason.code == "benchmark_correctness_failed"
    assert reason.source_artifact is not None


def test_reason_code_counts_group_iterations(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "valid_not_improved",
                "outcome_reason": {
                    "category": "decision",
                    "code": "valid_not_improved",
                    "severity": "info",
                    "message": "Candidate preserved correctness but did not improve over current best.",
                    "source_artifact": None,
                },
            },
            {
                "iteration": 2,
                "status": "valid_not_improved",
                "outcome_reason": {
                    "category": "decision",
                    "code": "valid_not_improved",
                    "severity": "info",
                    "message": "Candidate preserved correctness but did not improve over current best.",
                    "source_artifact": None,
                },
            },
            {
                "iteration": 3,
                "status": "no_op",
                "outcome_reason": {
                    "category": "no_op",
                    "code": "empty_edit_payload",
                    "severity": "info",
                    "message": "Candidate declared no expected effect and did not include edits.",
                    "source_artifact": None,
                },
            },
        ],
    )

    report_data = collect_report_data(experiment_dir)

    assert [(item.category, item.code, item.count, item.iterations) for item in report_data.reason_code_counts] == [
        ("decision", "valid_not_improved", 2, [1, 2]),
        ("no_op", "empty_edit_payload", 1, [3]),
    ]


def test_iteration_metrics_are_enriched_from_verification_json(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": str(candidate_dir),
            },
        ],
    )
    write_json(
        candidate_dir / "verification.json",
        {
            "benchmark": {
                "parsed_runtime_ns_per_problem_median": 777.0,
                "parsed_correctness_passed": True,
            },
        },
    )

    report_data = collect_report_data(experiment_dir)

    iteration = report_data.iterations[0]
    assert iteration.runtime_ns_per_problem_median == 777.0
    assert iteration.correctness_passed is True


def test_speedup_and_reason_are_enriched_from_decision_files(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "valid_not_improved",
                "candidate_run_dir": str(candidate_dir),
            },
        ],
    )
    write_json(
        candidate_dir / "decision_vs_original_baseline.json",
        {
            "status": "valid_not_improved",
            "comparison": {
                "speedup": 0.992,
                "runtime_reduction_percent": -0.8,
            },
            "non_acceptance_reasons": ["runtime_not_improved"],
        },
    )

    report_data = collect_report_data(experiment_dir)

    iteration = report_data.iterations[0]
    assert iteration.speedup_vs_baseline == 0.992
    assert iteration.reason == "runtime_not_improved"


def test_candidate_summary_fields_fall_back_to_candidate_json(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": str(candidate_dir),
            },
        ],
    )
    write_json(
        candidate_dir / "candidate.json",
        {
            "summary": "Hoist invariant expression.",
            "expected_effect": "runtime",
            "risk_level": "low",
            "extra": {"not": "copied"},
        },
    )

    report_data = collect_report_data(experiment_dir)

    iteration = report_data.iterations[0]
    assert iteration.candidate_summary == "Hoist invariant expression."
    assert iteration.expected_effect == "runtime"
    assert iteration.risk_level == "low"


def test_collect_report_data_includes_process_metadata(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(final_diff_stats={"files_changed": 1, "lines_added": 2, "lines_removed": 1, "changed_blocks": 1}),
    )
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": str(candidate_dir),
                "phase_timings": {
                    "generation_seconds": 0.1,
                    "materialization_seconds": 0.2,
                    "verification_seconds": 0.3,
                    "benchmark_seconds": None,
                    "total_iteration_seconds": 0.7,
                },
            }
        ],
    )
    write_json(
        candidate_dir / "llm_response.json",
        {
            "llm_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
                "api_latency_seconds": 1.25,
                "finish_reason": "stop",
                "model": "mock-model",
                "model_version": None,
            }
        },
    )
    write_json(
        candidate_dir / "materialization.json",
        {
            "diff_stats": {
                "files_changed": 1,
                "lines_added": 2,
                "lines_removed": 1,
                "changed_blocks": 1,
                "edit_count": 1,
                "fallback_used": False,
            }
        },
    )
    write_json(
        experiment_dir / "experiment_metadata.json",
        {
            "schema_version": "experiment_metadata.v1",
            "started_at": "2026-05-13T10:00:00+02:00",
            "finished_at": "2026-05-13T10:01:00+02:00",
            "total_duration_seconds": 60.0,
            "repository": {"git_commit": "abc", "git_branch": "reportUpdatev2v3", "dirty_worktree": True},
            "environment": {"platform": "test", "python_version": "3.x"},
        },
    )

    report_data = collect_report_data(experiment_dir)

    iteration = report_data.iterations[0]
    assert iteration.phase_timings is not None
    assert iteration.phase_timings.total_iteration_seconds == 0.7
    assert iteration.llm_usage is not None
    assert iteration.llm_usage.total_tokens == 30
    assert iteration.diff_stats is not None
    assert iteration.diff_stats.edit_count == 1
    assert report_data.experiment_metadata is not None
    assert report_data.experiment_metadata.repository["git_branch"] == "reportUpdatev2v3"
    final_best = report_data.final_best_candidate
    assert final_best.diff_stats is not None
    assert final_best.diff_stats.files_changed == 1


def test_missing_optional_candidate_artifacts_do_not_fail(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    candidate_dir.mkdir(parents=True)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": str(candidate_dir),
            },
        ],
    )

    report_data = collect_report_data(experiment_dir)

    iteration = report_data.iterations[0]
    assert iteration.runtime_ns_per_problem_median is None
    assert iteration.correctness_passed is None
    assert iteration.speedup_vs_baseline is None
    assert iteration.reason is None
    assert iteration.phase_timings is None
    assert iteration.llm_usage is None
    assert iteration.diff_stats is None
    assert iteration.outcome_reason.code == "accepted_improvement"
    assert report_data.experiment_metadata is None


def test_bad_optional_candidate_json_does_not_fail(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "verification.json").write_text("{not json", encoding="utf-8")
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": str(candidate_dir),
            },
        ],
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.iterations[0].runtime_ns_per_problem_median is None


def test_valid_not_improved_uses_default_reason_when_none_available(
    tmp_path: Path,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [{"iteration": 1, "status": "valid_not_improved"}],
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.iterations[0].reason == "runtime_not_improved"


def test_repo_relative_candidate_run_dir_is_resolved_for_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    monkeypatch.chdir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": "results/runs/candidate_001",
            },
        ],
    )
    write_json(
        candidate_dir / "verification.json",
        {"metrics": {"runtime_ns_per_problem_median": 615.0}},
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.iterations[0].runtime_ns_per_problem_median == 615.0


def test_collect_report_data_extracts_reason_from_decision_lists(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "valid_not_improved",
                "decision_vs_current_best": {
                    "rejection_reasons": [],
                    "non_acceptance_reasons": [
                        "runtime_improvement_below_minimum_threshold",
                        "candidate_not_promoted",
                    ],
                },
            },
        ],
    )

    report_data = collect_report_data(experiment_dir)

    assert (
        report_data.iterations[0].reason
        == "runtime_improvement_below_minimum_threshold; candidate_not_promoted"
    )


def test_reason_summary_ignores_original_baseline_decision(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "valid_not_improved",
                "decision_vs_current_best": {"non_acceptance_reasons": []},
                "decision_vs_original_baseline": {
                    "non_acceptance_reasons": [
                        "runtime_improvement_below_minimum_threshold"
                    ]
                },
            }
        ],
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.iterations[0].reason == "runtime_not_improved"
    assert report_data.reason_summary[0].reason == "runtime_not_improved"


def test_valid_not_improved_uses_current_best_specific_reason(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "valid_not_improved",
                "decision_vs_current_best": {
                    "non_acceptance_reasons": ["candidate_not_promoted"]
                },
                "decision_vs_original_baseline": {
                    "non_acceptance_reasons": [
                        "runtime_improvement_below_minimum_threshold"
                    ]
                },
            }
        ],
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.iterations[0].reason == "candidate_not_promoted"


def test_summary_status_counts_are_completed_with_zero_defaults(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(status_counts={"accepted_improvement": 1}),
    )
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.status_counts == {
        **{status.value: 0 for status in IterationStatus},
        "accepted_improvement": 1,
    }


def test_status_counts_fall_back_to_jsonl_when_summary_has_none(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    summary = _summary()
    summary.pop("status_counts")
    write_json(experiment_dir / "closed_loop_summary.json", summary)
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {"iteration": 1, "status": "accepted_improvement"},
            {"iteration": 2, "status": "valid_not_improved"},
            {"iteration": 3, "status": "valid_not_improved"},
        ],
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.status_counts["accepted_improvement"] == 1
    assert report_data.status_counts["valid_not_improved"] == 2
    assert report_data.status_counts["generation_failed"] == 0


def test_collect_and_write_report_data_writes_default_report_data_path(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    output_path = collect_and_write_report_data(experiment_dir)

    assert output_path == experiment_dir / "report" / "report_data.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["artifacts"]["report_data"].endswith("report_data.json")
    assert payload["artifacts"]["report_html"].endswith("report.html")
    assert payload["artifacts"]["report_pdf"] is None  # PDF not generated yet
    assert payload["artifacts"]["plots_dir"].endswith("plots")


def test_missing_baseline_metrics_file_keeps_metrics_empty(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(original_baseline_metrics_path=str(tmp_path / "missing.json")),
    )
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.baseline_metrics.runtime_ns_per_problem_median is None
    assert report_data.baseline_metrics.gt_found_percent is None
    assert report_data.baseline_metrics.valid_solutions_percent is None
    assert report_data.baseline_metrics.correctness_passed is None


def test_existing_baseline_metrics_are_loaded_best_effort(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    metrics_path = tmp_path / "results" / "runs" / "baseline" / "metrics.json"
    write_json(
        metrics_path,
        {
            "runtime_ns_per_problem_median": 1000.0,
            "gt_found_percent": 100.0,
            "valid_solutions_percent": 95.0,
            "total_solutions": 1024,
            "solutions_per_problem": 1,
            "gt_found": 1024,
            "valid_solutions": 973,
            "correctness_passed": True,
        },
    )
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(original_baseline_metrics_path=str(metrics_path)),
    )
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.baseline_metrics.runtime_ns_per_problem_median == 1000.0
    assert report_data.baseline_metrics.gt_found_percent == 100.0
    assert report_data.baseline_metrics.valid_solutions_percent == 95.0
    assert report_data.baseline_metrics.total_solutions == 1024
    assert report_data.baseline_metrics.solutions_per_problem == 1
    assert report_data.baseline_metrics.gt_found == 1024
    assert report_data.baseline_metrics.valid_solutions == 973
    assert report_data.baseline_metrics.correctness_passed is True


def test_missing_closed_loop_summary_raises_file_not_found(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    with pytest.raises(FileNotFoundError, match="closed_loop_summary.json"):
        collect_report_data(experiment_dir)


def test_missing_closed_loop_iterations_raises_file_not_found(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())

    with pytest.raises(FileNotFoundError, match="closed_loop_iterations.jsonl"):
        collect_report_data(experiment_dir)


# ---------------------------------------------------------------------------
# Current report enrichment coverage
# ---------------------------------------------------------------------------


def test_a_collector_fills_config_and_llm_fields(tmp_path: Path) -> None:
    """Collector reads experiment_config_snapshot.json and resolved LLM config."""

    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    write_json(
        experiment_dir / "experiment_config_snapshot.json",
        {
            "experiment_name": "My Experiment",
            "target_file": TARGET_FILE,
            "baseline_run_dir": "results/runs/baseline",
            "llm_config": "configs/llm_deepseek_pro_max.json",
            "iterations": 5,
            "optimization_scope": {"allowed_files": [TARGET_FILE]},
            "reporting": {"enabled": True, "formats": ["html"], "renderer": "auto"},
        },
    )

    write_json(
        experiment_dir / "resolved_llm_config.json",
        {
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "thinking": {"enabled": True, "effort": "high"},
            "max_tokens": 8192,
        },
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.experiment.experiment_name == "My Experiment"
    assert report_data.experiment.model == "deepseek-v4-pro"
    assert report_data.llm.provider == "deepseek"
    assert report_data.llm.model == "deepseek-v4-pro"
    assert report_data.llm.thinking_enabled is True
    assert report_data.llm.thinking_effort == "high"
    assert report_data.llm.max_tokens == 8192


def test_b_collector_fills_benchmark_config(tmp_path: Path) -> None:
    """Collector fills benchmark_config from baseline metrics.json."""

    experiment_dir = _experiment_dir(tmp_path)
    metrics_path = tmp_path / "results" / "runs" / "baseline" / "metrics.json"
    write_json(
        metrics_path,
        {
            "benchmark": {
                "family": "absolute_pose_solvers",
                "solver": "lambdatwist_p3p",
                "runtime_unit": "ns",
                "build_type": "Release",
                "benchmark_options": {
                    "build_type": "Release",
                    "num_problems": 1024,
                    "n_point_point": 3,
                    "n_point_line": 0,
                    "tolerance": 1.0,
                    "camera_fov": 60.0,
                    "timed_iterations": 50,
                    "random_seed": 42,
                },
                "parsed_runtime_ns_per_problem_median": 1000.0,
                "parsed_correctness_passed": True,
            }
        },
    )
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(original_baseline_metrics_path=str(metrics_path)),
    )
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.benchmark_config.family == "absolute_pose_solvers"
    assert report_data.benchmark_config.solver == "lambdatwist_p3p"
    assert report_data.benchmark_config.num_problems == 1024
    assert report_data.benchmark_config.timed_iterations == 50
    assert report_data.benchmark_config.seed == 42
    assert report_data.benchmark_config.build_type == "Release"


def test_benchmark_config_build_type_falls_back_to_release(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.benchmark_config.build_type == "Release"


def test_c_correctness_preserved_not_inferred_from_promoted_iteration(tmp_path: Path) -> None:
    """headline correctness_preserved comes only from final selection."""

    experiment_dir = _experiment_dir(tmp_path)
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(final_best_iteration=2),
    )
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "valid_not_improved",
                "correctness_passed": False,
                "current_best_updated": False,
            },
            {
                "iteration": 2,
                "status": "accepted_improvement",
                "correctness_passed": True,
                "current_best_updated": True,
            },
        ],
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.final_result.correctness_preserved is None


def test_d_pdf_display_when_html_only_formats(tmp_path: Path) -> None:
    """pdf_display shows 'Not generated' message when formats=["html"] and no PDF file."""

    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    write_json(
        experiment_dir / "experiment_config_snapshot.json",
        {
            "experiment_name": "Html Only",
            "target_file": TARGET_FILE,
            "reporting": {"enabled": True, "formats": ["html"], "renderer": "auto"},
            "baseline_run_dir": "results/runs/baseline",
        },
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.reporting_status.pdf_generated is False
    assert report_data.reporting_status.report_pdf_path is None
    assert "Not generated" in (report_data.reporting_status.pdf_display or "")
    assert '"html"' in (report_data.reporting_status.pdf_display or "")


def test_reason_summary_groups_non_accepted_iterations(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(total_iterations=5, completed_iterations=5),
    )
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {"iteration": 1, "status": "valid_not_improved"},
            {"iteration": 2, "status": "valid_not_improved"},
            {"iteration": 3, "status": "no_op"},
            {"iteration": 4, "status": "generation_failed"},
            {"iteration": 5, "status": "accepted_improvement", "current_best_updated": True},
        ],
    )

    report_data = collect_report_data(experiment_dir)

    reasons = {item.reason: item for item in report_data.reason_summary}
    assert "runtime_not_improved" in reasons
    assert reasons["runtime_not_improved"].count == 2
    assert sorted(reasons["runtime_not_improved"].iterations) == [1, 2]
    assert "no_op" in reasons
    assert reasons["no_op"].count == 1
    assert "generation_failed" in reasons
    assert reasons["generation_failed"].count == 1
    assert "accepted_improvement" not in reasons


def test_e_artifact_paths_end_with_known_segments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Artifact display paths end with expected filenames/dirs.

    When the experiment_dir is under a fake repo root (monkeypatched), display
    paths should be POSIX-relative to that root.
    """

    import orchestrator.reporting.report_data_collector as rdc

    from orchestrator.paths import get_project_paths

    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / "configs").mkdir(exist_ok=True)
    (tmp_path / "cpp").mkdir(exist_ok=True)
    (tmp_path / "orchestrator").mkdir(exist_ok=True)

    # Make tmp_path the fake repo root so display paths come out relative
    monkeypatch.setattr(rdc, "paths", get_project_paths(tmp_path))

    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    exp_dir_display = str(report_data.artifacts.experiment_dir or "")
    report_data_display = str(report_data.artifacts.report_data or "")
    report_html_display = str(report_data.artifacts.report_html or "")
    closed_loop_display = str(report_data.artifacts.closed_loop_summary or "")

    # All paths should use forward slashes (POSIX) and be repo-relative
    assert "\\" not in exp_dir_display
    assert exp_dir_display.startswith("results/experiments/exp_001")
    assert report_data_display.endswith("report_data.json")
    assert report_html_display.endswith("report.html")
    assert closed_loop_display.endswith("closed_loop_summary.json")
    # report_pdf is None since no PDF file was generated
    assert report_data.artifacts.report_pdf is None


def test_artifact_map_includes_extended_existing_artifacts(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    for name in (
        "experiment_metadata.json",
        "final_diff_stats.json",
        "current_best_state.json",
        "closed_loop_selection_report.json",
        "experiment_status.json",
    ):
        write_json(experiment_dir / name, {})
    write_json(experiment_dir / "final_selection_report.json", {})
    (experiment_dir / "final_selection").mkdir(parents=True, exist_ok=True)
    (experiment_dir / "summary.txt").write_text("summary\n", encoding="utf-8")

    report_data = collect_report_data(experiment_dir)

    assert str(report_data.artifacts.experiment_metadata).endswith("experiment_metadata.json")
    assert str(report_data.artifacts.final_diff_stats).endswith("final_diff_stats.json")
    assert str(report_data.artifacts.current_best_state).endswith("current_best_state.json")
    assert str(report_data.artifacts.closed_loop_selection_report).endswith("closed_loop_selection_report.json")
    assert str(report_data.artifacts.experiment_status).endswith("experiment_status.json")
    assert str(report_data.artifacts.summary_txt).endswith("summary.txt")
    assert str(report_data.artifacts.final_selection_dir).endswith("final_selection")
    assert str(report_data.artifacts.final_selection_report).replace("\\", "/").endswith(
        "final_selection_report.json"
    )


def test_llm_usage_summary_is_aggregated(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_1 = tmp_path / "results" / "runs" / "candidate_001"
    candidate_2 = tmp_path / "results" / "runs" / "candidate_002"
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {"iteration": 1, "status": "valid_not_improved", "candidate_run_dir": str(candidate_1)},
            {"iteration": 2, "status": "valid_not_improved", "candidate_run_dir": str(candidate_2)},
        ],
    )
    write_json(
        candidate_1 / "llm_response.json",
        {"llm_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "api_latency_seconds": 1.0}},
    )
    write_json(
        candidate_2 / "llm_response.json",
        {"llm_usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "api_latency_seconds": 3.0}},
    )

    report_data = collect_report_data(experiment_dir)

    summary = report_data.llm_usage_summary
    assert summary.prompt_tokens_total == 30
    assert summary.completion_tokens_total == 15
    assert summary.total_tokens == 45
    assert summary.api_latency_seconds_total == 4.0
    assert summary.api_latency_seconds_average == 2.0
    assert summary.iterations_with_usage == 2
    assert summary.most_expensive_iteration == 2
    assert summary.highest_latency_iteration == 2


def test_llm_usage_summary_computes_missing_total_tokens(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_1 = tmp_path / "results" / "runs" / "candidate_001"
    candidate_2 = tmp_path / "results" / "runs" / "candidate_002"
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {"iteration": 1, "status": "valid_not_improved", "candidate_run_dir": str(candidate_1)},
            {"iteration": 2, "status": "valid_not_improved", "candidate_run_dir": str(candidate_2)},
        ],
    )
    write_json(
        candidate_1 / "llm_response.json",
        {"llm_usage": {"prompt_tokens": 10, "completion_tokens": 5}},
    )
    write_json(
        candidate_2 / "llm_response.json",
        {"llm_usage": {"prompt_tokens": 20, "completion_tokens": 10}},
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.llm_usage_summary.total_tokens == 45
    assert report_data.llm_usage_summary.most_expensive_iteration == 2


# ---------------------------------------------------------------------------
# Fix 1: Report paths always populated even before files exist
# ---------------------------------------------------------------------------


def test_reporting_status_paths_always_populated(tmp_path: Path) -> None:
    """report_data_path and report_html_path are set even before files exist."""

    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    assert not (experiment_dir / "report" / "report_data.json").exists()
    assert not (experiment_dir / "report" / "report.html").exists()

    report_data = collect_report_data(experiment_dir)

    rdp = report_data.reporting_status.report_data_path or ""
    rhp = report_data.reporting_status.report_html_path or ""
    assert "report/report_data.json" in rdp.replace("\\", "/")
    assert "report/report.html" in rhp.replace("\\", "/")


# ---------------------------------------------------------------------------
# Fix 2: Reporting formats override
# ---------------------------------------------------------------------------


def test_reporting_formats_override(tmp_path: Path) -> None:
    """collect_report_data accepts reporting_formats_override and overrides config."""

    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    write_json(
        experiment_dir / "experiment_config_snapshot.json",
        {
            "experiment_name": "Override Test",
            "target_file": TARGET_FILE,
            "reporting": {"enabled": True, "formats": ["html"], "renderer": "weasyprint"},
            "baseline_run_dir": "results/runs/baseline",
        },
    )

    report_data = collect_report_data(
        experiment_dir,
        reporting_formats_override=("html", "pdf"),
        reporting_renderer_override="playwright",
    )

    assert report_data.reporting_status.formats == ["html", "pdf"]
    assert report_data.reporting_status.renderer == "playwright"


def test_reporting_pdf_pending_when_pdf_absent_but_requested(tmp_path: Path) -> None:
    """pdf_display shows 'generation pending' when formats include pdf but file missing."""

    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    write_json(
        experiment_dir / "experiment_config_snapshot.json",
        {
            "experiment_name": "PDF Pending",
            "target_file": TARGET_FILE,
            "reporting": {"enabled": True, "formats": ["html", "pdf"], "renderer": "auto"},
            "baseline_run_dir": "results/runs/baseline",
        },
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.reporting_status.pdf_generated is False
    assert report_data.reporting_status.report_pdf_path is None
    assert "PDF requested" in (report_data.reporting_status.pdf_display or "")
    assert "generation pending" in (report_data.reporting_status.pdf_display or "")


# ---------------------------------------------------------------------------
# Fix 4: Runtime difference sign
# ---------------------------------------------------------------------------


def test_runtime_difference_unavailable_without_final_selection_report(tmp_path: Path) -> None:
    """headline runtime difference is not set when final_selection_report.json is absent."""

    experiment_dir = _experiment_dir(tmp_path)
    metrics_path = tmp_path / "results" / "runs" / "baseline" / "metrics.json"
    write_json(
        metrics_path,
        {
            "benchmark": {"parsed_runtime_ns_per_problem_median": 100.0},
        },
    )
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(
            original_baseline_metrics_path=str(metrics_path),
            final_best_iteration=1,
            final_speedup_vs_original_baseline=1.25,
            final_runtime_reduction_percent=20.0,
        ),
    )
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "runtime_ns_per_problem_median": 80.0,
                "correctness_passed": True,
                "current_best_updated": True,
            },
        ],
    )

    report_data = collect_report_data(experiment_dir)

    diff = report_data.final_best_candidate.absolute_runtime_difference_ns_per_problem
    assert diff is None


# ---------------------------------------------------------------------------
# Fix 5: _display_path with known relative prefixes
# ---------------------------------------------------------------------------


def test_display_path_known_relative_prefixes(tmp_path: Path) -> None:
    """_display_path preserves known relative prefixes without CWD resolution."""

    import orchestrator.reporting.report_data_collector as rdc

    result = rdc._display_path("results/runs/baseline")
    assert result is not None
    assert "results/runs/baseline" in result
    assert "\\" not in result

    result = rdc._display_path("configs/llm.json")
    assert result is not None
    assert "configs/llm.json" in result

    result = rdc._display_path("cpp/external/lambdatwist/p3p.cc")
    assert result is not None
    assert "cpp/external/lambdatwist/p3p.cc" in result

    result = rdc._display_path("workspace/experiments/x")
    assert result is not None
    assert result.startswith("workspace/experiments/x")
    assert "\\" not in result


# ---------------------------------------------------------------------------
# New narrative fields
# ---------------------------------------------------------------------------


def test_final_code_diff_loaded_when_exists(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    diff_path = experiment_dir / "final_optimized_source.diff"
    diff_path.write_text("--- a/file\n+++ b/file\n@@ -1 +1 @@\n-old\n+new\n", encoding="utf-8")

    report_data = collect_report_data(experiment_dir)

    assert report_data.final_code_diff is not None
    assert "--- a/file" in report_data.final_code_diff
    assert "+new" in report_data.final_code_diff


def test_final_code_diff_loaded_from_summary_path(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    diff_path = tmp_path / "custom" / "final.diff"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(
        "--- a/summary\n+++ b/summary\n-old\n+summary path\n",
        encoding="utf-8",
    )
    fallback_path = experiment_dir / "final_optimized_source.diff"
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    fallback_path.write_text("fallback diff\n", encoding="utf-8")
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(final_optimized_source_diff_path=str(diff_path)),
    )
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.final_code_diff is not None
    assert "summary path" in report_data.final_code_diff
    assert "fallback diff" not in report_data.final_code_diff


def test_final_code_diff_falls_back_when_summary_path_missing(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(final_optimized_source_diff_path="missing/final.diff"),
    )
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    diff_path = experiment_dir / "final_optimized_source.diff"
    diff_path.write_text(
        "--- a/fallback\n+++ b/fallback\n-old\n+fallback\n",
        encoding="utf-8",
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.final_code_diff is not None
    assert "fallback" in report_data.final_code_diff


def test_final_code_diff_none_when_missing(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.final_code_diff is None


def test_executive_narrative_successful_improvement(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(total_iterations=3, completed_iterations=3),
    )
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "runtime_ns_per_problem_median": 800.0,
                "correctness_passed": True,
                "current_best_updated": True,
            },
        ],
    )
    write_json(
        experiment_dir / "experiment_config_snapshot.json",
        {"experiment_name": "speedup test", "llm_config": "mock", "baseline_run_dir": "runs/b"},
    )
    write_json(
        experiment_dir / "resolved_llm_config.json",
        {"provider": "deepseek", "model": "deepseek-v4-pro"},
    )
    write_json(
        experiment_dir / "final_selection_report.json",
        {
            "status": "completed",
            "comparison": {
                "speedup": 1.25,
                "runtime_reduction_percent": 20.0,
                "baseline_runtime_ns_per_problem_median": 1000.0,
                "final_runtime_ns_per_problem_median": 800.0,
            },
            "final_benchmark": {"parsed_correctness_passed": True},
        },
    )

    report_data = collect_report_data(experiment_dir)

    narrative = report_data.executive_narrative
    assert narrative is not None
    assert "deepseek-v4-pro" in narrative
    assert "completed 3 of 3 iterations" in narrative
    assert "1000" in narrative
    assert "800" in narrative
    assert "speedup 1.25x" in narrative
    assert "20.0%" in narrative and "reduction" in narrative
    assert "Correctness was preserved" in narrative
    assert "1 accepted" in narrative


def test_executive_narrative_no_accepted_improvements(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(
            total_iterations=5,
            completed_iterations=5,
            final_best_iteration=0,
            status_counts={
                "accepted_improvement": 0,
                "valid_not_improved": 3,
                "generation_failed": 2,
            },
        ),
    )
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {"iteration": 1, "status": "valid_not_improved"},
            {"iteration": 2, "status": "valid_not_improved"},
            {"iteration": 3, "status": "valid_not_improved"},
            {"iteration": 4, "status": "generation_failed"},
            {"iteration": 5, "status": "generation_failed"},
        ],
    )
    write_json(
        experiment_dir / "resolved_llm_config.json",
        {"provider": "deepseek", "model": "deepseek-v4-pro"},
    )

    report_data = collect_report_data(experiment_dir)

    narrative = report_data.executive_narrative
    assert narrative is not None
    assert "No accepted runtime improvement was found" in narrative
    assert "3 valid but not improved" in narrative
    assert "Pipeline failures" in narrative


def test_executive_narrative_correctness_regression(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    metrics_path = tmp_path / "results" / "runs" / "baseline" / "metrics.json"
    write_json(
        metrics_path,
        {
            "benchmark": {
                "parsed_runtime_ns_per_problem_median": 1000.0,
                "parsed_gt_found_percent": 100.0,
                "parsed_correctness_passed": True,
            },
        },
    )
    write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(
            total_iterations=3,
            completed_iterations=3,
            original_baseline_metrics_path=str(metrics_path),
        ),
    )
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "runtime_ns_per_problem_median": 800.0,
                "correctness_passed": True,
                "gt_found_percent": 90.0,
                "current_best_updated": True,
            },
        ],
    )
    write_json(
        experiment_dir / "resolved_llm_config.json",
        {"provider": "deepseek", "model": "deepseek-v4-pro"},
    )
    write_json(
        experiment_dir / "final_selection_report.json",
        {
            "status": "completed",
            "comparison": {
                "speedup": 1.25,
                "runtime_reduction_percent": 20.0,
                "baseline_runtime_ns_per_problem_median": 1000.0,
                "final_runtime_ns_per_problem_median": 800.0,
                "baseline_gt_found_percent": 100.0,
                "final_gt_found_percent": 90.0,
                "final_gt_found_delta_points": -10.0,
            },
            "final_benchmark": {"parsed_correctness_passed": False},
        },
    )

    report_data = collect_report_data(experiment_dir)

    narrative = report_data.executive_narrative
    assert narrative is not None
    assert "Correctness regressed" in narrative
    assert "GT Found dropped" in narrative


def test_closed_loop_selection_explanation_when_not_matching(
    tmp_path: Path,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 3,
                "status": "valid_not_improved",
                "candidate_summary": "Candidate was faster but not promoted.",
                "outcome_reason": {
                    "category": "decision",
                    "code": "valid_not_improved",
                    "severity": "info",
                    "message": "Not improved over current best.",
                },
            },
        ],
    )
    write_json(
        experiment_dir / "closed_loop_selection_report.json",
        {
            "promotion_policy": "accepted_improvement_only",
            "final_current_best": {"iteration": 1, "is_baseline": False},
            "best_verified_candidate_vs_original_baseline": {
                "iteration": 3,
                "speedup": 1.15,
                "runtime_reduction_percent": 13.0,
                "matches_final_current_best": False,
            },
        },
    )

    report_data = collect_report_data(experiment_dir)

    explanation = report_data.closed_loop_selection_explanation
    assert explanation is not None
    assert "Iteration 3" in explanation
    assert "not promoted" in explanation
    assert "valid_not_improved" in explanation


def test_closed_loop_selection_explanation_none_when_matching(
    tmp_path: Path,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    write_json(
        experiment_dir / "closed_loop_selection_report.json",
        {
            "promotion_policy": "accepted_improvement_only",
            "final_current_best": {"iteration": 1, "is_baseline": False},
            "best_verified_candidate_vs_original_baseline": {
                "iteration": 1,
                "speedup": 1.25,
                "matches_final_current_best": True,
            },
        },
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.closed_loop_selection_explanation is None


def test_closed_loop_selection_explanation_none_when_no_best_verified(
    tmp_path: Path,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.closed_loop_selection_explanation is None


def test_executive_narrative_uses_reason_code_for_fallback(
    tmp_path: Path,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 7,
                "status": "valid_not_improved",
                "failure_reason": "runtime_improvement_below_minimum_threshold",
                "outcome_reason": {
                    "category": "decision",
                    "code": "valid_not_improved",
                },
            },
        ],
    )
    write_json(
        experiment_dir / "closed_loop_selection_report.json",
        {
            "final_current_best": {"iteration": 1, "is_baseline": False},
            "best_verified_candidate_vs_original_baseline": {
                "iteration": 7,
                "speedup": 1.05,
                "matches_final_current_best": False,
            },
        },
    )

    report_data = collect_report_data(experiment_dir)

    explanation = report_data.closed_loop_selection_explanation
    assert explanation is not None
    assert "runtime_improvement_below_minimum_threshold" in explanation


def test_final_code_diff_not_loaded_for_broken_file(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    write_json(experiment_dir / "closed_loop_summary.json", _summary())
    write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.final_code_diff is None
