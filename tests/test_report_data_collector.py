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


def test_iteration_metrics_are_enriched_from_verification_json(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": str(candidate_dir),
            },
        ],
    )
    _write_json(
        candidate_dir / "verification.json",
        {
            "benchmark": {
                "parsed_runtime_ns_per_case_median": 777.0,
                "parsed_correctness_passed": True,
            },
        },
    )

    report_data = collect_report_data(experiment_dir)

    iteration = report_data.iterations[0]
    assert iteration.runtime_ns_per_case_median == 777.0
    assert iteration.correctness_passed is True


def test_speedup_and_reason_are_enriched_from_decision_files(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "valid_not_improved",
                "candidate_run_dir": str(candidate_dir),
            },
        ],
    )
    _write_json(
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
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": str(candidate_dir),
            },
        ],
    )
    _write_json(
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


def test_missing_optional_candidate_artifacts_do_not_fail(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    candidate_dir.mkdir(parents=True)
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
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
    assert iteration.runtime_ns_per_case_median is None
    assert iteration.correctness_passed is None
    assert iteration.speedup_vs_baseline is None
    assert iteration.reason is None


def test_bad_optional_candidate_json_does_not_fail(tmp_path: Path) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    candidate_dir = tmp_path / "results" / "runs" / "candidate_001"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "verification.json").write_text("{not json", encoding="utf-8")
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
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

    assert report_data.iterations[0].runtime_ns_per_case_median is None


def test_valid_not_improved_uses_default_reason_when_none_available(
    tmp_path: Path,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
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
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_run_dir": "results/runs/candidate_001",
            },
        ],
    )
    _write_json(
        candidate_dir / "verification.json",
        {"metrics": {"runtime_ns_per_case_median": 615.0}},
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.iterations[0].runtime_ns_per_case_median == 615.0


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
    assert payload["artifacts"]["report_pdf"] is None  # PDF not generated yet
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


# ---------------------------------------------------------------------------
# New tests A–E (v1 cleanup)
# ---------------------------------------------------------------------------


def test_a_collector_fills_config_and_llm_fields(tmp_path: Path) -> None:
    """Collector reads experiment_config_snapshot.json and variant LLM config."""

    experiment_dir = _experiment_dir(tmp_path)
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    _write_json(
        experiment_dir / "experiment_config_snapshot.json",
        {
            "experiment_name": "My Experiment",
            "target_file": TARGET_FILE,
            "candidate_format": {
                "type": "line_range_edits",
                "source_presentation": "line_numbered",
                "require_original_verification": True,
                "allow_exact_search_fallback": False,
            },
            "closed_loop": {"enabled": True},
            "variants": [
                {
                    "variant_id": "deepseek_pro_max",
                    "description": "DeepSeek Pro Max variant",
                    "llm_config": "configs/llm_deepseek_pro_max.json",
                    "iterations": 5,
                }
            ],
            "history_policy": {"enabled": True, "scope": "all"},
            "selection": {"enabled": True, "baseline_run_dir": "results/runs/baseline"},
            "optimization_scope": {"allowed_files": [TARGET_FILE]},
            "reporting": {"enabled": True, "formats": ["html"], "renderer": "auto"},
            "candidate_generation": {"max_source_chars": 32000},
        },
    )

    _write_json(
        experiment_dir / "variant_configs" / "deepseek_pro_max_llm_config.json",
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
    assert report_data.experiment.candidate_format == "line_range_edits"
    assert report_data.experiment.source_presentation == "line_numbered"
    assert report_data.llm.provider == "deepseek"
    assert report_data.llm.model == "deepseek-v4-pro"
    assert report_data.llm.thinking_enabled is True
    assert report_data.llm.thinking_effort == "high"
    assert report_data.llm.max_tokens == 8192
    assert report_data.llm.variant_id == "deepseek_pro_max"


def test_b_collector_fills_benchmark_config(tmp_path: Path) -> None:
    """Collector fills benchmark_config from baseline metrics.json."""

    experiment_dir = _experiment_dir(tmp_path)
    metrics_path = tmp_path / "results" / "runs" / "baseline" / "metrics.json"
    _write_json(
        metrics_path,
        {
            "benchmark": {
                "family": "absolute_pose_solvers",
                "solver": "lambdatwist_p3p",
                "runtime_unit": "ns",
                "build_type": "Release",
                "benchmark_options": {
                    "num_cases": 1024,
                    "points_per_case": 3,
                    "warmup_iterations": 10,
                    "timed_iterations": 50,
                    "random_seed": 42,
                    "reprojection_error_threshold": 1e-6,
                    "min_success_rate": 0.99,
                    "require_all_cases_valid": True,
                    "use_max_reprojection_error_as_hard_gate": False,
                },
                "parsed_runtime_ns_per_case_median": 1000.0,
                "parsed_correctness_passed": True,
            }
        },
    )
    _write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(original_baseline_metrics_path=str(metrics_path)),
    )
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    report_data = collect_report_data(experiment_dir)

    assert report_data.benchmark_config.family == "absolute_pose_solvers"
    assert report_data.benchmark_config.solver == "lambdatwist_p3p"
    assert report_data.benchmark_config.num_cases == 1024
    assert report_data.benchmark_config.timed_iterations == 50
    assert report_data.benchmark_config.seed == 42
    assert report_data.benchmark_config.build_type == "Release"


def test_c_correctness_preserved_from_promoted_iteration(tmp_path: Path) -> None:
    """correctness_preserved is inferred from the promoted iteration with final_best_iteration."""

    experiment_dir = _experiment_dir(tmp_path)
    _write_json(
        experiment_dir / "closed_loop_summary.json",
        _summary(final_best_iteration=2),
    )
    _write_jsonl(
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

    assert report_data.final_result.correctness_preserved is True


def test_d_pdf_display_when_html_only_formats(tmp_path: Path) -> None:
    """pdf_display shows 'Not generated' message when formats=["html"] and no PDF file."""

    experiment_dir = _experiment_dir(tmp_path)
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])
    _write_json(
        experiment_dir / "experiment_config_snapshot.json",
        {
            "experiment_name": "Html Only",
            "target_file": TARGET_FILE,
            "reporting": {"enabled": True, "formats": ["html"], "renderer": "auto"},
            "closed_loop": {"enabled": True},
        },
    )

    report_data = collect_report_data(experiment_dir)

    assert report_data.reporting_status.pdf_generated is False
    assert report_data.reporting_status.report_pdf_path is None
    assert "Not generated" in (report_data.reporting_status.pdf_display or "")
    assert '"html"' in (report_data.reporting_status.pdf_display or "")


def test_e_artifact_paths_end_with_known_segments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Artifact display paths end with expected filenames/dirs.

    When the experiment_dir is under a fake repo root (monkeypatched), display
    paths should be POSIX-relative to that root.
    """

    import orchestrator.reporting.report_data_collector as rdc

    # Make tmp_path the fake repo root so display paths come out relative
    monkeypatch.setattr(rdc, "_REPO_ROOT", tmp_path)

    experiment_dir = _experiment_dir(tmp_path)
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

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
