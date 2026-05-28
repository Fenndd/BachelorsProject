from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

import json
from pathlib import Path

from orchestrator.reporting import (
    ReportArtifactMap,
    ReportBaselineMetrics,
    ReportBenchmarkConfig,
    ReportClosedLoopSelection,
    ReportData,
    ReportDiffStats,
    ReportExperimentConfigDetails,
    ReportExperimentMetadata,
    ReportFinalBestCandidate,
    ReportFinalSelection,
    ReportFinalResult,
    ReportIterationSummary,
    ReportLlmInfo,
    ReportLlmUsage,
    ReportLlmUsageSummary,
    ReportOutcomeReason,
    ReportPhaseTimings,
    ReportReasonCodeCount,
    ReportReasonSummaryItem,
    ReportReportingStatus,
    build_report_figures,
    default_status_counts,
    generate_basic_html_report,
    generate_basic_report,
    make_empty_report_data,
    render_report_html,
)


from orchestrator.tests.conftest import TARGET_FILE
EXPECTED_PLOTS = {
    "runtime_progress": "runtime_progress.svg",
    "runtime_reduction_by_iteration": "runtime_reduction_by_iteration.svg",
    "correctness_metrics": "correctness_metrics.svg",
    "status_breakdown": "status_breakdown.svg",
    "candidate_funnel": "candidate_funnel.svg",
    "phase_timings": "phase_timings.svg",
    "llm_tokens_by_iteration": "llm_tokens_by_iteration.svg",
    "llm_latency_by_iteration": "llm_latency_by_iteration.svg",
    "failure_reason_breakdown": "failure_reason_breakdown.svg",
    "diff_stats_by_iteration": "diff_stats_by_iteration.svg",
}

NEW_SECTION_IDS = (
    "reproducibility-environment",
    "failure-analysis",
    "phase-timings",
    "llm-usage",
    "final-comparison",
    "diff-statistics",
    "iteration-appendix",
)


def _report_data() -> ReportData:
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
        runtime_ns_per_problem_median=1000.0,
        gt_found_percent=100.0,
        valid_solutions_percent=95.0,
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
            runtime_ns_per_problem_median=800.0,
            speedup_vs_baseline=1.25,
            correctness_passed=True,
            promoted=True,
            candidate_run_dir="results/runs/candidate_001",
        ),
        ReportIterationSummary(
            iteration=2,
            status="valid_not_improved",
            candidate_summary="Try branch cleanup.",
            runtime_ns_per_problem_median=820.0,
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
        experiment_metadata="results/experiments/exp_001/experiment_metadata.json",
        closed_loop_selection_report="results/experiments/exp_001/closed_loop_selection_report.json",
    )
    return report_data


