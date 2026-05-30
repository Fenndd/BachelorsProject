"""Read-only final repeated-median comparison for closed-loop experiments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.core.benchmarking.benchmark_artifacts import empty_benchmark_artifact
from orchestrator.core.benchmarking.solver_registry import (
    SolverBenchmarkDescriptor,
    default_solver_descriptor,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT / "workspace"

FINAL_SELECTION_DIR_NAME = "final_selection"
FINAL_BENCHMARK_RUN_DIR_NAME = "final_benchmark_run"
FINAL_SELECTION_REPORT_FILENAME = "final_selection_report.json"
_BUILD_DIR_NAME = "final_selection_build"

_DESCRIPTOR: SolverBenchmarkDescriptor = default_solver_descriptor()


def run_final_selection_report(
    *,
    experiment_dir: Path,
    experiment_id: str,
    repo_root: Path,
    baseline_run_dir: Path,
    final_source_dir: Path,
    final_best_run_dir: Path | None,
    target_file: str,
    final_best_is_baseline: bool,
    descriptor: SolverBenchmarkDescriptor | None = None,
    build_type: str = "Release",
    gt_found_max_drop_points: float | None = None,
) -> Path:
    """Write final_selection_report.json from existing repeated benchmark artifacts."""
    output_dir = experiment_dir / FINAL_SELECTION_DIR_NAME
    benchmark_descriptor = descriptor or _DESCRIPTOR
    report_path = experiment_dir / FINAL_SELECTION_REPORT_FILENAME
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_benchmark = _load_baseline_benchmark(baseline_run_dir, benchmark_descriptor)
    baseline_runtime = _runtime_ns(baseline_benchmark)
    baseline_gt_found = _gt_found_percent(baseline_benchmark)
    baseline_valid = _valid_solutions_percent(baseline_benchmark)

    if final_best_is_baseline:
        marker = {
            "reused_baseline": True,
            "note": "Final best is original baseline; existing repeated benchmark artifact was reused.",
            "baseline_run_dir": _display_path(baseline_run_dir, repo_root),
        }
        _write_json(output_dir / "reused_baseline.json", marker)
        comparison = {
            "speedup": 1.0,
            "runtime_reduction_percent": 0.0,
            "baseline_runtime_ns_per_problem_median": baseline_runtime,
            "final_runtime_ns_per_problem_median": baseline_runtime,
            "candidate_runtime_lower": False,
            "baseline_gt_found_percent": baseline_gt_found,
            "final_gt_found_percent": baseline_gt_found,
            "final_gt_found_delta_points": 0.0 if baseline_gt_found is not None else None,
            "baseline_valid_solutions_percent": baseline_valid,
            "final_valid_solutions_percent": baseline_valid,
            "final_valid_solutions_delta_points": 0.0 if baseline_valid is not None else None,
            "baseline_benchmark_run_count": baseline_benchmark.get("benchmark_run_count"),
            "final_benchmark_run_count": baseline_benchmark.get("benchmark_run_count"),
            "decision_metric": baseline_benchmark.get("decision_metric"),
        }
        report = _build_report(
            experiment_id=experiment_id,
            target_file=target_file,
            baseline_run_dir=baseline_run_dir,
            final_source_dir=final_source_dir,
            final_best_run_dir=final_best_run_dir,
            final_best_is_baseline=True,
            baseline_benchmark=baseline_benchmark,
            final_benchmark=baseline_benchmark,
            decision_vs_original_baseline=None,
            comparison=comparison,
            status="skipped",
            failed_step=None,
            error_message=None,
            artifacts={
                "final_benchmark_run_dir": None,
                "final_benchmark_log": None,
                "final_benchmark_verification": _display_path(baseline_run_dir / "metrics.json", repo_root),
            },
            repo_root=repo_root,
        )
        _write_json(report_path, report)
        return report_path

    final_benchmark = _load_candidate_benchmark(final_best_run_dir, benchmark_descriptor)
    final_runtime = _runtime_ns(final_benchmark)
    final_gt_found = _gt_found_percent(final_benchmark)
    final_valid = _valid_solutions_percent(final_benchmark)
    speedup = (
        baseline_runtime / final_runtime
        if baseline_runtime is not None and final_runtime is not None and final_runtime > 0
        else None
    )
    runtime_reduction = (
        ((baseline_runtime - final_runtime) / baseline_runtime) * 100.0
        if baseline_runtime is not None and final_runtime is not None and baseline_runtime > 0
        else None
    )
    comparison = {
        "speedup": speedup,
        "runtime_reduction_percent": runtime_reduction,
        "baseline_runtime_ns_per_problem_median": baseline_runtime,
        "final_runtime_ns_per_problem_median": final_runtime,
        "candidate_runtime_lower": final_runtime is not None and baseline_runtime is not None and final_runtime < baseline_runtime,
        "baseline_gt_found_percent": baseline_gt_found,
        "final_gt_found_percent": final_gt_found,
        "final_gt_found_delta_points": final_gt_found - baseline_gt_found if final_gt_found is not None and baseline_gt_found is not None else None,
        "baseline_valid_solutions_percent": baseline_valid,
        "final_valid_solutions_percent": final_valid,
        "final_valid_solutions_delta_points": final_valid - baseline_valid if final_valid is not None and baseline_valid is not None else None,
        "baseline_benchmark_run_count": baseline_benchmark.get("benchmark_run_count"),
        "final_benchmark_run_count": final_benchmark.get("benchmark_run_count"),
        "decision_metric": final_benchmark.get("decision_metric") or baseline_benchmark.get("decision_metric"),
    }
    status = "completed" if final_benchmark.get("parse_success") is True else "failed"
    failed_step = None if status == "completed" else "load_final_best_benchmark"
    error_message = None if status == "completed" else "Final best benchmark artifact is missing or invalid."
    report = _build_report(
        experiment_id=experiment_id,
        target_file=target_file,
        baseline_run_dir=baseline_run_dir,
        final_source_dir=final_source_dir,
        final_best_run_dir=final_best_run_dir,
        final_best_is_baseline=False,
        baseline_benchmark=baseline_benchmark,
        final_benchmark=final_benchmark,
        decision_vs_original_baseline=None,
        comparison=comparison,
        status=status,
        failed_step=failed_step,
        error_message=error_message,
        artifacts={
            "final_benchmark_run_dir": _display_path(final_best_run_dir, repo_root) if final_best_run_dir else None,
            "final_benchmark_log": None,
            "final_benchmark_verification": _display_path(final_best_run_dir / "verification.json", repo_root) if final_best_run_dir else None,
        },
        repo_root=repo_root,
    )
    _write_json(report_path, report)
    return report_path


def _load_baseline_benchmark(
    baseline_run_dir: Path,
    descriptor: SolverBenchmarkDescriptor,
) -> dict[str, Any]:
    metrics_path = baseline_run_dir / "metrics.json"
    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return empty_benchmark_artifact(descriptor)
    if not isinstance(payload, dict):
        return empty_benchmark_artifact(descriptor)
    benchmark = payload.get("benchmark")
    return benchmark if isinstance(benchmark, dict) else empty_benchmark_artifact(descriptor)


def _load_candidate_benchmark(
    candidate_run_dir: Path | None,
    descriptor: SolverBenchmarkDescriptor,
) -> dict[str, Any]:
    if candidate_run_dir is None:
        return empty_benchmark_artifact(descriptor)
    verification_path = candidate_run_dir / "verification.json"
    try:
        payload = json.loads(verification_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return empty_benchmark_artifact(descriptor)
    if not isinstance(payload, dict):
        return empty_benchmark_artifact(descriptor)
    benchmark = payload.get("benchmark")
    return benchmark if isinstance(benchmark, dict) else empty_benchmark_artifact(descriptor)


def _runtime_ns(benchmark: dict[str, Any]) -> float | None:
    value = benchmark.get("parsed_runtime_ns_per_problem_median")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _gt_found_percent(benchmark: dict[str, Any]) -> float | None:
    value = benchmark.get("parsed_gt_found_percent")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _valid_solutions_percent(benchmark: dict[str, Any]) -> float | None:
    value = benchmark.get("parsed_valid_solutions_percent")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _null_comparison(
    baseline_runtime: float | None,
    baseline_gt_found: float | None,
) -> dict[str, Any]:
    return {
        "speedup": None,
        "runtime_reduction_percent": None,
        "baseline_runtime_ns_per_problem_median": baseline_runtime,
        "final_runtime_ns_per_problem_median": None,
        "candidate_runtime_lower": False,
        "baseline_gt_found_percent": baseline_gt_found,
        "final_gt_found_percent": None,
        "final_gt_found_delta_points": None,
    }


def _build_report(
    *,
    experiment_id: str,
    target_file: str,
    baseline_run_dir: Path,
    final_source_dir: Path,
    final_best_run_dir: Path | None,
    final_best_is_baseline: bool,
    baseline_benchmark: dict[str, Any],
    final_benchmark: dict[str, Any],
    decision_vs_original_baseline: dict[str, Any] | None,
    comparison: dict[str, Any],
    status: str,
    failed_step: str | None,
    error_message: str | None,
    artifacts: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "report_type": "repeated_median_final_selection_report",
        "experiment_id": experiment_id,
        "target_file": target_file,
        "mode": "closed_loop",
        "metric_source": "existing_repeated_median_final_best_vs_original_baseline",
        "baseline_run_dir": _display_path(baseline_run_dir, repo_root),
        "final_source_dir": _display_path(final_source_dir, repo_root),
        "final_best_run_dir": _display_path(final_best_run_dir, repo_root) if final_best_run_dir else None,
        "final_best_is_baseline": final_best_is_baseline,
        "baseline_benchmark": baseline_benchmark,
        "final_benchmark": final_benchmark,
        "decision_vs_original_baseline": decision_vs_original_baseline,
        "comparison": comparison,
        "status": status,
        "failed_step": failed_step,
        "error_message": error_message,
        "artifacts": artifacts,
    }


def _display_path(path: Path, repo_root: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        pass
    try:
        return (Path("workspace") / path.resolve().relative_to(WORKSPACE_ROOT.resolve())).as_posix()
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
