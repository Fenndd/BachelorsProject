"""Normalized benchmark artifact builders.

These functions produce the ``benchmark`` section of ``verification.json``
and the ``benchmark`` fields stored in ``metrics.json``. Every artifact
conforms to the schema expected by the audit, decision, and reporting layers.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from orchestrator.core.benchmarking.solver_registry import SolverBenchmarkDescriptor


DECISION_METRIC = "median_runtime_ns_per_problem_median"


def benchmark_required_fields() -> list[str]:
    """Return the ordered list of fields that must be present in a parsed benchmark."""
    return [
        "solver_name",
        "num_problems",
        "total_solutions",
        "solutions_per_problem",
        "valid_solutions",
        "valid_solutions_percent",
        "gt_found",
        "gt_found_percent",
        "runtime_ns_total_median",
        "runtime_ns_per_problem_median",
        "correctness_passed",
    ]


def empty_benchmark_artifact(
    descriptor: SolverBenchmarkDescriptor,
    raw_output_available: bool = False,
    build_type: str = "Release",
) -> dict[str, Any]:
    """Return a normalized benchmark artifact representing an unexecuted or failed run."""
    return {
        "family": descriptor.family,
        "solver": descriptor.solver_id,
        "runtime_unit": descriptor.runtime_unit,
        "build_type": build_type,
        "raw_output_available": raw_output_available,
        "parse_success": False,
        "missing_fields": list(benchmark_required_fields()),
        "parse_errors": [],
        "parsed_solver_name": None,
        "parsed_num_problems": None,
        "parsed_total_solutions": None,
        "parsed_solutions_per_problem": None,
        "parsed_valid_solutions": None,
        "parsed_valid_solutions_percent": None,
        "parsed_gt_found": None,
        "parsed_gt_found_percent": None,
        "parsed_runtime_ns_total_median": None,
        "parsed_runtime_ns_per_problem_median": None,
        "parsed_correctness_passed": None,
        "benchmark_options": None,
        "benchmark_run_count": 0,
        "decision_metric": DECISION_METRIC,
        "repeated_benchmark_samples": [],
        "repeated_benchmark_aggregate": {
            "benchmark_run_count": 0,
            "decision_metric": DECISION_METRIC,
            "median_runtime_ns_per_problem_median": None,
            "min_runtime_ns_per_problem_median": None,
            "total_benchmark_wall_seconds": 0.0,
        },
    }


def benchmark_artifact_from_repeated_samples(
    samples: list[dict[str, Any]],
    descriptor: SolverBenchmarkDescriptor,
    build_type: str,
    *,
    parse_results: list[dict[str, Any]] | None = None,
    template: dict[str, Any] | None = None,
    total_benchmark_wall_seconds: float | None = None,
) -> dict[str, Any]:
    """Build a normalized benchmark artifact from repeated parsed samples."""

    if not samples:
        artifact = empty_benchmark_artifact(descriptor, raw_output_available=False, build_type=build_type)
        artifact["parse_errors"] = ["no repeated benchmark samples were provided"]
        return artifact

    runtimes = [_number(sample.get("runtime_ns_per_problem_median")) for sample in samples]
    if any(value is None for value in runtimes):
        artifact = empty_benchmark_artifact(descriptor, raw_output_available=True, build_type=build_type)
        artifact["parse_errors"] = ["at least one repeated sample is missing runtime_ns_per_problem_median"]
        return artifact

    numeric_runtime_values = [float(value) for value in runtimes if value is not None]
    benchmark_options = _benchmark_options_from_parse_results(parse_results, build_type)
    if benchmark_options is None and isinstance(template, dict):
        benchmark_options = template.get("benchmark_options")

    aggregate = {
        "benchmark_run_count": len(samples),
        "decision_metric": DECISION_METRIC,
        "median_runtime_ns_per_problem_median": _median(numeric_runtime_values),
        "min_runtime_ns_per_problem_median": min(numeric_runtime_values),
        "total_benchmark_wall_seconds": (
            total_benchmark_wall_seconds
            if total_benchmark_wall_seconds is not None
            else _sum_numeric(sample.get("wall_seconds") for sample in samples)
        ),
    }

    artifact = {
        "family": descriptor.family,
        "solver": descriptor.solver_id,
        "runtime_unit": descriptor.runtime_unit,
        "build_type": build_type,
        "raw_output_available": True,
        "parse_success": True,
        "missing_fields": [],
        "parse_errors": [],
        "parsed_solver_name": _first_non_none(samples, "solver_name"),
        "parsed_num_problems": _median_sample_field(samples, "num_problems"),
        "parsed_total_solutions": _median_sample_field(samples, "total_solutions"),
        "parsed_solutions_per_problem": _median_sample_field(samples, "solutions_per_problem"),
        "parsed_valid_solutions": _median_sample_field(samples, "valid_solutions"),
        "parsed_valid_solutions_percent": _median_sample_field(samples, "valid_solutions_percent"),
        "parsed_gt_found": _median_sample_field(samples, "gt_found"),
        "parsed_gt_found_percent": _median_sample_field(samples, "gt_found_percent"),
        "parsed_runtime_ns_total_median": _median_sample_field(samples, "runtime_ns_total_median"),
        "parsed_runtime_ns_per_problem_median": aggregate["median_runtime_ns_per_problem_median"],
        "parsed_correctness_passed": all(sample.get("correctness_passed") is True for sample in samples),
        "benchmark_options": benchmark_options,
        "benchmark_run_count": len(samples),
        "decision_metric": DECISION_METRIC,
        "repeated_benchmark_samples": samples,
        "repeated_benchmark_aggregate": aggregate,
    }
    if artifact["parsed_solver_name"] is None and isinstance(template, dict):
        artifact["parsed_solver_name"] = template.get("parsed_solver_name")
    return artifact


def benchmark_artifact_from_parse(
    parse_result: dict[str, Any],
    descriptor: SolverBenchmarkDescriptor,
    build_type: str,
) -> dict[str, Any]:
    """Build a normalized benchmark artifact from a parse result."""
    parsed_metrics = parse_result["metrics"]

    benchmark_options = None
    if all(k in parsed_metrics for k in (
        "num_problems", "tolerance", "camera_fov", "n_point_point",
        "n_point_line", "timed_iterations", "runtime_unit",
    )):
        benchmark_options = {
            "num_problems": parsed_metrics["num_problems"],
            "tolerance": parsed_metrics["tolerance"],
            "camera_fov": parsed_metrics["camera_fov"],
            "n_point_point": parsed_metrics["n_point_point"],
            "n_point_line": parsed_metrics["n_point_line"],
            "timed_iterations": parsed_metrics["timed_iterations"],
            "runtime_unit": parsed_metrics["runtime_unit"],
            "build_type": build_type,
        }

    artifact = {
        "family": descriptor.family,
        "solver": descriptor.solver_id,
        "runtime_unit": descriptor.runtime_unit,
        "build_type": build_type,
        "raw_output_available": True,
        "parse_success": parse_result["parse_success"],
        "missing_fields": parse_result["missing_fields"],
        "parse_errors": parse_result["parse_errors"],
        "parsed_solver_name": parsed_metrics.get("solver_name"),
        "parsed_num_problems": parsed_metrics.get("num_problems"),
        "parsed_total_solutions": parsed_metrics.get("total_solutions"),
        "parsed_solutions_per_problem": parsed_metrics.get("solutions_per_problem"),
        "parsed_valid_solutions": parsed_metrics.get("valid_solutions"),
        "parsed_valid_solutions_percent": parsed_metrics.get("valid_solutions_percent"),
        "parsed_gt_found": parsed_metrics.get("gt_found"),
        "parsed_gt_found_percent": parsed_metrics.get("gt_found_percent"),
        "parsed_runtime_ns_total_median": parsed_metrics.get("runtime_ns_total_median"),
        "parsed_runtime_ns_per_problem_median": parsed_metrics.get("runtime_ns_per_problem_median"),
        "parsed_correctness_passed": parsed_metrics.get("correctness_passed"),
        "benchmark_options": benchmark_options,
    }
    if parse_result.get("parse_success") is True:
        sample = {
            "run_index": 1,
            "runtime_ns_per_problem_median": parsed_metrics.get("runtime_ns_per_problem_median"),
            "gt_found_percent": parsed_metrics.get("gt_found_percent"),
            "valid_solutions_percent": parsed_metrics.get("valid_solutions_percent"),
            "wall_seconds": 0.0,
        }
        artifact.update(
            {
                "benchmark_run_count": 1,
                "decision_metric": DECISION_METRIC,
                "repeated_benchmark_samples": [sample],
                "repeated_benchmark_aggregate": {
                    "benchmark_run_count": 1,
                    "decision_metric": DECISION_METRIC,
                    "median_runtime_ns_per_problem_median": parsed_metrics.get("runtime_ns_per_problem_median"),
                    "min_runtime_ns_per_problem_median": parsed_metrics.get("runtime_ns_per_problem_median"),
                    "total_benchmark_wall_seconds": 0.0,
                },
            }
        )
    return artifact


def build_benchmark_correctness_error_message(benchmark: dict[str, Any]) -> str:
    """Build an error message describing a benchmark that failed the correctness check."""
    return (
        "Family benchmark parsed successfully, but correctness_passed=false. "
        "The candidate is numerically incorrect and is not usable for comparison. "
        f"gt_found_percent={benchmark.get('parsed_gt_found_percent')!r}, "
        "valid_solutions_percent="
        f"{benchmark.get('parsed_valid_solutions_percent')!r}, "
        "runtime_ns_per_problem_median="
        f"{benchmark.get('parsed_runtime_ns_per_problem_median')!r}."
    )


def _benchmark_options_from_parse_results(
    parse_results: list[dict[str, Any]] | None,
    build_type: str,
) -> dict[str, Any] | None:
    if not parse_results:
        return None
    metrics = parse_results[0].get("metrics")
    if not isinstance(metrics, dict):
        return None
    if all(k in metrics for k in (
        "num_problems", "tolerance", "camera_fov", "n_point_point",
        "n_point_line", "timed_iterations", "runtime_unit",
    )):
        return {
            "num_problems": metrics["num_problems"],
            "tolerance": metrics["tolerance"],
            "camera_fov": metrics["camera_fov"],
            "n_point_point": metrics["n_point_point"],
            "n_point_line": metrics["n_point_line"],
            "timed_iterations": metrics["timed_iterations"],
            "runtime_unit": metrics["runtime_unit"],
            "build_type": build_type,
        }
    return None


def _median_sample_field(samples: list[dict[str, Any]], field_name: str) -> float | None:
    values = [_number(sample.get(field_name)) for sample in samples]
    numeric_values = [float(value) for value in values if value is not None]
    if len(numeric_values) != len(samples):
        return None
    return _median(numeric_values)


def _median(values: list[float]) -> float:
    return float(statistics.median(values))


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    return None


def _sum_numeric(values: Any) -> float:
    total = 0.0
    for value in values:
        number = _number(value)
        if number is not None:
            total += number
    return round(total, 3)


def _first_non_none(samples: list[dict[str, Any]], field_name: str) -> Any:
    for sample in samples:
        value = sample.get(field_name)
        if value is not None:
            return value
    return None
