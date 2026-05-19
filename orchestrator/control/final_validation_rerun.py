"""Control-layer final validation rerun for completed experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from orchestrator.experiments.final_validation import run_final_validation
from orchestrator.reporting.generate_report import generate_basic_report

from .project_paths import get_project_paths
from .results_browser import resolve_result_selector


RerunFinalValidationStatus = Literal["success", "preflight_failed", "failed"]


@dataclass(frozen=True)
class RerunFinalValidationResult:
    status: RerunFinalValidationStatus
    experiment_dir: Path | None
    report_path: Path | None
    message: str


def rerun_final_validation_for_experiment(
    selector: str,
    repo_root: Path | None = None,
) -> RerunFinalValidationResult:
    paths = get_project_paths(repo_root)
    item = resolve_result_selector(selector, paths.repo_root)
    if item is None or item.kind != "experiment":
        return RerunFinalValidationResult("preflight_failed", None, None, f"Experiment not found: {selector}")

    experiment_dir = item.path
    final_source_dir = experiment_dir / "final_optimized_source"
    if not final_source_dir.is_dir():
        return RerunFinalValidationResult(
            "preflight_failed",
            experiment_dir,
            None,
            f"Final optimized source not found: {final_source_dir}",
        )
    summary_path = experiment_dir / "closed_loop_summary.json"
    if not summary_path.is_file():
        return RerunFinalValidationResult(
            "preflight_failed",
            experiment_dir,
            None,
            f"Closed-loop summary not found: {summary_path}",
        )

    try:
        config = _load_config_artifact(experiment_dir)
        final_validation_raw = config.get("final_validation")
        final_validation_config = final_validation_raw if isinstance(final_validation_raw, dict) else {}
        enabled = _bool_value(final_validation_config, "enabled", True)
        repetitions = _positive_int_value(final_validation_config, "benchmark_repetitions", 5)
        report_path = run_final_validation(
            experiment_dir=experiment_dir,
            experiment_id=_experiment_id(experiment_dir),
            repo_root=paths.repo_root,
            baseline_source_dir=paths.repo_root,
            final_source_dir=final_source_dir,
            enabled=enabled,
            benchmark_repetitions=repetitions,
        )
        validation_status = _update_summary_with_final_validation(summary_path, report_path)
        _update_experiment_status(experiment_dir, validation_status, enabled)
        _refresh_report(experiment_dir)
    except Exception as exc:
        return RerunFinalValidationResult("failed", experiment_dir, None, str(exc))

    return RerunFinalValidationResult(
        "success",
        experiment_dir,
        report_path,
        "Final validation rerun completed.",
    )


def _load_config_artifact(experiment_dir: Path) -> dict[str, Any]:
    for name in ("experiment_config_effective.json", "experiment_config_snapshot.json"):
        path = experiment_dir / name
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ValueError(f"Expected JSON object in: {path}")
            return payload
    return {}


def _experiment_id(experiment_dir: Path) -> str:
    status = _read_json_object_if_exists(experiment_dir / "experiment_status.json")
    if isinstance(status.get("experiment_id"), str) and status["experiment_id"]:
        return status["experiment_id"]
    summary = _read_json_object_if_exists(experiment_dir / "closed_loop_summary.json")
    if isinstance(summary.get("experiment_id"), str) and summary["experiment_id"]:
        return summary["experiment_id"]
    return experiment_dir.name


def _update_summary_with_final_validation(summary_path: Path, report_path: Path) -> dict[str, Any]:
    summary = _read_json_object(summary_path)
    report = _read_json_object(report_path)
    comparison_raw = report.get("comparison")
    baseline_raw = report.get("baseline")
    final_raw = report.get("final")
    comparison = comparison_raw if isinstance(comparison_raw, dict) else {}
    baseline = baseline_raw if isinstance(baseline_raw, dict) else {}
    final = final_raw if isinstance(final_raw, dict) else {}
    baseline_summary_raw = baseline.get("summary")
    final_summary_raw = final.get("summary")
    baseline_summary = baseline_summary_raw if isinstance(baseline_summary_raw, dict) else {}
    final_summary = final_summary_raw if isinstance(final_summary_raw, dict) else {}
    baseline_median_runtime = _numeric_or_none(
        baseline_summary.get("median_runtime_ns_per_problem")
    )
    if baseline_median_runtime is None:
        baseline_median_runtime = _numeric_or_none(
            baseline_summary.get("median_runtime_ns_per_case")
        )
    final_median_runtime = _numeric_or_none(
        final_summary.get("median_runtime_ns_per_problem")
    )
    if final_median_runtime is None:
        final_median_runtime = _numeric_or_none(
            final_summary.get("median_runtime_ns_per_case")
        )
    median_speedup = _numeric_or_none(comparison.get("median_speedup"))
    median_reduction = _numeric_or_none(comparison.get("median_runtime_reduction_percent"))

    summary["final_validation_report_path"] = _display_path(report_path)
    summary["final_validation_median_speedup"] = median_speedup
    summary["final_validation_median_runtime_reduction_percent"] = median_reduction
    _write_json(summary_path, summary)
    return {
        "enabled": report.get("enabled"),
        "status": report.get("status"),
        "benchmark_repetitions": report.get("benchmark_repetitions"),
        "report_path": _display_path(report_path),
        "median_speedup": median_speedup,
        "median_runtime_reduction_percent": median_reduction,
        "baseline_median_runtime_ns_per_problem": baseline_median_runtime,
        "final_median_runtime_ns_per_problem": final_median_runtime,
    }


def _update_experiment_status(
    experiment_dir: Path,
    validation_status: dict[str, Any],
    final_validation_enabled: bool,
) -> None:
    status_path = experiment_dir / "experiment_status.json"
    status = _read_json_object_if_exists(status_path)
    closed_loop_raw = status.get("closed_loop")
    closed_loop = closed_loop_raw if isinstance(closed_loop_raw, dict) else {}
    closed_loop["final_validation"] = validation_status
    closed_loop["final_validation_report_path"] = validation_status.get("report_path")
    closed_loop["final_validation_median_speedup"] = validation_status.get("median_speedup")
    closed_loop["final_validation_median_runtime_reduction_percent"] = validation_status.get(
        "median_runtime_reduction_percent"
    )
    status["closed_loop"] = closed_loop
    if status:
        status["overall_status"] = (
            "completed"
            if not final_validation_enabled or _has_final_validation_metrics(validation_status)
            else "completed_with_warnings"
        )
        _write_json(status_path, status)


def _refresh_report(experiment_dir: Path) -> None:
    if (experiment_dir / "closed_loop_iterations.jsonl").is_file():
        generate_basic_report(experiment_dir, formats=("html",))


def _has_final_validation_metrics(status: dict[str, Any]) -> bool:
    return (
        status.get("status") in {"completed", "completed_partial"}
        and _numeric_or_none(status.get("median_speedup")) is not None
        and _numeric_or_none(status.get("median_runtime_reduction_percent")) is not None
    )


def _bool_value(payload: dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key)
    return value if isinstance(value, bool) else default


def _positive_int_value(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _numeric_or_none(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in: {path}")
    return payload


def _read_json_object_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return _read_json_object(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    return str(path).replace("\\", "/")
