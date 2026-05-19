"""Normalized benchmark artifact builders.

These functions produce the ``benchmark`` section of ``verification.json``
and the ``benchmark`` fields stored in ``metrics.json``. Every artifact
conforms to the schema expected by the audit, decision, and reporting layers.
"""

from __future__ import annotations

from typing import Any

from orchestrator.benchmarking.solver_registry import SolverBenchmarkDescriptor


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
    }


def benchmark_artifact_from_parse(
    stdout: str,
    parse_result: dict[str, Any],
    descriptor: SolverBenchmarkDescriptor,
    build_type: str,
) -> dict[str, Any]:
    """Build a normalized benchmark artifact from raw stdout and its parse result."""
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

    return {
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