def _enriched_report_data() -> ReportData:
    report_data = _report_data()
    report_data.final_best_candidate = ReportFinalBestCandidate(
        iteration=1,
        runtime_ns_per_problem_median=800.0,
        speedup_vs_baseline=1.25,
        diff_stats=ReportDiffStats(
            files_changed=1,
            lines_added=4,
            lines_removed=2,
            changed_blocks=1,
            edit_count=2,
            fallback_used=False,
        ),
    )
    report_data.reason_code_counts = [
        ReportReasonCodeCount(
            category="decision",
            code="valid_not_improved",
            count=1,
            iterations=[2],
        )
    ]
    report_data.iterations[0].phase_timings = ReportPhaseTimings(
        generation_seconds=0.1,
        materialization_seconds=0.2,
        verification_seconds=0.3,
        benchmark_seconds=0.4,
        total_iteration_seconds=1.0,
    )
    report_data.iterations[0].llm_usage = ReportLlmUsage(
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        api_latency_seconds=1.2,
        finish_reason="stop",
        model="mock-model",
    )
    report_data.iterations[0].diff_stats = ReportDiffStats(
        files_changed=1,
        lines_added=4,
        lines_removed=2,
        changed_blocks=1,
        edit_count=2,
        fallback_used=False,
    )
    report_data.iterations[0].outcome_reason = ReportOutcomeReason(
        category="decision",
        code="accepted_improvement",
        message="Candidate improved the current best runtime.",
    )
    report_data.iterations[1].phase_timings = ReportPhaseTimings(
        generation_seconds=0.2,
        materialization_seconds=0.1,
        verification_seconds=0.3,
        total_iteration_seconds=0.6,
    )
    report_data.iterations[1].llm_usage = ReportLlmUsage(
        prompt_tokens=120,
        completion_tokens=40,
        total_tokens=160,
        api_latency_seconds=1.4,
        finish_reason="stop",
        model="mock-model",
    )
    report_data.iterations[1].diff_stats = ReportDiffStats(
        files_changed=1,
        lines_added=1,
        lines_removed=1,
        changed_blocks=1,
        edit_count=1,
        fallback_used=True,
    )
    report_data.iterations[1].outcome_reason = ReportOutcomeReason(
        category="decision",
        code="valid_not_improved",
        message="Candidate was correct but slower than the current best.",
    )
    report_data.llm_usage_summary = ReportLlmUsageSummary(
        prompt_tokens_total=220,
        completion_tokens_total=90,
        total_tokens=310,
        api_latency_seconds_total=2.6,
        api_latency_seconds_average=1.3,
        iterations_with_usage=2,
        most_expensive_iteration=2,
        highest_latency_iteration=2,
    )
    report_data.experiment_metadata = ReportExperimentMetadata(
        repository={
            "git_commit": "abc123",
            "git_branch": "reportUpdatev2v3",
            "dirty_worktree": False,
        },
        environment={
            "os": "nt",
            "platform": "Windows-test",
            "python_version": "3.12",
            "cmake_build_type": "Release",
            "cmake_exe": "cmake",
            "cmake_generator": "Ninja",
            "cxx_compiler": "clang++",
        },
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

    assert "Current best runtime data unavailable" in (
        plots_dir / "runtime_progress.svg"
    ).read_text(encoding="utf-8")
    assert "Correctness data unavailable" in (
        plots_dir / "correctness_metrics.svg"
    ).read_text(encoding="utf-8")
    assert "Phase timing data unavailable" in (
        plots_dir / "phase_timings.svg"
    ).read_text(encoding="utf-8")
    assert "LLM token usage data unavailable" in (
        plots_dir / "llm_tokens_by_iteration.svg"
    ).read_text(encoding="utf-8")
    assert "LLM latency data unavailable" in (
        plots_dir / "llm_latency_by_iteration.svg"
    ).read_text(encoding="utf-8")
    assert "Failure reason data unavailable" in (
        plots_dir / "failure_reason_breakdown.svg"
    ).read_text(encoding="utf-8")
    assert "Diff statistics unavailable" in (
        plots_dir / "diff_stats_by_iteration.svg"
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
    assert "experiment_metadata" in html
    assert "closed_loop_selection_report" in html
    for section_id in NEW_SECTION_IDS:
        assert f'id="{section_id}"' in html
    for filename in EXPECTED_PLOTS.values():
        assert f"plots/{filename}" in html


def test_report_html_contains_enriched_sections(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    plot_paths = build_report_figures(report_data, tmp_path / "report" / "plots")
    html_path = render_report_html(
        report_data,
        plot_paths,
        tmp_path / "report" / "report.html",
    )

    html = html_path.read_text(encoding="utf-8")

    for section_id in NEW_SECTION_IDS:
        assert f'id="{section_id}"' in html
    assert 'id="failure-analysis"' in html
    assert "Outcome and Failure Analysis" in html
    assert "Phase Timings" in html
    assert "LLM Usage" in html
    assert "Total Tokens" in html
    assert "310" in html
    assert "Diff Statistics" in html
    assert "Iteration Appendix" in html
    assert "Reproducibility and Environment" in html
    assert "reportUpdatev2v3" in html
    assert "valid_not_improved" in html
    assert "mock-model" in html
    assert "Candidate improved the current best runtime." in html
    assert "reports/runs" not in html
    assert "Benchmark s" not in html


def test_report_html_handles_older_missing_enriched_fields(tmp_path: Path) -> None:
    report_data = {
        "schema_version": "report.v1",
        "report_metadata": {"report_profile": "basic_single_experiment"},
        "experiment": {"experiment_id": "exp_old", "target_file": TARGET_FILE},
        "final_result": {},
        "baseline_metrics": {},
        "iterations": [
            {
                "iteration": 1,
                "status": "valid_not_improved",
                "candidate_summary": "Old artifact without enriched fields.",
            }
        ],
        "status_counts": {"valid_not_improved": 1},
        "artifacts": {},
    }
    plot_paths = build_report_figures(report_data, tmp_path / "report" / "plots")
    html_path = render_report_html(
        report_data,
        plot_paths,
        tmp_path / "report" / "report.html",
    )

    html = html_path.read_text(encoding="utf-8")

    assert "exp_old" in html
    assert "Old artifact without enriched fields." in html
    assert "No structured outcome reasons are available" in html
    assert "\u2014" in html
    for section_id in NEW_SECTION_IDS:
        assert f'id="{section_id}"' in html


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
                "runtime_ns_per_problem_median": 800.0,
                "speedup_vs_original_baseline": 1.25,
                "correctness_passed": True,
                "current_best_updated": True,
            },
            {
                "iteration": 2,
                "status": "valid_not_improved",
                "runtime_ns_per_problem_median": 820.0,
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


def test_f_html_contains_enriched_fields(tmp_path: Path) -> None:
    """Rendered HTML surfaces model, benchmark, selection, final-best, and PDF status."""

    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.experiment.model = "deepseek-v4-pro"
    report_data.experiment.benchmark_family = "absolute_pose_solvers"
    report_data.final_result = ReportFinalResult(
        final_best_iteration=1,
        final_speedup_vs_baseline=1.30,
        final_runtime_reduction_percent=23.0,
        accepted_improvements=1,
        correctness_preserved=True,
    )
    report_data.baseline_metrics = ReportBaselineMetrics(
        runtime_ns_per_problem_median=1000.0,
        correctness_passed=True,
    )
    report_data.llm = ReportLlmInfo(
        provider="deepseek",
        model="deepseek-v4-pro",
        thinking_enabled=True,
        thinking_effort="high",
        max_tokens=8192,
    )
    report_data.experiment_config_details = ReportExperimentConfigDetails(
        baseline_run_dir="results/runs/baseline",
    )
    report_data.benchmark_config = ReportBenchmarkConfig(
        family="absolute_pose_solvers",
        solver="lambdatwist_p3p",
        num_problems=1024,
        timed_iterations=50,
        build_type="Release",
    )
    report_data.closed_loop_selection = ReportClosedLoopSelection(
        promotion_policy="decision_vs_current_best.accepted_improvement_only",
        final_current_best_iteration=1,
        final_current_best_is_baseline=False,
    )
    report_data.final_best_candidate = ReportFinalBestCandidate(
        iteration=1,
        speedup_vs_baseline=1.30,
        runtime_reduction_percent=23.0,
        correctness_passed=True,
        candidate_summary="Optimized hot loop.",
        final_optimized_source="results/experiments/exp_001/final_optimized_source",
    )
    report_data.reporting_status = ReportReportingStatus(
        enabled=True,
        status="completed",
        formats=["html"],
        pdf_generated=False,
        pdf_display='Not generated. Current reporting formats: ["html"]',
    )
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            candidate_summary="Optimized hot loop.",
            speedup_vs_current_best=1.30,
            speedup_vs_baseline=1.30,
            expected_effect="decrease",
            risk_level="low",
            correctness_passed=True,
            promoted=True,
        )
    ]

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "deepseek-v4-pro" in html
    assert "absolute_pose_solvers" in html
    assert "lambdatwist_p3p" in html
    assert "Speedup vs Current Best" in html
    assert "Closed-Loop Selection" in html
    assert "single-run selection analytics from per-iteration candidate verification" in html
    assert "Best Verified Candidate Single-Run Speedup vs Baseline" in html
    assert "Best Verified Candidate Single-Run Runtime Reduction %" in html
    assert "Promotion Policy" in html
    assert "decision_vs_current_best.accepted_improvement_only" in html
    assert "Selection Enabled" not in html
    assert "History Policy Enabled" not in html
    assert "Final Best Candidate" in html
    assert "Candidate runtime fields in this section reflect the final single-run comparison against the original baseline" in html
    assert "Not generated" in html
    # correctness_preserved rendered as Yes/No
    assert "Yes" in html


def test_g_html_does_not_contain_manual_prose_paragraphs(tmp_path: Path) -> None:
    """The HTML template must not contain hand-written explanatory paragraphs."""

    report_data = _report_data()
    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "This report describes" not in html
    assert "The final promoted version" not in html
    assert "All benchmarked non-no-op candidates" not in html


def test_runtime_progress_uses_current_best_step_plot(tmp_path: Path) -> None:
    """runtime_progress.svg reflects current-best runtime, not raw candidate runtime."""

    report_data = make_empty_report_data("exp_002", TARGET_FILE)
    report_data.baseline_metrics = ReportBaselineMetrics(runtime_ns_per_problem_median=100.0)
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            runtime_ns_per_problem_median=90.0,
            promoted=True,
        ),
        ReportIterationSummary(
            iteration=2,
            status="valid_not_improved",
            runtime_ns_per_problem_median=95.0,
            promoted=False,
        ),
        ReportIterationSummary(
            iteration=3,
            status="accepted_improvement",
            runtime_ns_per_problem_median=80.0,
            promoted=True,
        ),
    ]
    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_path = plots_dir / "runtime_progress.svg"
    assert svg_path.is_file()
    svg_text = svg_path.read_text(encoding="utf-8")
    assert svg_text.strip() != ""
    assert "Runtime Progress" in svg_text
    assert "baseline" in svg_text
    assert "current best" in svg_text


