"""Audit benchmark artifacts for safe future comparison.

This module checks whether reference and candidate benchmark metric artifacts are
well-formed and comparable. It intentionally does not decide which artifact is
better, faster, accepted, or rejected.

Baseline-vs-candidate helpers remain available for backward compatibility with
the original selection path.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


BENCHMARK_FIELDS = [
    "family",
    "solver",
    "parse_success",
    "parsed_num_cases",
    "parsed_success_rate",
    "parsed_mean_best_reprojection_error",
    "parsed_max_best_reprojection_error",
    "parsed_runtime_ns_total_median",
    "parsed_runtime_ns_per_case_median",
    "parsed_correctness_passed",
    "parsed_valid_cases",
    "parsed_total_solutions",
    "runtime_unit",
    "build_type",
    "benchmark_options",
]


def load_baseline_benchmark_artifact(run_dir: Path) -> dict[str, Any]:
    """Load the benchmark section from a baseline run's metrics.json."""
    metrics_path = Path(run_dir) / "metrics.json"
    return _load_benchmark_artifact(run_dir, metrics_path, "metrics.json")


def load_candidate_benchmark_artifact(candidate_run_dir: Path) -> dict[str, Any]:
    """Load the benchmark section from a candidate run's verification.json."""
    verification_path = Path(candidate_run_dir) / "verification.json"
    return _load_benchmark_artifact(
        candidate_run_dir,
        verification_path,
        "verification.json",
    )


def load_verified_candidate_benchmark_artifact(run_dir: Path) -> dict[str, Any]:
    """Load the benchmark section from a verified candidate run's verification.json."""
    return load_candidate_benchmark_artifact(run_dir)


def load_reference_benchmark_artifact(
    reference_run_dir: Path,
    reference_kind: str,
) -> dict[str, Any]:
    """Load a reference benchmark artifact using an explicit reference kind.

    Supported reference kinds are:
    - ``baseline``: load ``metrics.json``
    - ``verified_candidate``: load ``verification.json``
    """

    if reference_kind == "baseline":
        return load_baseline_benchmark_artifact(reference_run_dir)
    if reference_kind == "verified_candidate":
        return load_verified_candidate_benchmark_artifact(reference_run_dir)
    raise ValueError(
        "invalid reference_kind "
        f"{reference_kind!r}; expected one of: baseline, verified_candidate"
    )


def audit_single_benchmark_artifact(artifact: dict[str, Any], role: str) -> dict[str, Any]:
    """Audit one loaded benchmark artifact for required comparable fields."""
    failed_checks: list[str] = []
    warnings: list[str] = []
    normalized = _normalize_artifact(artifact)

    if not artifact.get("artifact_exists"):
        failed_checks.append("artifact_file_missing")
    if artifact.get("load_error"):
        failed_checks.append("artifact_load_error")
    if not artifact.get("benchmark_section_exists"):
        failed_checks.append("benchmark_section_missing")

    _check_present_string(normalized, "family", failed_checks)
    _check_present_string(normalized, "solver", failed_checks)
    if normalized.get("parse_success") is not True:
        failed_checks.append("parse_success_not_true")
    _check_positive_number(normalized, "parsed_num_cases", failed_checks)
    _check_positive_number(
        normalized,
        "parsed_runtime_ns_per_case_median",
        failed_checks,
    )
    _check_present_number(normalized, "parsed_success_rate", failed_checks)
    _check_present_bool(normalized, "parsed_correctness_passed", failed_checks)
    _check_present_number(
        normalized,
        "parsed_mean_best_reprojection_error",
        failed_checks,
    )
    _check_present_number(
        normalized,
        "parsed_max_best_reprojection_error",
        failed_checks,
    )

    runtime_unit = normalized.get("runtime_unit")
    if runtime_unit is None:
        warnings.append("runtime_unit_not_recorded_assuming_ns")
        normalized["runtime_unit"] = "ns"
    elif runtime_unit != "ns":
        failed_checks.append("runtime_unit_not_ns")

    return {
        "role": role,
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "warnings": warnings,
        "normalized_artifact": normalized,
    }


def audit_comparable_benchmark_pair(
    baseline_artifact: dict[str, Any],
    candidate_artifact: dict[str, Any],
) -> dict[str, Any]:
    """Audit whether two benchmark artifacts are safe to compare later."""
    audit = audit_comparable_benchmark_artifacts(
        baseline_artifact,
        candidate_artifact,
        reference_role="baseline",
        reference_invalid_check="baseline_artifact_invalid",
    )
    audit["baseline"] = audit["reference"]
    return audit


