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
    "ReportData",
    "ReportFinalResult",
    "ReportIterationSummary",
    "ReportMetadata",
    "ReportStatusCounts",
    "default_status_counts",
    "make_empty_report_data",
    "to_report_dict",
    "write_report_data",
]