def test_runtime_progress_placeholder_when_no_runtime_data(tmp_path: Path) -> None:
    """runtime_progress.svg shows placeholder when no baseline and no promoted runtime."""

    report_data = make_empty_report_data("exp_003", TARGET_FILE)
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="valid_not_improved",
            runtime_ns_per_problem_median=None,
            promoted=False,
        ),
    ]
    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_text = (plots_dir / "runtime_progress.svg").read_text(encoding="utf-8")
    assert "Current best runtime data unavailable" in svg_text


def test_combined_runtime_plot_includes_scatter_by_status(tmp_path: Path) -> None:
    """runtime_progress.svg combines step line and scatter with semantic colors."""

    report_data = make_empty_report_data("exp_004", TARGET_FILE)
    report_data.baseline_metrics = ReportBaselineMetrics(runtime_ns_per_problem_median=100.0)
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            runtime_ns_per_problem_median=90.0,
            promoted=True,
        ),
        ReportIterationSummary(
            iteration=2,
            status="valid_not_improved",
            runtime_ns_per_problem_median=95.0,
            promoted=False,
        ),
        ReportIterationSummary(
            iteration=3,
            status="rejected",
            runtime_ns_per_problem_median=105.0,
            promoted=False,
        ),
        ReportIterationSummary(
            iteration=4,
            status="generation_failed",
            promoted=False,
        ),
    ]
    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_path = plots_dir / "runtime_progress.svg"
    assert svg_path.is_file()
    svg_text = svg_path.read_text(encoding="utf-8")

    assert "Runtime Progress" in svg_text
    assert "baseline" in svg_text
    assert "current best" in svg_text

    assert "accepted_improvement" in svg_text
    assert "valid_not_improved" in svg_text
    assert "rejected" in svg_text
    assert "generation_failed" not in svg_text


