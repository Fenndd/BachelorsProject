"""Normalized report_data.json contract for experiment reporting.

This module defines the read-only data shape used by the reporting layer. It
does not collect artifacts, render reports, run benchmarks, or make optimization
decisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from orchestrator.experiments.closed_loop_state import IterationStatus

    KNOWN_ITERATION_STATUSES = tuple(status.value for status in IterationStatus)
except ImportError:
    KNOWN_ITERATION_STATUSES = (
        "accepted_improvement",
        "valid_not_improved",
        "rejected",
        "materialization_failed",
        "verification_failed",
        "no_op",
        "generation_failed",
    )


REPORT_SCHEMA_VERSION = "report.v1"
REPORT_GENERATOR = "orchestrator.reporting"
REPORT_PROFILE_BASIC_SINGLE_EXPERIMENT = "basic_single_experiment"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ReportMetadata:
    """Metadata about report_data.json generation."""

    generated_at: str = field(default_factory=_utc_now_iso)
    generator: str = REPORT_GENERATOR
    report_profile: str = REPORT_PROFILE_BASIC_SINGLE_EXPERIMENT


@dataclass
class ExperimentReportInfo:
    """Experiment-level details shown in a report."""

    experiment_id: str
    experiment_name: str | None = None
    target_file: str = ""
    model: str | None = None
    candidate_format: str | None = None
    source_presentation: str | None = None
    total_iterations: int = 0
    completed_iterations: int = 0
    closed_loop_enabled: bool = True
    benchmark_family: str | None = None


@dataclass
class ReportFinalResult:
    """Final normalized optimization outcome."""

    final_best_iteration: int = 0
    final_speedup_vs_baseline: float | None = None
    final_runtime_reduction_percent: float | None = None
    accepted_improvements: int = 0
    correctness_preserved: bool | None = None


@dataclass
class ReportBaselineMetrics:
    """Baseline benchmark and correctness metrics."""

    runtime_ns_per_case_median: float | None = None
    success_rate: float | None = None
    mean_reprojection_error: float | None = None
    max_reprojection_error: float | None = None
    correctness_passed: bool | None = None


@dataclass
class ReportIterationSummary:
    """Normalized per-iteration summary for reports."""

    iteration: int
    status: str
    candidate_summary: str | None = None
    expected_effect: str | None = None
    risk_level: str | None = None
    runtime_ns_per_case_median: float | None = None
    speedup_vs_current_best: float | None = None
    speedup_vs_baseline: float | None = None
    correctness_passed: bool | None = None
    promoted: bool = False
    reason: str | None = None
    candidate_run_dir: Path | str | None = None


@dataclass
class ReportStatusCounts:
    """Counts for each known closed-loop iteration status."""

    accepted_improvement: int = 0
    valid_not_improved: int = 0
    rejected: int = 0
    materialization_failed: int = 0
    verification_failed: int = 0
    no_op: int = 0
    generation_failed: int = 0


@dataclass
class ReportArtifactMap:
    """Report and source artifact locations referenced by report_data.json."""

    experiment_dir: Path | str | None = None
    report_dir: Path | str | None = None
    report_data: Path | str | None = None
    report_html: Path | str | None = None
    report_pdf: Path | str | None = None
    plots_dir: Path | str | None = None
    final_optimized_source: Path | str | None = None
    final_diff: Path | str | None = None
    closed_loop_summary: Path | str | None = None
    closed_loop_iterations: Path | str | None = None


@dataclass
class ReportLlmInfo:
    """LLM and variant configuration used in the experiment."""

    provider: str | None = None
    model: str | None = None
    llm_config: str | None = None
    variant_id: str | None = None
    variant_description: str | None = None
    thinking_enabled: bool | None = None
    thinking_effort: str | None = None
    max_tokens: int | None = None


@dataclass
class ReportExperimentConfigDetails:
    """Raw experiment config snapshot fields surfaced in the report."""

    description: str | None = None
    candidate_generation_max_source_chars: int | None = None
    candidate_format_type: str | None = None
    source_presentation: str | None = None
    require_original_verification: bool | None = None
    allow_exact_search_fallback: bool | None = None
    history_policy_enabled: bool | None = None
    history_policy_scope: str | None = None
    selection_enabled: bool | None = None
    selection_baseline_run_dir: str | None = None
    closed_loop_enabled: bool | None = None
    optimization_scope_allowed_files: list[str] = field(default_factory=list)
    reporting_enabled: bool | None = None
    reporting_formats: list[str] = field(default_factory=list)
    reporting_renderer: str | None = None
    reporting_fail_on_error: bool | None = None


@dataclass
class ReportBenchmarkConfig:
    """Benchmark configuration extracted from baseline metrics artifact."""

    family: str | None = None
    solver: str | None = None
    num_cases: int | None = None
    points_per_case: int | None = None
    warmup_iterations: int | None = None
    timed_iterations: int | None = None
    seed: int | None = None
    runtime_unit: str | None = None
    reprojection_error_threshold: float | None = None
    minimum_success_rate: float | None = None
    require_all_cases_valid: bool | None = None
    use_max_reprojection_error_as_hard_gate: bool | None = None
    build_type: str | None = None


@dataclass
class ReportClosedLoopSelection:
    """Summary of closed-loop selection from closed_loop_selection_report.json."""

    promotion_policy: str | None = None
    final_current_best_iteration: int | None = None
    final_current_best_is_baseline: bool | None = None
    final_current_best_run_dir: str | None = None
    final_current_best_source_dir: str | None = None
    final_current_best_metrics_path: str | None = None
    best_verified_candidate_iteration: int | None = None
    best_verified_candidate_run_dir: str | None = None
    best_verified_candidate_speedup_vs_baseline: float | None = None
    best_verified_candidate_runtime_reduction_percent: float | None = None
    matches_final_current_best: bool | None = None


@dataclass
class ReportReportingStatus:
    """Reporting pipeline status and PDF generation outcome."""

    enabled: bool | None = None
    status: str | None = None
    formats: list[str] = field(default_factory=list)
    renderer: str | None = None
    report_data_path: str | None = None
    report_html_path: str | None = None
    report_pdf_path: str | None = None
    pdf_generated: bool = False
    pdf_display: str | None = None
    error: str | None = None


@dataclass
class ReportFinalBestCandidate:
    """Full summary of the final best candidate (or baseline if no improvement)."""

    iteration: int | None = None
    candidate_run_dir: str | None = None
    runtime_ns_per_case_median: float | None = None
    baseline_runtime_ns_per_case_median: float | None = None
    absolute_runtime_difference_ns_per_case: float | None = None
    speedup_vs_baseline: float | None = None
    runtime_reduction_percent: float | None = None
    correctness_passed: bool | None = None
    candidate_summary: str | None = None
    expected_effect: str | None = None
    risk_level: str | None = None
    changed_files: list[str] = field(default_factory=list)
    final_optimized_source: str | None = None
    final_diff: str | None = None


@dataclass(kw_only=True)
class ReportData:
    """Top-level normalized report_data.json contract."""

    schema_version: str = REPORT_SCHEMA_VERSION
    report_metadata: ReportMetadata = field(default_factory=ReportMetadata)
    experiment: ExperimentReportInfo
    final_result: ReportFinalResult = field(default_factory=ReportFinalResult)
    baseline_metrics: ReportBaselineMetrics = field(default_factory=ReportBaselineMetrics)
    iterations: list[ReportIterationSummary] = field(default_factory=list)
    status_counts: ReportStatusCounts | dict[str, int] = field(default_factory=ReportStatusCounts)
    artifacts: ReportArtifactMap = field(default_factory=ReportArtifactMap)
    llm: ReportLlmInfo = field(default_factory=ReportLlmInfo)
    experiment_config_details: ReportExperimentConfigDetails = field(
        default_factory=ReportExperimentConfigDetails
    )
    benchmark_config: ReportBenchmarkConfig = field(default_factory=ReportBenchmarkConfig)
    closed_loop_selection: ReportClosedLoopSelection = field(
        default_factory=ReportClosedLoopSelection
    )
    final_best_candidate: ReportFinalBestCandidate = field(
        default_factory=ReportFinalBestCandidate
    )
    reporting_status: ReportReportingStatus = field(default_factory=ReportReportingStatus)


def default_status_counts() -> dict[str, int]:
    """Return every known closed-loop status with a zero count."""

    return {status: 0 for status in KNOWN_ITERATION_STATUSES}


def to_report_dict(value: Any) -> Any:
    """Recursively convert report data into JSON-compatible values."""

    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_report_dict(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [to_report_dict(item) for item in value]
    if isinstance(value, tuple):
        return [to_report_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_report_dict(item) for key, item in value.items()}
    return value


def write_report_data(path: Path | str, report_data: ReportData) -> Path:
    """Write report_data.json as human-readable UTF-8 JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(to_report_dict(report_data), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def make_empty_report_data(experiment_id: str, target_file: str) -> ReportData:
    """Create a minimal valid single-experiment report data object."""

    return ReportData(
        experiment=ExperimentReportInfo(
            experiment_id=experiment_id,
            target_file=target_file,
        ),
        status_counts=default_status_counts(),
    )


__all__ = [
    "KNOWN_ITERATION_STATUSES",
    "REPORT_GENERATOR",
    "REPORT_PROFILE_BASIC_SINGLE_EXPERIMENT",
    "REPORT_SCHEMA_VERSION",
    "ExperimentReportInfo",
    "ReportArtifactMap",
    "ReportBaselineMetrics",
    "ReportBenchmarkConfig",
    "ReportClosedLoopSelection",
    "ReportData",
    "ReportExperimentConfigDetails",
    "ReportFinalBestCandidate",
    "ReportFinalResult",
    "ReportIterationSummary",
    "ReportLlmInfo",
    "ReportMetadata",
    "ReportReportingStatus",
    "ReportStatusCounts",
    "default_status_counts",
    "make_empty_report_data",
    "to_report_dict",
    "write_report_data",
]