def audit_comparable_benchmark_artifacts(
    reference_artifact: dict[str, Any],
    candidate_artifact: dict[str, Any],
    *,
    reference_role: str = "reference",
    reference_invalid_check: str = "reference_artifact_invalid",
) -> dict[str, Any]:
    """Audit whether reference and candidate artifacts are safe to compare later."""
    reference_audit = audit_single_benchmark_artifact(reference_artifact, reference_role)
    candidate_audit = audit_single_benchmark_artifact(candidate_artifact, "candidate")
    reference = reference_audit["normalized_artifact"]
    candidate = candidate_audit["normalized_artifact"]

    checks = {
        "same_family": reference.get("family") == candidate.get("family")
        and reference.get("family") is not None,
        "same_solver": reference.get("solver") == candidate.get("solver")
        and reference.get("solver") is not None,
        "same_num_cases": reference.get("parsed_num_cases")
        == candidate.get("parsed_num_cases")
        and reference.get("parsed_num_cases") is not None,
        "runtime_available": _is_positive_number(
            reference.get("parsed_runtime_ns_per_case_median")
        )
        and _is_positive_number(candidate.get("parsed_runtime_ns_per_case_median")),
        "correctness_available": reference.get("parsed_correctness_passed") is not None
        and candidate.get("parsed_correctness_passed") is not None,
        "runtime_unit_ns": reference.get("runtime_unit") == "ns"
        and candidate.get("runtime_unit") == "ns",
    }

    failed_checks: list[str] = []
    warnings = list(reference_audit["warnings"]) + list(candidate_audit["warnings"])

    if not reference_audit["passed"]:
        failed_checks.append(reference_invalid_check)
    if not candidate_audit["passed"]:
        failed_checks.append("candidate_artifact_invalid")

    for check_name, passed in checks.items():
        if not passed:
            failed_checks.append(check_name)

    reference_options = reference.get("benchmark_options")
    candidate_options = candidate.get("benchmark_options")
    if reference_options is None or candidate_options is None:
        checks["same_benchmark_options"] = None
        warnings.append("benchmark_options_not_recorded")
    elif reference_options != candidate_options:
        checks["same_benchmark_options"] = False
        failed_checks.append("benchmark_options_mismatch")
    else:
        checks["same_benchmark_options"] = True

    reference_build_type = reference.get("build_type")
    candidate_build_type = candidate.get("build_type")
    if reference_build_type is None or candidate_build_type is None:
        checks["same_build_type"] = None
        warnings.append("build_type_not_recorded")
    elif reference_build_type != candidate_build_type:
        checks["same_build_type"] = False
        failed_checks.append("build_type_mismatch")
    else:
        checks["same_build_type"] = True

    comparable = not failed_checks
    return {
        "overall_status": "passed" if comparable else "failed",
        "comparable": comparable,
        "failed_checks": failed_checks,
        "warnings": _unique_preserving_order(warnings),
        "reference": reference_audit,
        "candidate": candidate_audit,
        "checks": checks,
    }


def _load_benchmark_artifact(
    run_dir: Path,
    artifact_path: Path,
    artifact_filename: str,
) -> dict[str, Any]:
    artifact = {
        "run_dir": str(Path(run_dir)),
        "artifact_path": str(artifact_path),
        "artifact_filename": artifact_filename,
        "artifact_exists": artifact_path.exists(),
        "benchmark_section_exists": False,
        "load_error": None,
        "benchmark": None,
    }
    if not artifact_path.exists():
        return artifact

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        artifact["load_error"] = str(exc)
        return artifact

    benchmark = payload.get("benchmark") if isinstance(payload, dict) else None
    if isinstance(benchmark, dict):
        artifact["benchmark_section_exists"] = True
        artifact["benchmark"] = benchmark
    return artifact


def _normalize_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    benchmark = artifact.get("benchmark")
    if not isinstance(benchmark, dict):
        benchmark = {}
    normalized = {field: benchmark.get(field) for field in BENCHMARK_FIELDS}
    normalized["source_artifact"] = artifact.get("artifact_path")
    return normalized


def _check_present_string(
    normalized: dict[str, Any],
    field_name: str,
    failed_checks: list[str],
) -> None:
    value = normalized.get(field_name)
    if not isinstance(value, str) or not value:
        failed_checks.append(f"{field_name}_missing")


def _check_present_bool(
    normalized: dict[str, Any],
    field_name: str,
    failed_checks: list[str],
) -> None:
    if not isinstance(normalized.get(field_name), bool):
        failed_checks.append(f"{field_name}_missing")


def _check_present_number(
    normalized: dict[str, Any],
    field_name: str,
    failed_checks: list[str],
) -> None:
    if not _is_number(normalized.get(field_name)):
        failed_checks.append(f"{field_name}_missing")


def _check_positive_number(
    normalized: dict[str, Any],
    field_name: str,
    failed_checks: list[str],
) -> None:
    if not _is_positive_number(normalized.get(field_name)):
        failed_checks.append(f"{field_name}_missing_or_non_positive")


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _is_positive_number(value: object) -> bool:
    return _is_number(value) and value > 0


def _unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values