def test_combined_runtime_plot_works_without_baseline(tmp_path: Path) -> None:
    """runtime_progress.svg works when baseline is missing but iterations have data."""

    report_data = make_empty_report_data("exp_005", TARGET_FILE)
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            runtime_ns_per_problem_median=90.0,
            promoted=True,
        ),
        ReportIterationSummary(
            iteration=2,
            status="valid_not_improved",
            runtime_ns_per_problem_median=85.0,
            promoted=True,
        ),
    ]
    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_path = plots_dir / "runtime_progress.svg"
    assert svg_path.is_file()
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "Runtime Progress" in svg_text
    assert "current best" in svg_text


def test_candidate_runtime_by_iteration_not_generated(tmp_path: Path) -> None:
    """candidate_runtime_by_iteration.svg is no longer generated."""

    from orchestrator.reporting.figure_builder import PLOT_FILENAMES

    assert "candidate_runtime_by_iteration" not in PLOT_FILENAMES
    assert "candidate_runtime_by_iteration.svg" not in PLOT_FILENAMES.values()

    report_data = _report_data()
    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    assert not (plots_dir / "candidate_runtime_by_iteration.svg").exists()


def test_runtime_reduction_uses_semantic_colors(tmp_path: Path) -> None:
    """runtime_reduction_by_iteration.svg uses semantic status colors."""

    report_data = make_empty_report_data("exp_006", TARGET_FILE)
    report_data.baseline_metrics = ReportBaselineMetrics(runtime_ns_per_problem_median=100.0)
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            runtime_ns_per_problem_median=90.0,
            speedup_vs_baseline=1.11,
            promoted=True,
        ),
        ReportIterationSummary(
            iteration=2,
            status="valid_not_improved",
            runtime_ns_per_problem_median=95.0,
            speedup_vs_baseline=1.05,
            promoted=False,
        ),
    ]
    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_path = plots_dir / "runtime_reduction_by_iteration.svg"
    assert svg_path.is_file()
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "Runtime Reduction by Iteration" in svg_text
    assert "baseline (1.0)" in svg_text


