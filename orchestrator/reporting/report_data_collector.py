"""Read-only collector for normalized experiment report data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.reporting.report_data import (
    ExperimentReportInfo,
    ReportArtifactMap,
    ReportBaselineMetrics,
    ReportData,
    ReportFinalResult,
    ReportIterationSummary,
    default_status_counts,
    write_report_data,
)


def collect_report_data(
    experiment_dir: Path | str,
    *,
    output_path: Path | str | None = None,
) -> ReportData:
    """Collect normalized report data from persisted closed-loop artifacts."""

    experiment_path = Path(experiment_dir)
    summary_path = experiment_path / "closed_loop_summary.json"
    iterations_path = experiment_path / "closed_loop_iterations.jsonl"
    _require_file(summary_path, "closed-loop summary")
    _require_file(iterations_path, "closed-loop iterations")

    summary = _read_json_object(summary_path)
    records = _read_jsonl_objects(iterations_path)
    report_data_path = (
        Path(output_path)
        if output_path is not None
        else experiment_path / "report" / "report_data.json"
    )

    status_counts = _status_counts(summary, records)

    report_data = ReportData(
        experiment=ExperimentReportInfo(
            experiment_id=_string_or_default(summary.get("experiment_id")),
            target_file=_string_or_default(summary.get("target_file")),
            total_iterations=_int_or_default(summary.get("total_iterations")),
            completed_iterations=_int_or_default(summary.get("completed_iterations")),
            closed_loop_enabled=True,
        ),
        final_result=ReportFinalResult(
            final_best_iteration=_int_or_default(summary.get("final_best_iteration")),
            final_speedup_vs_baseline=_number_or_none(
                summary.get("final_speedup_vs_original_baseline")
            ),
            final_runtime_reduction_percent=_number_or_none(
                summary.get("final_runtime_reduction_percent")
            ),
            accepted_improvements=status_counts["accepted_improvement"],
            correctness_preserved=None,
        ),
        baseline_metrics=_load_baseline_metrics(
            summary.get("original_baseline_metrics_path"),
            experiment_path,
        ),
        iterations=[_iteration_summary(record) for record in records],
        status_counts=status_counts,
        artifacts=_artifact_map(
            experiment_path,
            summary,
            report_data_path=report_data_path,
        ),
    )

    if output_path is not None:
        write_report_data(report_data_path, report_data)
    return report_data


def collect_and_write_report_data(
    experiment_dir: Path | str,
    output_path: Path | str | None = None,
) -> Path:
    """Collect report data and write report/report_data.json."""

    experiment_path = Path(experiment_dir)
    report_data_path = (
        Path(output_path)
        if output_path is not None
        else experiment_path / "report" / "report_data.json"
    )
    collect_report_data(experiment_path, output_path=report_data_path)
    return report_data_path


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required {label} artifact: {path}")


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in: {path}")
    return payload


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object on line {line_number} in: {path}")
        records.append(payload)
    return records


def _status_counts(
    summary: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, int]:
    counts = default_status_counts()
    raw_counts = summary.get("status_counts")
    if isinstance(raw_counts, dict):
        for status, value in raw_counts.items():
            if (
                status in counts
                and isinstance(value, int)
                and not isinstance(value, bool)
            ):
                counts[status] = value
        return counts

    for record in records:
        status = record.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _iteration_summary(record: dict[str, Any]) -> ReportIterationSummary:
    return ReportIterationSummary(
        iteration=_int_or_default(record.get("iteration")),
        status=_string_or_default(record.get("status")),
        candidate_summary=_summary_text(record.get("candidate_summary")),
        expected_effect=_string_or_none(record.get("candidate_expected_effect")),
        risk_level=_string_or_none(record.get("candidate_risk_level")),
        runtime_ns_per_case_median=_number_or_none(
            record.get("runtime_ns_per_case_median")
        ),
        speedup_vs_current_best=_number_or_none(record.get("speedup_vs_current_best")),
        speedup_vs_baseline=_number_or_none(
            record.get("speedup_vs_original_baseline")
        ),
        correctness_passed=_bool_or_none(record.get("correctness_passed")),
        promoted=record.get("current_best_updated") is True,
        reason=_extract_reason(record),
        candidate_run_dir=_path_text_or_none(record.get("candidate_run_dir")),
    )


def _extract_reason(record: dict[str, Any]) -> str | None:
    failure_reason = _reason_text(record.get("failure_reason"))
    if failure_reason is not None:
        return failure_reason

    for decision_key in ("decision_vs_current_best", "decision_vs_original_baseline"):
        decision = record.get(decision_key)
        if not isinstance(decision, dict):
            continue
        for reason_key in ("rejection_reasons", "non_acceptance_reasons"):
            reason = _reason_text(decision.get(reason_key))
            if reason is not None:
                return reason
    return None


def _reason_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        values = [str(item) for item in value if item is not None and str(item)]
        return "; ".join(values) if values else None
    return None


def _load_baseline_metrics(
    raw_path: Any,
    experiment_dir: Path,
) -> ReportBaselineMetrics:
    path_text = _path_text_or_none(raw_path)
    if path_text is None:
        return ReportBaselineMetrics()

    metrics_path = _resolve_existing_or_display_path(path_text, experiment_dir)
    if not metrics_path.is_file():
        return ReportBaselineMetrics()

    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return ReportBaselineMetrics()
    if not isinstance(payload, dict):
        return ReportBaselineMetrics()

    candidates = [payload]
    benchmark = payload.get("benchmark")
    if isinstance(benchmark, dict):
        candidates.insert(0, benchmark)

    return ReportBaselineMetrics(
        runtime_ns_per_case_median=_first_number(
            candidates,
            (
                "runtime_ns_per_case_median",
                "runtime_median_ns_per_case",
                "median_runtime_ns_per_case",
                "parsed_runtime_ns_per_case_median",
            ),
        ),
        success_rate=_first_number(
            candidates,
            ("success_rate", "parsed_success_rate"),
        ),
        mean_reprojection_error=_first_number(
            candidates,
            (
                "mean_reprojection_error",
                "mean_best_reprojection_error",
                "parsed_mean_best_reprojection_error",
            ),
        ),
        max_reprojection_error=_first_number(
            candidates,
            (
                "max_reprojection_error",
                "max_best_reprojection_error",
                "parsed_max_best_reprojection_error",
            ),
        ),
        correctness_passed=_first_bool(
            candidates,
            ("correctness_passed", "parsed_correctness_passed"),
        ),
    )


def _artifact_map(
    experiment_dir: Path,
    summary: dict[str, Any],
    *,
    report_data_path: Path,
) -> ReportArtifactMap:
    report_dir = experiment_dir / "report"
    return ReportArtifactMap(
        experiment_dir=experiment_dir,
        report_dir=report_dir,
        report_data=report_data_path,
        report_html=report_dir / "report.html",
        report_pdf=report_dir / "report.pdf",
        plots_dir=report_dir / "plots",
        final_optimized_source=_path_text_or_none(
            summary.get("final_optimized_source_dir")
        ),
        final_diff=_path_text_or_none(
            summary.get("final_optimized_source_diff_path")
        ),
        closed_loop_summary=experiment_dir / "closed_loop_summary.json",
        closed_loop_iterations=experiment_dir / "closed_loop_iterations.jsonl",
    )


def _resolve_existing_or_display_path(path_text: str, experiment_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path

    candidates = [experiment_dir / path]
    if len(experiment_dir.parents) >= 3:
        candidates.append(experiment_dir.parents[2] / path)
    candidates.extend([Path.cwd() / path, path])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def _first_number(
    payloads: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> float | None:
    for payload in payloads:
        for key in keys:
            value = _number_or_none(payload.get(key))
            if value is not None:
                return value
    return None


def _first_bool(
    payloads: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> bool | None:
    for payload in payloads:
        for key in keys:
            value = _bool_or_none(payload.get(key))
            if value is not None:
                return value
    return None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _int_or_default(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _string_or_default(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _path_text_or_none(value: Any) -> str | None:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def _summary_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


__all__ = [
    "collect_and_write_report_data",
    "collect_report_data",
]
