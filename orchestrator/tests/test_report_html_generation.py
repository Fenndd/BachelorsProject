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
from orchestrator.reporting.figure_builder import PLOT_FILENAMES


from orchestrator.tests.conftest import TARGET_FILE

EXPECTED_PLOTS = PLOT_FILENAMES

NEW_SECTION_IDS = (
    "executive-summary",
    "setup",
    "final-result",
    "optimization-process",
    "iteration-outcomes",
    "cost-performance-profile",
    "reproducibility",
    "appendix",
)

OLD_SECTION_IDS = (
    "cover",
    "reporting-status",
    "artifact-map",
    "reason-summary",
    "final-comparison",
    "baseline-metrics",
    "final-best-candidate-summary",
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
    assert "Per-Iteration Summary" in html
    assert "Simplify arithmetic." in html
    for section_id in NEW_SECTION_IDS:
        assert f'id="{section_id}"' in html
    for section_id in OLD_SECTION_IDS:
        assert f'id="{section_id}"' not in html
    for filename in EXPECTED_PLOTS.values():
        assert f"plots/{filename}" in html
    assert "candidate_runtime_by_iteration" not in html
    assert "Not available" not in html


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
    assert "Iteration Outcomes" in html
    assert "Cost &amp; Performance Profile" in html
    assert "Total Tokens" in html
    assert "310" in html
    assert "Final Diff Statistics" in html
    assert "Selected Iteration Details" in html
    assert "Reproducibility" in html
    assert "valid_not_improved" in html
    assert "Candidate improved the current best runtime." in html
    assert "reports/runs" not in html
    assert "Benchmark s" not in html
    assert "Not available" not in html


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
    assert "\u2014" in html
    for section_id in NEW_SECTION_IDS:
        assert f'id="{section_id}"' in html
    for section_id in OLD_SECTION_IDS:
        assert f'id="{section_id}"' not in html
    assert "Not available" not in html


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
    report_data.experiment.benchmark_family = "poselib_native"
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
        family="poselib_native",
        solver="poselib_p3p_lambdatwist",
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
            correctness_passed=True,
            promoted=True,
        )
    ]

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "deepseek-v4-pro" in html
    assert "poselib_native" in html
    assert "poselib_p3p_lambdatwist" in html
    assert "Speedup vs Current Best" in html
    assert "Closed-Loop Selection" in html
    assert "Best Verified Candidate Speedup vs Baseline" in html
    assert "Promotion Policy" in html
    assert "decision_vs_current_best.accepted_improvement_only" in html
    assert "Selection Enabled" not in html
    assert "History Policy Enabled" not in html
    assert "Final Best Candidate" in html
    # correctness_preserved rendered as Yes/No
    assert "Yes" in html
    assert "Not available" not in html


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




