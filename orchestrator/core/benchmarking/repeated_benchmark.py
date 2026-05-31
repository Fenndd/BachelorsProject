"""Sequential repeated benchmark execution and median aggregation."""

from __future__ import annotations

import math
import statistics
from pathlib import Path
from typing import Any, Callable, Sequence

from orchestrator.core.benchmarking.benchmark_artifacts import (
    benchmark_artifact_from_repeated_samples,
    empty_benchmark_artifact,
)
from orchestrator.core.benchmarking.solver_registry import SolverBenchmarkDescriptor
from orchestrator.shared.process.step_runner import StepRunner


DEFAULT_REPEATED_BENCHMARK_RUN_COUNT = 100
DECISION_METRIC = "median_runtime_ns_per_problem_median"

_RUNNER = StepRunner()

BenchmarkLogCallback = Callable[
    [int, str, Sequence[str], Path, int | None, str, str],
    None,
]


def run_repeated_benchmark(
    *,
    command: Sequence[str],
    cwd: Path,
    descriptor: SolverBenchmarkDescriptor,
    build_type: str,
    step_name: str,
    title: str,
    run_count: int = DEFAULT_REPEATED_BENCHMARK_RUN_COUNT,
    run_index_start: int = 1,
    log_callback: BenchmarkLogCallback | None = None,
    echo_progress: bool = False,
) -> dict[str, Any]:
    """Run one benchmark executable sequentially and aggregate parsed metrics.

    The benchmark process is never parallelized. Each successful process stdout is
    parsed immediately with ``descriptor.parser`` and contributes one raw sample.
    """

    if run_count <= 0:
        raise ValueError("run_count must be positive")
    if run_index_start <= 0:
        raise ValueError("run_index_start must be positive")

    samples: list[dict[str, Any]] = []
    parse_results: list[dict[str, Any]] = []
    total_wall_seconds = 0.0
    total_parse_seconds = 0.0
    command_list = list(command)

    for offset in range(run_count):
        run_index = run_index_start + offset
        run_label = f"{step_name}_{run_index:03d}"
        if echo_progress:
            print(f"[BENCH] {title}: run {offset + 1}/{run_count}")
        result = _RUNNER.run_step(
            run_label,
            command_list,
            cwd,
            title=f"{title} ({offset + 1}/{run_count})",
        )
        total_wall_seconds += result.duration_seconds
        if log_callback is not None:
            log_callback(
                run_index,
                run_label,
                command_list,
                cwd,
                result.exit_code,
                result.stdout,
                result.stderr,
            )
        if result.error_message:
            return _failed_result(
                descriptor,
                build_type,
                step_name,
                step_name,
                run_index,
                total_wall_seconds,
                f"benchmark run {run_index} failed: {result.error_message}",
            )

        import time

        parse_started = time.perf_counter()
        parse_result = descriptor.parser(result.stdout)
        total_parse_seconds += time.perf_counter() - parse_started
        if parse_result.get("parse_success") is not True:
            missing = parse_result.get("missing_fields")
            errors = parse_result.get("parse_errors")
            return _failed_result(
                descriptor,
                build_type,
                step_name,
                f"parse_{descriptor.benchmark_target}",
                run_index,
                total_wall_seconds,
                "benchmark run "
                f"{run_index} parse failed: missing={missing}; parse_errors={errors}",
            )

        metrics = parse_result.get("metrics")
        if not isinstance(metrics, dict):
            return _failed_result(
                descriptor,
                build_type,
                step_name,
                f"parse_{descriptor.benchmark_target}",
                run_index,
                total_wall_seconds,
                f"benchmark run {run_index} parse result did not contain metrics",
            )
        runtime = _runtime_value(metrics)
        if not _is_positive_number(runtime):
            return _failed_result(
                descriptor,
                build_type,
                step_name,
                f"parse_{descriptor.benchmark_target}",
                run_index,
                total_wall_seconds,
                "benchmark run "
                f"{run_index} missing positive runtime_ns_per_problem_median",
            )

        runtime_number = float(runtime) if isinstance(runtime, (int, float)) else 0.0
        sample = _sample_from_metrics(run_index, metrics, runtime_number, result.duration_seconds)
        samples.append(sample)
        parse_results.append(parse_result)

    benchmark = benchmark_artifact_from_repeated_samples(
        samples,
        descriptor,
        build_type,
        parse_results=parse_results,
        total_benchmark_wall_seconds=round(total_wall_seconds, 3),
    )
    correctness_passed = benchmark.get("parsed_correctness_passed") is True
    return {
        "success": correctness_passed,
        "failed_step": None if correctness_passed else "benchmark_correctness_check",
        "error_message": None
        if correctness_passed
        else "At least one repeated benchmark run reported correctness_passed=false.",
        "benchmark": benchmark,
        "run_step_status": {
            "name": step_name,
            "status": "success",
            "exit_code": 0,
            "duration_seconds": round(total_wall_seconds, 3),
        },
        "parse_step_status": {
            "name": f"parse_{descriptor.benchmark_target}",
            "status": "success",
            "exit_code": None,
            "duration_seconds": round(total_parse_seconds, 3),
        },
        "correctness_step_status": {
            "name": "benchmark_correctness_check",
            "status": "success" if correctness_passed else "failed",
            "exit_code": None,
            "duration_seconds": 0.0,
        },
    }