def test_status_breakdown_uses_semantic_colors(tmp_path: Path) -> None:
    """Status breakdown bars use semantic status colors."""

    report_data = make_empty_report_data("exp_007", TARGET_FILE)
    counts = default_status_counts()
    counts["accepted_improvement"] = 1
    counts["valid_not_improved"] = 1
    counts["rejected"] = 1
    report_data.status_counts = counts

    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_path = plots_dir / "status_breakdown.svg"
    assert svg_path.is_file()
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "Status Breakdown" in svg_text


def test_report_html_includes_reason_summary_and_new_plot(tmp_path: Path) -> None:
    """Generated HTML contains reason summary, new plot, and key section headings."""

    report_data = _report_data()
    report_data.reason_summary = [
        ReportReasonSummaryItem(reason="runtime_not_improved", count=1, iterations=[2]),
    ]
    report_data.reporting_status = ReportReportingStatus(
        enabled=True,
        status="completed",
        formats=["html"],
        pdf_generated=False,
        pdf_display='Not generated. Current reporting formats: ["html"]',
    )
    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Reason Summary" in html
    assert "Speedup vs Current Best" in html
    assert "Closed-Loop Selection" in html
    assert "Final Best Candidate Summary" in html
    assert "Not generated" in html
    # Must not contain explanatory prose
    assert "This report describes" not in html
    assert "The final promoted version" not in html
    assert "All benchmarked non-no-op candidates" not in html
    # Must not leak absolute temp path into HTML body
    assert str(tmp_path) not in html


