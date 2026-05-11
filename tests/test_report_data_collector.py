from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.experiments.closed_loop_state import IterationStatus
from orchestrator.reporting import (
    collect_and_write_report_data,
    collect_report_data,
)


TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


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
        "final_speedup_vs_original_baseline": 1.25,
        "final_runtime_reduction_percent": 20.0,
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
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.experiment.experiment_id == "exp_001"
    assert report_data.experiment.target_file == TARGET_FILE
    assert report_data.experiment.total_iterations == 2
    assert report_data.experiment.completed_iterations == 2
    assert report_data.experiment.closed_loop_enabled is True
    assert report_data.final_result.final_speedup_vs_baseline == 1.25
    assert report_data.final_result.final_runtime_reduction_percent == 20.0
    assert report_data.final_result.accepted_improvements == 1


def test_collect_report_data_maps_iteration_records(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
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
                "runtime_ns_per_case_median": None,
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
    assert failed.runtime_ns_per_case_median is None
    assert failed.reason == "Patch could not be applied."


def test_collect_report_data_extracts_reason_from_decision_lists(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
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


def test_summary_status_counts_are_completed_with_zero_defaults(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    _write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(status_counts={"accepted_improvement": 1}),
    )
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.status_counts == {
        **{status.value: 0 for status in IterationStatus},
        "accepted_improvement": 1,
    }


def test_status_counts_fall_back_to_jsonl_when_summary_has_none(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    summary = _summary()
    summary.pop("status_counts")
    _write_json(experiment_dir / "closed_loop_summary.json", summary)
    _write_jsonl(
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
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    output_path = collect_and_write_report_data(experiment_dir)

    assert output_path == experiment_dir / "report" / "report_data.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["artifacts"]["report_data"].endswith("report_data.json")
    assert payload["artifacts"]["report_html"].endswith("report.html")
    assert payload["artifacts"]["report_pdf"].endswith("report.pdf")
    assert payload["artifacts"]["plots_dir"].endswith("plots")


def test_missing_baseline_metrics_file_keeps_metrics_empty(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    _write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(original_baseline_metrics_path=str(tmp_path / "missing.json")),
    )
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.baseline_metrics.runtime_ns_per_case_median is None
    assert report_data.baseline_metrics.success_rate is None
    assert report_data.baseline_metrics.mean_reprojection_error is None
    assert report_data.baseline_metrics.max_reprojection_error is None
    assert report_data.baseline_metrics.correctness_passed is None


def test_existing_baseline_metrics_are_loaded_best_effort(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    metrics_path = tmp_path / "results" / "runs" / "baseline" / "metrics.json"
    _write_json(
        metrics_path,
        {
            "runtime_ns_per_case_median": 1000.0,
            "success_rate": 1.0,
            "mean_best_reprojection_error": 1.0e-12,
            "max_best_reprojection_error": 2.0e-12,
            "correctness_passed": True,
        },
    )
    _write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(original_baseline_metrics_path=str(metrics_path)),
    )
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.baseline_metrics.runtime_ns_per_case_median == 1000.0
    assert report_data.baseline_metrics.success_rate == 1.0
    assert report_data.baseline_metrics.mean_reprojection_error == 1.0e-12
    assert report_data.baseline_metrics.max_reprojection_error == 2.0e-12
    assert report_data.baseline_metrics.correctness_passed is True


def test_missing_closed_loop_summary_raises_file_not_found(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    with pytest.raises(FileNotFoundError, match="closed_loop_summary.json"):
        collect_report_data(experiment_dir)


def test_missing_closed_loop_iterations_raises_file_not_found(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())

    with pytest.raises(FileNotFoundError, match="closed_loop_iterations.jsonl"):
        collect_report_data(experiment_dir)