def merge_repeated_benchmark_artifacts(
    existing: dict[str, Any],
    additional: dict[str, Any],
    descriptor: SolverBenchmarkDescriptor,
    build_type: str,
) -> dict[str, Any]:
    """Merge two repeated benchmark artifacts and recompute median aggregates."""

    existing_samples = existing.get("repeated_benchmark_samples")
    additional_samples = additional.get("repeated_benchmark_samples")
    if not isinstance(existing_samples, list) or not isinstance(additional_samples, list):
        raise ValueError("both benchmark artifacts must contain repeated_benchmark_samples")
    samples = [*existing_samples, *additional_samples]
    total_wall = _number_or_zero(
        (existing.get("repeated_benchmark_aggregate") or {}).get("total_benchmark_wall_seconds")
    ) + _number_or_zero(
        (additional.get("repeated_benchmark_aggregate") or {}).get("total_benchmark_wall_seconds")
    )
    return benchmark_artifact_from_repeated_samples(
        samples,
        descriptor,
        build_type,
        template=existing,
        total_benchmark_wall_seconds=round(total_wall, 3),
    )


def _failed_result(
    descriptor: SolverBenchmarkDescriptor,
    build_type: str,
    step_name: str,
    failed_step: str,
    run_index: int,
    total_wall_seconds: float,
    error_message: str,
) -> dict[str, Any]:
    benchmark = empty_benchmark_artifact(descriptor, raw_output_available=True, build_type=build_type)
    benchmark["parse_errors"] = [error_message]
    benchmark["benchmark_run_count"] = 0
    benchmark["decision_metric"] = DECISION_METRIC
    benchmark["repeated_benchmark_samples"] = []
    benchmark["repeated_benchmark_aggregate"] = {
        "benchmark_run_count": 0,
        "decision_metric": DECISION_METRIC,
        "median_runtime_ns_per_problem_median": None,
        "min_runtime_ns_per_problem_median": None,
        "total_benchmark_wall_seconds": round(total_wall_seconds, 3),
    }
    return {
        "success": False,
        "failed_step": failed_step,
        "failed_run_index": run_index,
        "error_message": error_message,
        "benchmark": benchmark,
        "run_step_status": {
            "name": step_name,
            "status": "failed",
            "exit_code": None,
            "duration_seconds": round(total_wall_seconds, 3),
        },
        "parse_step_status": {
            "name": f"parse_{descriptor.benchmark_target}",
            "status": "skipped",
            "exit_code": None,
            "duration_seconds": None,
        },
        "correctness_step_status": {
            "name": "benchmark_correctness_check",
            "status": "skipped",
            "exit_code": None,
            "duration_seconds": None,
        },
    }


def _sample_from_metrics(
    run_index: int,
    metrics: dict[str, Any],
    runtime: float,
    wall_seconds: float,
) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "run_index": run_index,
        "runtime_ns_per_problem_median": runtime,
        "wall_seconds": wall_seconds,
    }
    for key in (
        "solver_name",
        "num_problems",
        "total_solutions",
        "solutions_per_problem",
        "valid_solutions",
        "valid_solutions_percent",
        "gt_found",
        "gt_found_percent",
        "runtime_ns_total_median",
        "correctness_passed",
        "tolerance",
        "camera_fov",
        "n_point_point",
        "n_point_line",
        "timed_iterations",
        "runtime_unit",
    ):
        value = _metric_value(metrics, key)
        if value is not None:
            sample[key] = value
    return sample


def _runtime_value(metrics: dict[str, Any]) -> object:
    return _metric_value(metrics, "runtime_ns_per_problem_median")


def _metric_value(metrics: dict[str, Any], key: str) -> object:
    if key in metrics:
        return metrics[key]
    parsed_key = f"parsed_{key}"
    if parsed_key in metrics:
        return metrics[parsed_key]
    return None


def _is_positive_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def _number_or_zero(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return 0.0


def median(values: list[float]) -> float:
    """Expose median for focused tests without exposing mean/max helpers."""

    return float(statistics.median(values))