def test_iteration_appendix_appears_after_artifact_map(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert html.index('id="artifact-map"') < html.index('id="iteration-appendix"')


def test_report_template_packaging_renders_real_template(tmp_path: Path) -> None:
    """report.html.j2 exists on disk and generate_basic_report renders report.html."""

    from pathlib import Path as _Path
    template_path = _Path(__file__).resolve().parents[2] / "orchestrator" / "reporting" / "templates" / "report.html.j2"
    assert template_path.is_file(), f"Template missing: {template_path}"

    experiment_dir = tmp_path / "results" / "experiments" / "exp_tpl"
    _write_json(
        experiment_dir / "closed_loop_summary.json",
        {
            "experiment_id": "exp_tpl",
            "target_file": TARGET_FILE,
            "total_iterations": 1,
            "completed_iterations": 1,
            "original_baseline_metrics_path": "missing.json",
            "final_best_iteration": 0,
            "status_counts": {"accepted_improvement": 0},
        },
    )
    _write_jsonl(experiment_dir / "closed_loop_iterations.jsonl", [])

    artifacts = generate_basic_report(experiment_dir, formats=("html",))

    html_path = artifacts["html"]
    assert html_path.is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "exp_tpl" in html
    payload = json.loads((experiment_dir / "report" / "report_data.json").read_text(encoding="utf-8"))
    assert payload["reporting_status"]["status"] == "completed"
    assert payload["reporting_status"]["pdf_generated"] is False
    assert payload["reporting_status"]["pdf_display"] == 'Not generated. Current reporting formats: ["html"]'
    assert "<th>Status</th><td>completed</td>" in html
    assert "PDF requested" not in payload["reporting_status"]["pdf_display"]


def test_phase_timings_chart_still_generated_without_benchmark_column(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    plots_dir = tmp_path / "plots"
    plot_paths = build_report_figures(report_data, plots_dir)
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")

    assert (plots_dir / "phase_timings.svg").is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "Benchmark s" not in html
    assert "Verification time includes build" in html
    assert 'colspan="6"' not in html


def test_html_contains_final_comparison_section_and_llm_kpis(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.llm_usage_summary = ReportLlmUsageSummary(
        total_tokens=100,
        most_expensive_iteration=2,
        highest_latency_iteration=1,
    )
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        final_best_is_baseline=False,
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        baseline_runtime_ns_per_problem_median=100.0,
        final_runtime_ns_per_problem_median=80.0,
        final_correctness_passed=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert 'id="final-comparison"' in html
    assert "Speedup vs Original Baseline" in html
    assert "Runtime Reduction %" in html
    assert "Final Correctness Passed" in html
    assert "Most Expensive Iteration" in html
    assert "Highest Latency Iteration" in html


def test_executive_summary_uses_final_selection_baseline_runtime(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_result.final_speedup_vs_baseline = 1.25
    report_data.final_result.final_runtime_reduction_percent = 20.0
    report_data.final_best_candidate = ReportFinalBestCandidate(
        baseline_runtime_ns_per_problem_median=900.0,
        runtime_ns_per_problem_median=700.0,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")
    executive = html.split('id="experiment-configuration"', 1)[0]

    assert "Baseline Runtime ns/problem</strong>900" in executive
    assert "Final Best Runtime ns/problem</strong>700" in executive
    assert "Baseline Runtime ns/problem</strong>1000" not in executive


def test_executive_summary_not_available_when_final_selection_metrics_null(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_result.final_speedup_vs_baseline = None
    report_data.final_result.final_runtime_reduction_percent = None
    report_data.final_result.correctness_preserved = None
    report_data.final_best_candidate = ReportFinalBestCandidate()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")
    executive = html.split('id="experiment-configuration"', 1)[0]

    assert "Final Selection Speedup</strong>\u2014" in executive
    assert "Final Selection Runtime Reduction %</strong>\u2014" in executive
    assert "Correctness Preserved</strong>\u2014" in executive
    assert "Headline performance metrics are unavailable" in executive


def test_final_comparison_html_not_available_message(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")
    final_comparison = html.split('id="final-comparison"', 1)[1].split(
        'id="baseline-metrics"', 1
    )[0]

    assert "Final single-run comparison was not available" in final_comparison


def test_final_comparison_html_failed_message(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_selection = ReportFinalSelection(status="failed")

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")
    final_comparison = html.split('id="final-comparison"', 1)[1].split(
        'id="baseline-metrics"', 1
    )[0]

    assert "Final single-run comparison failed" in final_comparison


def test_final_validation_runtime_distribution_plot_not_generated(tmp_path: Path) -> None:
    report_data = _report_data()
    plots_dir = tmp_path / "plots"

    build_report_figures(report_data, plots_dir)

    assert not (plots_dir / "final_validation_runtime_distribution.svg").exists()


# ---------------------------------------------------------------------------
# Fix 4: Runtime Improvement label in HTML
# ---------------------------------------------------------------------------


def test_html_contains_runtime_improvement_label(tmp_path: Path) -> None:
    """HTML renders 'Runtime Improvement ns/problem' label with positive value."""

    report_data = _report_data()
    report_data.final_best_candidate = ReportFinalBestCandidate(
        iteration=1,
        runtime_ns_per_problem_median=80.0,
        baseline_runtime_ns_per_problem_median=100.0,
        absolute_runtime_difference_ns_per_problem=20.0,
        speedup_vs_baseline=1.25,
    )
    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Runtime Improvement ns/problem" in html
    assert "20" in html


# ---------------------------------------------------------------------------
# Fix 6: List fields render cleanly (not Python repr)
# ---------------------------------------------------------------------------


def test_list_fields_render_as_comma_separated(tmp_path: Path) -> None:
    """List fields in HTML display as comma-separated, not Python list syntax."""

    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.experiment.total_iterations = 1
    report_data.experiment.completed_iterations = 1
    report_data.baseline_metrics = ReportBaselineMetrics(
        runtime_ns_per_problem_median=100.0,
        correctness_passed=True,
    )
    report_data.reporting_status = ReportReportingStatus(
        enabled=True,
        status="completed",
        formats=["html"],
        pdf_generated=False,
        pdf_display='Not generated. Current reporting formats: ["html"]',
    )
    report_data.experiment_config_details = ReportExperimentConfigDetails(
        optimization_scope_allowed_files=["cpp/external/lambdatwist/p3p.cc"],
    )
    report_data.final_best_candidate = ReportFinalBestCandidate(
        changed_files=["cpp/external/lambdatwist/p3p.cc"],
    )
    counts = default_status_counts()
    counts["accepted_improvement"] = 1
    report_data.status_counts = counts

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "html" in html
    assert "cpp/external/lambdatwist/p3p.cc" in html
    assert "['html']" not in html
    assert "['cpp/external/lambdatwist/p3p.cc']" not in html


# ---------------------------------------------------------------------------
# Fix 7: Empty reason_summary hides the section
# ---------------------------------------------------------------------------


def test_reason_summary_section_absent_when_empty(tmp_path: Path) -> None:
    """Reason Summary section is not rendered when reason_summary is empty."""

    report_data = _report_data()
    report_data.reason_summary = []

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Reason Summary" not in html


def test_reason_summary_section_present_when_nonempty(tmp_path: Path) -> None:
    """Reason Summary section is rendered when reason_summary has entries."""

    report_data = _report_data()
    report_data.reason_summary = [
        ReportReasonSummaryItem(reason="runtime_not_improved", count=1, iterations=[2]),
    ]
    report_data.reporting_status = ReportReportingStatus(
        enabled=True,
        status="completed",
        formats=["html"],
        pdf_generated=False,
        pdf_display='Not generated. Current reporting formats: ["html"]',
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Reason Summary" in html
    assert "runtime_not_improved" in html