def test_report_html_includes_reason_codes_and_final_sections(tmp_path: Path) -> None:
    """Generated HTML contains reason codes, plots, and final section headings."""

    report_data = _report_data()
    report_data.reason_code_counts = [
        ReportReasonCodeCount(
            category="decision",
            code="runtime_not_improved",
            count=1,
            iterations=[2],
        ),
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

    assert "Iteration Outcome Codes" in html
    assert "runtime_not_improved" in html
    assert "Speedup vs Current Best" in html
    assert "Closed-Loop Selection" in html
    assert "Final Best Candidate" in html
    # Must not contain explanatory prose
    assert "This report describes" not in html
    assert "The final promoted version" not in html
    assert "All benchmarked non-no-op candidates" not in html
    # Must not leak absolute temp path into HTML body
    assert str(tmp_path) not in html
    assert "Not available" not in html


def test_appendix_contains_final_diff_area_after_iteration_outcomes(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert html.index('id="iteration-outcomes"') < html.index('id="appendix"')
    assert 'id="final-code-diff"' in html
    assert 'id="artifact-map"' not in html
    assert 'id="iteration-appendix"' not in html


def test_final_code_diff_is_visible_for_print_output(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    report_data.final_code_diff = "--- a/file.cc\n+++ b/file.cc\n@@ -1 +1 @@\n-old\n+new\n"

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert 'id="final-code-diff"' in html
    assert "<details open>" not in html
    assert 'class="screen-only"' in html
    assert 'class="print-only"' in html
    assert "View final diff" in html
    assert "old" in html
    assert "new" in html
    assert "Final optimized source diff was not available" not in html
    assert "Not available" not in html


def test_optional_empty_report_rows_are_hidden(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.benchmark_config = ReportBenchmarkConfig(
        family="poselib_native",
        solver="poselib_p3p_lambdatwist",
        build_type="Release",
    )
    report_data.experiment_metadata = ReportExperimentMetadata(
        repository={"git_commit": "abc123"},
        environment={"python_version": "3.12"},
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Experiment ID" in html
    assert "Target File" in html
    assert "Timed Iterations" not in html
    assert "Seed" not in html
    assert "Tolerance" not in html
    assert "Camera FOV" not in html
    assert "Started At" not in html
    assert "Finished At" not in html
    assert "CMake Executable" not in html
    assert "CMake Generator" not in html
    assert "C++ Compiler" not in html


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
    for section_id in NEW_SECTION_IDS:
        assert f'id="{section_id}"' in html
    payload = json.loads((experiment_dir / "report" / "report_data.json").read_text(encoding="utf-8"))
    assert payload["reporting_status"]["status"] == "completed"
    assert payload["reporting_status"]["pdf_generated"] is False
    assert payload["reporting_status"]["pdf_display"] == 'Not generated. Current reporting formats: ["html"]'
    assert "Not generated" not in html
    assert "Not available" not in html
    assert "PDF requested" not in payload["reporting_status"]["pdf_display"]


def test_phase_timings_chart_still_generated_without_benchmark_column(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    plots_dir = tmp_path / "plots"
    plot_paths = build_report_figures(report_data, plots_dir)
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")

    assert (plots_dir / "phase_timings.svg").is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "Benchmark s" not in html
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

    assert 'id="final-result"' in html
    assert "Speedup vs Original Baseline" in html
    assert "Runtime Reduction" in html
    assert "Correctness Passed" in html
    assert "Most Expensive Iteration" in html
    assert "Highest Latency Iteration" in html


def test_final_result_uses_final_best_runtime_fallback(tmp_path: Path) -> None:
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
    final_result = html.split('id="final-result"', 1)[1].split(
        'id="optimization-process"', 1
    )[0]

    assert "900" in final_result
    assert "700" in final_result
    assert "1000" not in final_result


def test_executive_summary_not_available_when_final_selection_metrics_null(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_result.final_speedup_vs_baseline = None
    report_data.final_result.final_runtime_reduction_percent = None
    report_data.final_result.correctness_preserved = None
    report_data.final_best_candidate = ReportFinalBestCandidate()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")
    executive = html.split('id="setup"', 1)[0]
    final_result = html.split('id="final-result"', 1)[1].split(
        'id="optimization-process"', 1
    )[0]

    assert "Speedup vs Baseline" in executive
    assert "Runtime Reduction" in executive
    assert "Correctness Preserved" in executive
    assert "Final repeated-median comparison metrics are unavailable" in final_result
    assert "Not available" not in html


def test_final_result_html_missing_metrics_message(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")
    final_result = html.split('id="final-result"', 1)[1].split(
        'id="optimization-process"', 1
    )[0]

    assert "Final repeated-median comparison metrics are unavailable" in final_result


def test_final_result_html_failed_message(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_selection = ReportFinalSelection(status="failed")

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")
    final_result = html.split('id="final-result"', 1)[1].split(
        'id="optimization-process"', 1
    )[0]

    assert "because the final selection report failed" in final_result


def test_final_validation_runtime_distribution_plot_not_generated(tmp_path: Path) -> None:
    report_data = _report_data()
    plots_dir = tmp_path / "plots"

    build_report_figures(report_data, plots_dir)

    assert not (plots_dir / "final_validation_runtime_distribution.svg").exists()


# ---------------------------------------------------------------------------
# Fix 4: Runtime Delta label in HTML
# ---------------------------------------------------------------------------


def test_html_contains_runtime_improvement_label(tmp_path: Path) -> None:
    """HTML renders 'Runtime Delta, ns/problem' label with positive value."""

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

    assert "Runtime Delta, ns/problem" in html
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
        optimization_scope_allowed_files=["cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"],
    )
    report_data.final_best_candidate = ReportFinalBestCandidate(
        changed_files=["cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"],
    )
    counts = default_status_counts()
    counts["accepted_improvement"] = 1
    report_data.status_counts = counts

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "html" in html
    assert "cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc" in html
    assert "['html']" not in html
    assert "['cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc']" not in html


# ---------------------------------------------------------------------------
# Fix 7: reason_summary is not rendered as a standalone section
# ---------------------------------------------------------------------------


def test_reason_summary_section_absent_when_empty(tmp_path: Path) -> None:
    """Reason Summary section is not rendered when reason_summary is empty."""

    report_data = _report_data()
    report_data.reason_summary = []

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Reason Summary" not in html


def test_reason_summary_section_absent_when_nonempty(tmp_path: Path) -> None:
    """Reason Summary is no longer rendered as a standalone report section."""

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

    assert "Reason Summary" not in html
    assert "runtime_not_improved" not in html
    assert 'id="reason-summary"' not in html


# ---------------------------------------------------------------------------
# correctness_metrics plot - GT Found % (item 1)
# ---------------------------------------------------------------------------


def test_correctness_metrics_uses_gt_found_percent(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.experiment.total_iterations = 3
    report_data.experiment.completed_iterations = 3
    report_data.baseline_metrics = ReportBaselineMetrics(
        runtime_ns_per_problem_median=100.0,
        gt_found_percent=95.0,
        correctness_passed=True,
    )
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            runtime_ns_per_problem_median=90.0,
            gt_found_percent=94.0,
            correctness_passed=True,
            promoted=True,
        ),
        ReportIterationSummary(
            iteration=2,
            status="valid_not_improved",
            runtime_ns_per_problem_median=88.0,
            gt_found_percent=93.5,
            correctness_passed=True,
            promoted=False,
        ),
        ReportIterationSummary(
            iteration=3,
            status="rejected",
            runtime_ns_per_problem_median=85.0,
            gt_found_percent=92.0,
            correctness_passed=False,
            promoted=False,
        ),
    ]

    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_path = plots_dir / "correctness_metrics.svg"
    assert svg_path.is_file()
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "GT Found %" in svg_text
    assert "baseline" in svg_text
    assert "95" in svg_text


def test_correctness_metrics_fallback_to_pass_fail(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.experiment.total_iterations = 2
    report_data.experiment.completed_iterations = 2
    report_data.baseline_metrics = ReportBaselineMetrics(
        runtime_ns_per_problem_median=100.0,
        correctness_passed=True,
    )
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            runtime_ns_per_problem_median=90.0,
            correctness_passed=True,
            promoted=True,
        ),
        ReportIterationSummary(
            iteration=2,
            status="verification_failed",
            correctness_passed=False,
            promoted=False,
        ),
    ]

    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_path = plots_dir / "correctness_metrics.svg"
    svg_text = svg_path.read_text(encoding="utf-8")
    assert "Pass" in svg_text or "Fail" in svg_text
    assert "GT Found %" not in svg_text


# ---------------------------------------------------------------------------
# GT Found Δ KPI (item 8)
# ---------------------------------------------------------------------------


def test_gt_found_delta_kpi_present(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        final_best_is_baseline=False,
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        final_gt_found_delta_points=-2.5,
        final_correctness_passed=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "GT Found Δ" in html
    assert "-2.50" in html
    assert "pp" in html


def test_gt_found_delta_kpi_hidden_when_missing(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "GT Found Δ" not in html


def test_gt_found_delta_kpi_fallback_to_final_best_candidate(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_best_candidate = ReportFinalBestCandidate(
        iteration=1,
        runtime_ns_per_problem_median=800.0,
        speedup_vs_baseline=1.25,
        gt_found_delta_points=-1.0,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "GT Found Δ" in html
    assert "-1.00" in html


# ---------------------------------------------------------------------------
# GT Found Max Drop Points conditional (item 7)
# ---------------------------------------------------------------------------


def test_gt_found_max_drop_hidden_when_gate_disabled(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.selection_policy.gt_found_gate_enabled = False
    report_data.selection_policy.gt_found_max_drop_points = 5.0

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "GT Found Gate Enabled" in html
    assert "GT Found Max Drop Points" not in html


def test_gt_found_max_drop_shown_when_gate_enabled(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.selection_policy.gt_found_gate_enabled = True
    report_data.selection_policy.gt_found_max_drop_points = 5.0

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "GT Found Max Drop Points" in html


# ---------------------------------------------------------------------------
# Selected Iteration Details empty/filled (item 5)
# ---------------------------------------------------------------------------


def test_selected_iteration_empty_shows_message_no_table(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.experiment.total_iterations = 1
    report_data.experiment.completed_iterations = 1
    report_data.baseline_metrics = ReportBaselineMetrics(
        runtime_ns_per_problem_median=100.0,
        correctness_passed=True,
    )
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="no_op",
            candidate_summary="No changes made.",
            promoted=False,
        ),
    ]

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Selected Iteration Details" in html
    assert "No accepted, failed, or rejected iterations required appendix-level details." in html
    appendix_section = html.split('id="appendix"', 1)[1]
    assert "<table" not in appendix_section


def test_selected_iteration_populated_renders_table(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.iterations[0].outcome_reason = ReportOutcomeReason(
        category="decision",
        code="accepted_improvement",
        message="Candidate improved the current best runtime.",
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Selected Iteration Details" in html
    assert "<thead>" in html
    assert "<table" in html


# ---------------------------------------------------------------------------
# Sticky TOC (item 10)
# ---------------------------------------------------------------------------


def test_sticky_toc_css_present(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "position: sticky" in html
    assert "z-index: 50" in html


# ---------------------------------------------------------------------------
# runtime_ns formatting in per-iteration summary (item 9)
# ---------------------------------------------------------------------------


def test_runtime_ns_applied_in_per_iteration_summary(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.experiment.total_iterations = 1
    report_data.experiment.completed_iterations = 1
    report_data.baseline_metrics = ReportBaselineMetrics(
        runtime_ns_per_problem_median=1000.0,
        correctness_passed=True,
    )
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            runtime_ns_per_problem_median=485.988,
            min_runtime_ns_per_problem_median=400.567,
            speedup_vs_baseline=2.058,
            correctness_passed=True,
            promoted=True,
        ),
    ]

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "485.99" in html
    assert "400.57" in html


# ---------------------------------------------------------------------------
# Iteration Outcomes 2x2 grid (item 12)
# ---------------------------------------------------------------------------


def test_iteration_outcomes_single_column_grid(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    iteration_outcomes_section = html.split('id="iteration-outcomes"', 1)[1].split(
        'id="cost-performance-profile"', 1
    )[0]
    assert "plot-grid-single-column" in iteration_outcomes_section
    assert "plot-grid-two-column" not in iteration_outcomes_section


# ---------------------------------------------------------------------------
# Total Iterations label (item 11)
# ---------------------------------------------------------------------------


def test_total_iterations_label(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    executive = html.split('id="setup"', 1)[0]
    assert "Total Iterations" in executive
    assert "Total / Completed" not in executive


# ---------------------------------------------------------------------------
# Diff stats optional fields (item 6)
# ---------------------------------------------------------------------------


def test_diff_stats_optional_fields_hidden_when_missing(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    report_data.final_best_candidate.diff_stats = ReportDiffStats(
        files_changed=1,
        lines_added=4,
        lines_removed=2,
        changed_blocks=1,
        edit_count=None,
        fallback_used=None,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    cost_section = html.split('id="cost-performance-profile"', 1)[1].split(
        'id="reproducibility"', 1
    )[0]
    assert "Files Changed" in cost_section
    assert "Lines Added" in cost_section
    assert "Changed Blocks" in cost_section
    assert "Edit Count" not in cost_section
    assert "Fallback Used" not in cost_section


def test_diff_stats_optional_fields_shown_when_present(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    report_data.final_best_candidate.diff_stats = ReportDiffStats(
        files_changed=1,
        lines_added=4,
        lines_removed=2,
        changed_blocks=1,
        edit_count=2,
        fallback_used=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Edit Count" in html
    assert "Fallback Used" in html


# ---------------------------------------------------------------------------
# Status badge semantic colors (item 3)
# ---------------------------------------------------------------------------


def test_status_badge_css_colors_match_semantics(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert ".status-valid_not_improved" in html
    assert ".status-no_op" in html
    assert "status-valid_not_improved,\n    .status-no_op" not in html


# ---------------------------------------------------------------------------
# Timestamps use human_datetime (item 4)
# ---------------------------------------------------------------------------


def test_timestamps_use_human_datetime(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.experiment_metadata = ReportExperimentMetadata(
        started_at="2026-05-30T14:22:33.123456+00:00",
        finished_at="2026-05-30T15:10:05Z",
        repository={"git_commit": "abc123"},
        environment={"python_version": "3.12"},
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "2026-05-30 14:22" in html
    assert "2026-05-30 15:10" in html
    assert "123456" not in html


# ---------------------------------------------------------------------------
# Issue 1: Status badge overflow CSS
# ---------------------------------------------------------------------------


def test_status_badge_wrap_css_in_iteration_tables(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "white-space: normal" in html
    assert "overflow-wrap: anywhere" in html
    assert "word-break: break-word" in html
    assert "max-width: 100%" in html


# ---------------------------------------------------------------------------
# Issue 2: Scroll margin for sticky TOC
# ---------------------------------------------------------------------------


def test_scroll_margin_top_in_section_css(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "scroll-margin-top: 140px" in html
    assert "scroll-margin-top: 0" in html


# ---------------------------------------------------------------------------
# Issue 3: Decision Metric uses data not hardcoded
# ---------------------------------------------------------------------------


def test_decision_metric_not_hardcoded(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.baseline_metrics.decision_metric = "median_runtime"
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        decision_metric="median_runtime",
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        final_correctness_passed=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    # Decision Metric appears in Setup -> Benchmark card
    setup_section = html.split('id="setup"', 1)[1].split('id="final-result"', 1)[0]
    assert "median_runtime" in setup_section


def test_decision_metric_fallbacks_to_baseline(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.baseline_metrics.decision_metric = "minimum_runtime"

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "minimum_runtime" in html


# ---------------------------------------------------------------------------
# Issue 4: delta_pp applied to percentage-point deltas in comparison table
# ---------------------------------------------------------------------------


def test_valid_solutions_delta_uses_delta_pp(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        final_valid_solutions_delta_points=-1.50,
        final_correctness_passed=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "-1.50\u202fpp" in html


def test_gt_found_delta_uses_delta_pp_in_comparison(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        final_gt_found_delta_points=0.00,
        final_correctness_passed=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "0.00\u202fpp" in html


# ---------------------------------------------------------------------------
# Issue 5: final_valid_solutions_percent uses percent filter
# ---------------------------------------------------------------------------


def test_final_valid_solutions_percent_uses_percent_filter(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        final_valid_solutions_percent=95.00,
        final_correctness_passed=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "95.00%" in html


# ---------------------------------------------------------------------------
# Issue 6: Missing final diff message distinguishes two cases
# ---------------------------------------------------------------------------


def test_missing_diff_message_when_baseline_is_final_best(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        final_best_is_baseline=True,
        speedup_vs_original_baseline=1.0,
        runtime_reduction_percent=0.0,
        final_correctness_passed=True,
    )
    report_data.final_code_diff = None

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "final selected source is the original baseline" in html
    assert "artifact is missing" not in html


def test_missing_diff_message_when_artifact_missing(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        final_best_is_baseline=False,
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        final_correctness_passed=True,
    )
    report_data.final_code_diff = None

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "artifact is missing" in html
    assert "final selected source is the original baseline" not in html


# ---------------------------------------------------------------------------
# Issue 8: Speedup cell in Selected Iteration Details uses <br>
# ---------------------------------------------------------------------------


def test_speedup_cell_two_line_format(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.iterations[0].outcome_reason = ReportOutcomeReason(
        category="decision",
        code="accepted_improvement",
        message="Accepted.",
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    appendix_section = html.split('id="appendix"', 1)[1]
    assert "<br>" in appendix_section
    assert "; current best" not in appendix_section


# ---------------------------------------------------------------------------
# Issue 9: Diff stats zero vs None distinction
# ---------------------------------------------------------------------------


def test_diff_stats_explicit_zero_is_shown(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    report_data.final_best_candidate.diff_stats = ReportDiffStats(
        files_changed=0,
        lines_added=0,
        lines_removed=0,
        changed_blocks=0,
        edit_count=0,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    cost_section = html.split('id="cost-performance-profile"', 1)[1].split(
        'id="reproducibility"', 1
    )[0]
    assert "Files Changed" in cost_section
    assert "0" in cost_section


def test_diff_stats_missing_fields_are_hidden(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    report_data.final_best_candidate.diff_stats = ReportDiffStats(
        files_changed=1,
        lines_added=None,
        lines_removed=None,
        changed_blocks=1,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    cost_section = html.split('id="cost-performance-profile"', 1)[1].split(
        'id="reproducibility"', 1
    )[0]
    assert "Files Changed" in cost_section
    assert "Changed Blocks" in cost_section
    assert "Lines Added" not in cost_section
    assert "Lines Removed" not in cost_section


def test_diff_stats_all_none_shows_fallback(tmp_path: Path) -> None:
    report_data = _enriched_report_data()
    report_data.final_best_candidate.diff_stats = ReportDiffStats()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    cost_section = html.split('id="cost-performance-profile"', 1)[1].split(
        'id="reproducibility"', 1
    )[0]
    assert "Final Diff Statistics" not in cost_section
    assert "Final diff statistics were not recorded" in cost_section


# ---------------------------------------------------------------------------
# Issue 11: GT Found Δ fallback from iteration data
# ---------------------------------------------------------------------------


def test_gt_found_delta_fallback_from_iteration_data(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_result.final_best_iteration = 1
    report_data.iterations = [
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            runtime_ns_per_problem_median=800.0,
            speedup_vs_baseline=1.25,
            correctness_passed=True,
            promoted=True,
            gt_found_delta_points_vs_original_baseline=-0.50,
        ),
    ]

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "GT Found Δ" in html
    assert "-0.50" in html


# ---------------------------------------------------------------------------
# Task 1: Min-runtime delta in comparison table
# ---------------------------------------------------------------------------


def test_min_runtime_delta_in_comparison_table(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.baseline_metrics.min_runtime_ns_per_problem_median = 500.0
    report_data.final_best_candidate = ReportFinalBestCandidate(
        iteration=1,
        min_runtime_ns_per_problem_median=400.0,
        min_runtime_absolute_difference_ns_per_problem=100.0,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "100.00" in html
    # Should not use runtime_reduction_percent for min runtime row
    comparison_section = html.split('id="final-result"', 1)[1]
    assert "Min runtime ns/problem" in comparison_section


def test_comparison_table_header_is_change(tmp_path: Path) -> None:
    report_data = _report_data()
    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "<th>Change</th>" in html
    assert "<th>Delta / Result</th>" not in html


def test_runtime_deltas_show_ns_unit(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_best_candidate = ReportFinalBestCandidate(
        iteration=1,
        absolute_runtime_difference_ns_per_problem=200.0,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    # Runtime deltas should include "ns"
    assert "200.00" in html
    assert "ns" in html


# ---------------------------------------------------------------------------
# Task 8: Per-iteration reason column
# ---------------------------------------------------------------------------


def test_per_iteration_reason_prefers_granular_reason(tmp_path: Path) -> None:
    report_data = _report_data()
    # Set a granular reason on iteration 2 that differs from status
    report_data.iterations[1].reason = "insufficient_speedup"
    report_data.iterations[1].status = "valid_not_improved"
    report_data.iterations[1].display_reason = "insufficient_speedup"

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "insufficient_speedup" in html
    assert "<th>Reason</th>" in html


def test_per_iteration_reason_header_is_reason(tmp_path: Path) -> None:
    report_data = _report_data()
    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "<th>Reason</th>" in html
    assert "Reason Code or Reason" not in html


# ---------------------------------------------------------------------------
# Task 5: No duplicate Benchmark Family / Solver in Experiment card
# ---------------------------------------------------------------------------


def test_setup_no_duplicate_benchmark_family_in_experiment_card(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.experiment.benchmark_family = "poselib_native"
    report_data.benchmark_config = ReportBenchmarkConfig(
        family="poselib_native",
        solver="poselib_p3p",
        build_type="Release",
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    # Benchmark card still shows family
    setup_section = html.split('id="setup"', 1)[1].split('id="final-result"', 1)[0]
    # Experiment card should NOT have Benchmark Family row
    experiment_card = setup_section.split("<h3>Experiment</h3>", 1)[1].split("<h3>LLM</h3>", 1)[0]
    assert "Benchmark Family" not in experiment_card
    assert "Solver / Model" not in experiment_card


# ---------------------------------------------------------------------------
# Task 7: Wall-time labels
# ---------------------------------------------------------------------------


def test_wall_time_labels_clarified(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.baseline_metrics.total_benchmark_wall_seconds = 120.0
    report_data.final_best_candidate = ReportFinalBestCandidate(
        iteration=1,
        total_benchmark_wall_seconds=100.0,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Baseline Benchmark Wall Time" in html
    assert "Final Benchmark Wall Time" in html
    assert "Total Benchmark Wall Time" not in html


# ---------------------------------------------------------------------------
# Task 10: No Reporting Formats or Renderer in Reproducibility
# ---------------------------------------------------------------------------


def test_reproducibility_no_reporting_formats_or_renderer(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.experiment_config_details = ReportExperimentConfigDetails(
        reporting_formats=["html"],
        reporting_renderer="auto",
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    reproducibility = html.split('id="reproducibility"', 1)[1].split('id="appendix"', 1)[0]
    assert "Reporting Formats" not in reproducibility
    assert "Renderer" not in reproducibility


# ---------------------------------------------------------------------------
# Task 11: Final diff collapsed for screen, visible in print
# ---------------------------------------------------------------------------


def test_final_diff_collapsed_for_screen(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_code_diff = "--- a/file.cc\n+++ b/file.cc\n@@ -1 +1 @@\n-old\n+new\n"

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "<details open>" not in html
    assert 'class="screen-only"' in html
    assert 'class="print-only"' in html
    assert "View final diff" in html


def test_final_diff_print_block_present(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_code_diff = "--- a/file.cc\n+++ b/file.cc\n@@ -1 +1 @@\n-old\n+new\n"

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert 'class="print-only"' in html


def test_final_diff_summary_includes_line_counts(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.final_code_diff = "--- a/file.cc\n+++ b/file.cc\n@@ -1 +1 @@\n-old\n+new\n"
    report_data.final_best_candidate = ReportFinalBestCandidate(
        iteration=1,
        diff_stats=ReportDiffStats(
            lines_added=5,
            lines_removed=3,
        ),
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "View final diff (+5 /" in html


# ---------------------------------------------------------------------------
# Task 9: status_breakdown not generated or referenced
# ---------------------------------------------------------------------------


def test_status_breakdown_not_in_html(tmp_path: Path) -> None:
    report_data = _report_data()
    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "status_breakdown" not in html
    assert not (tmp_path / "plots" / "status_breakdown.svg").exists()


# ---------------------------------------------------------------------------
# Visual cleanup: Decision Metric KPI removed from Final Result
# ---------------------------------------------------------------------------


def test_final_result_no_decision_metric_kpi(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.baseline_metrics.decision_metric = "median_runtime"
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        decision_metric="median_runtime",
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        final_correctness_passed=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    final_result = html.split('id="final-result"', 1)[1].split(
        'id="optimization-process"', 1
    )[0]
    # Decision Metric KPI card must NOT appear inside final-result
    assert "Decision Metric</strong>" not in final_result

    # But the label and value should still appear in Setup -> Benchmark
    setup_section = html.split('id="setup"', 1)[1].split('id="final-result"', 1)[0]
    assert "Decision Metric</th>" in setup_section
    assert "median_runtime" in setup_section


def test_final_result_comparison_no_correctness_row(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.baseline_metrics.correctness_passed = True
    report_data.final_selection = ReportFinalSelection(
        status="completed",
        speedup_vs_original_baseline=1.25,
        runtime_reduction_percent=20.0,
        final_correctness_passed=True,
    )

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    final_result = html.split('id="final-result"', 1)[1].split(
        'id="optimization-process"', 1
    )[0]
    comparison_template = final_result.split("<h3>Comparison</h3>", 1)[1].split(
        "<h3>Final Best Candidate</h3>", 1
    )[0]
    assert "Correctness" not in comparison_template


def test_optimization_process_no_explanatory_prose(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Closed-loop optimization updates the current best source only when a verified candidate is accepted as an improvement." not in html


def test_per_iteration_min_runtime_ns_problem_header(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "<th>Min Runtime ns/problem</th>" in html
    assert "<th>Min Runtime</th>" not in html


def test_cost_profile_two_column_grid(tmp_path: Path) -> None:
    report_data = _report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    cost_section = html.split('id="cost-performance-profile"', 1)[1].split(
        'id="reproducibility"', 1
    )[0]
    assert "plot-grid-two-column" in cost_section


def test_reproducibility_no_removed_fields(tmp_path: Path) -> None:
    report_data = _report_data()
    report_data.experiment_metadata = ReportExperimentMetadata(
        repository={
            "git_commit": "abc123",
            "git_branch": "main",
            "dirty_worktree": True,
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

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    reproducibility = html.split('id="reproducibility"', 1)[1].split(
        'id="appendix"', 1
    )[0]
    assert "Git Commit" not in reproducibility
    assert "Git Branch" not in reproducibility
    assert "Dirty Worktree" not in reproducibility
    assert "CMake Executable" not in reproducibility
    assert "C++ Compiler" not in reproducibility
    # These should still be present
    assert "OS" in reproducibility
    assert "Platform" in reproducibility
    assert "Python Version" in reproducibility
    assert "CMake Build Type" in reproducibility
    assert "CMake Generator" in reproducibility
    assert "Baseline Run Directory" in reproducibility


# ---------------------------------------------------------------------------
# Integer iteration ticks on plots
# ---------------------------------------------------------------------------


def test_runtime_progress_integer_ticks_0_to_10(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_ticks", TARGET_FILE)
    report_data.baseline_metrics = ReportBaselineMetrics(runtime_ns_per_problem_median=100.0)
    report_data.iterations = [
        ReportIterationSummary(
            iteration=i,
            status="accepted_improvement",
            runtime_ns_per_problem_median=100.0 - i,
            promoted=True,
        )
        for i in range(1, 11)
    ]
    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_text = (plots_dir / "runtime_progress.svg").read_text(encoding="utf-8")
    for i in range(0, 11):
        assert str(i) in svg_text


def test_runtime_reduction_integer_ticks_1_to_10(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_ticks", TARGET_FILE)
    report_data.iterations = [
        ReportIterationSummary(
            iteration=i,
            status="accepted_improvement",
            runtime_ns_per_problem_median=100.0,
            speedup_vs_baseline=1.0 + 0.01 * i,
            promoted=True,
        )
        for i in range(1, 11)
    ]
    plots_dir = tmp_path / "plots"
    build_report_figures(report_data, plots_dir)

    svg_text = (plots_dir / "runtime_reduction_by_iteration.svg").read_text(encoding="utf-8")
    for i in range(1, 11):
        assert str(i) in svg_text, f"Tick label {i} not found in runtime_reduction SVG"

    # Tick label 0 should not appear as an x-axis tick (runtime_reduction only uses iterations 1+)
    # The SVG may contain "0" as part of "1.0", version strings, etc. -- that is fine.


def test_html_no_not_available_after_visual_cleanup(tmp_path: Path) -> None:
    report_data = _enriched_report_data()

    plot_paths = build_report_figures(report_data, tmp_path / "plots")
    html_path = render_report_html(report_data, plot_paths, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    assert "Not available" not in html
