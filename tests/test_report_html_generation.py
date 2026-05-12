from __future__ import annotations

import json
from pathlib import Path

from orchestrator.reporting import (
    ReportArtifactMap,
    ReportBaselineMetrics,
    ReportFinalResult,
    ReportIterationSummary,
    build_report_figures,
    default_status_counts,
    generate_basic_html_report,
    make_empty_report_data,
    render_report_html,
)


TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"
EXPECTED_PLOTS = {
    "runtime_progress": "runtime_progress.svg",
    "runtime_reduction_by_iteration": "runtime_reduction_by_iteration.svg",
    "correctness_metrics": "correctness_metrics.svg",
    "status_breakdown": "status_breakdown.svg",
    "candidate_funnel": "candidate_funnel.svg",
}


def _report_data() -> object:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.experiment.total_iterations = 2
    report_data.experiment.completed_iterations = 2
    report_data.final_result = ReportFinalResult(
        final_best_iteration=1,
        final_speedup_vs_baseline=1.25,
        final_runtime_reduction_percent=20.0,
        accepted_improvements=1,
        correctness_preserved=True,
    )
    report_data.baseline_metrics = ReportBaselineMetrics(
        runtime_ns_per_case_median=1000.0,
        success_rate=1.0,
        mean_reprojection_error=1.0e-12,
        max_reprojection_error=2.0e-12,
        correctness_passed=True,
    )
    counts = default_status_counts()
    counts["accepted_improvement"] = 1
    counts["valid_not_improved"] = 1
    report_data.status_counts = counts
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            candidate_summary="Simplify arithmetic.",
            runtime_ns_per_case_median=800.0,
            speedup_vs_baseline=1.25,
            correctness_passed=True,
            promoted=True,
            candidate_run_dir="results/runs/candidate_001",
        ),
        ReportIterationSummary(
            iteration=2,
            status="valid_not_improved",
            candidate_summary="Try branch cleanup.",
            runtime_ns_per_case_median=820.0,
            speedup_vs_baseline=1.22,
            correctness_passed=True,
            promoted=False,
            reason="candidate_not_promoted",
            candidate_run_dir="results/runs/candidate_002",
        ),
    ]
    report_data.artifacts = ReportArtifactMap(
        experiment_dir="results/experiments/exp_001",
        report_dir="results/experiments/exp_001/report",
        report_data="results/experiments/exp_001/report/report_data.json",
        report_html="results/experiments/exp_001/report/report.html",
        plots_dir="results/experiments/exp_001/report/plots",
        final_optimized_source="results/experiments/exp_001/final_optimized_source",
        final_diff="results/experiments/exp_001/final_optimized_source.diff",
        closed_loop_summary="results/experiments/exp_001/closed_loop_summary.json",
        closed_loop_iterations="results/experiments/exp_001/closed_loop_iterations.jsonl",
    )
    return report_data


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


def _summary() -> dict:
    return {
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
            "valid_not_improved": 1,
        },
    }


def test_build_report_figures_creates_expected_svg_files(tmp_path: Path) -> None:
    plots_dir = tmp_path / "report" / "plots"

    plot_paths = build_report_figures(_report_data(), plots_dir)

    assert plot_paths == {
        key: f"plots/{filename}" for key, filename in EXPECTED_PLOTS.items()
    }
    for filename in EXPECTED_PLOTS.values():
        path = plots_dir / filename
        assert path.is_file()
        assert path.read_text(encoding="utf-8").lstrip().startswith("<?xml")


def test_build_report_figures_creates_placeholder_svgs_when_data_missing(
    tmp_path: Path,
) -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    plots_dir = tmp_path / "report" / "plots"

    build_report_figures(report_data, plots_dir)

    assert "Runtime data unavailable" in (
        plots_dir / "runtime_progress.svg"
    ).read_text(encoding="utf-8")
    assert "Correctness data unavailable" in (
        plots_dir / "correctness_metrics.svg"
    ).read_text(encoding="utf-8")


def test_render_report_html_creates_report_html(tmp_path: Path) -> None:
    plot_paths = build_report_figures(_report_data(), tmp_path / "report" / "plots")
    output_path = render_report_html(
        _report_data(),
        plot_paths,
        tmp_path / "report" / "report.html",
    )

    assert output_path == tmp_path / "report" / "report.html"
    assert output_path.is_file()


def test_report_html_contains_expected_report_content(tmp_path: Path) -> None:
    report_data = _report_data()
    plot_paths = build_report_figures(report_data, tmp_path / "report" / "plots")
    html_path = render_report_html(
        report_data,
        plot_paths,
        tmp_path / "report" / "report.html",
    )

    html = html_path.read_text(encoding="utf-8")

    assert "exp_001" in html
    assert TARGET_FILE in html
    assert "1.25" in html
    assert "20" in html
    assert "accepted_improvement" in html
    assert "valid_not_improved" in html
    assert "Per-Iteration Table" in html
    assert "Simplify arithmetic." in html
    assert "Artifact Map" in html
    assert "final_optimized_source" in html
    for filename in EXPECTED_PLOTS.values():
        assert f"plots/{filename}" in html


def test_generate_basic_html_report_creates_report_outputs_read_only(
    tmp_path: Path,
) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "exp_001"
    summary_path = experiment_dir / "closed_loop_summary.json"
    iterations_path = experiment_dir / "closed_loop_iterations.jsonl"
    _write_json(summary_path, _summary())
    _write_jsonl(
        iterations_path,
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_summary": "Simplify arithmetic.",
                "runtime_ns_per_case_median": 800.0,
                "speedup_vs_original_baseline": 1.25,
                "correctness_passed": True,
                "current_best_updated": True,
            },
            {
                "iteration": 2,
                "status": "valid_not_improved",
                "runtime_ns_per_case_median": 820.0,
                "speedup_vs_original_baseline": 1.22,
                "correctness_passed": True,
            },
        ],
    )
    summary_before = summary_path.read_text(encoding="utf-8")
    iterations_before = iterations_path.read_text(encoding="utf-8")

    output_path = generate_basic_html_report(experiment_dir)

    assert output_path == experiment_dir / "report" / "report.html"
    assert (experiment_dir / "report" / "report_data.json").is_file()
    assert output_path.is_file()
    for filename in EXPECTED_PLOTS.values():
        assert (experiment_dir / "report" / "plots" / filename).is_file()
    assert summary_path.read_text(encoding="utf-8") == summary_before
    assert iterations_path.read_text(encoding="utf-8") == iterations_before
