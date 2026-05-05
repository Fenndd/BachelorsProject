"""Pairwise baseline-vs-candidate benchmark decision helpers.

This module evaluates exactly one candidate run against exactly one baseline run.
It relies on the existing benchmark artifact audit module for artifact loading and
comparability checks, then applies correctness-first acceptance gates.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.benchmarking.benchmark_artifact_audit import (
    audit_comparable_benchmark_pair,
    load_baseline_benchmark_artifact,
    load_candidate_benchmark_artifact,
)


@dataclass(frozen=True)
class CandidateDecisionThresholds:
    """Conservative correctness-tolerance thresholds for pairwise decision."""

    allowed_success_rate_drop: float = 0.0
    max_mean_reprojection_error_ratio: float = 1.05
    max_max_reprojection_error_ratio: float = 1.05


def evaluate_candidate_against_baseline(
    baseline_run_dir: Path,
    candidate_run_dir: Path,
    thresholds: CandidateDecisionThresholds | None = None,
) -> dict[str, Any]:
    """Evaluate one candidate run against one baseline run.

    The function first invokes the benchmark artifact audit to verify data loading
    and comparability. It then applies correctness-first rejection gates and, when
    valid, runtime comparison using parsed_runtime_ns_per_case_median.
    """

    baseline_path = Path(baseline_run_dir)
    candidate_path = Path(candidate_run_dir)
    effective_thresholds = thresholds or CandidateDecisionThresholds()

    baseline_artifact = load_baseline_benchmark_artifact(baseline_path)
    candidate_artifact = load_candidate_benchmark_artifact(candidate_path)
    audit = audit_comparable_benchmark_pair(baseline_artifact, candidate_artifact)

    baseline = _normalized_from_audit(audit, "baseline")
    candidate = _normalized_from_audit(audit, "candidate")

    rejection_reasons: list[str] = []
    if audit.get("comparable") is not True:
        rejection_reasons.append("audit_not_comparable")
        rejection_reasons.extend(_audit_failed_check_reasons(audit))

    if candidate.get("parsed_correctness_passed") is not True:
        rejection_reasons.append("candidate_correctness_not_true")
    if baseline.get("parsed_correctness_passed") is not True:
        rejection_reasons.append("baseline_correctness_not_true")

    baseline_runtime = baseline.get("parsed_runtime_ns_per_case_median")
    candidate_runtime = candidate.get("parsed_runtime_ns_per_case_median")
    baseline_runtime_num = _to_finite_number(baseline_runtime)
    candidate_runtime_num = _to_finite_number(candidate_runtime)

    if not _is_positive_finite_number(baseline_runtime):
        rejection_reasons.append("baseline_runtime_invalid")
    if not _is_positive_finite_number(candidate_runtime):
        rejection_reasons.append("candidate_runtime_invalid")

    baseline_success_rate = _to_finite_number(baseline.get("parsed_success_rate"))
    candidate_success_rate = _to_finite_number(candidate.get("parsed_success_rate"))
    if baseline_success_rate is not None and candidate_success_rate is not None:
        min_allowed_success_rate = (
            baseline_success_rate - effective_thresholds.allowed_success_rate_drop
        )
        if candidate_success_rate < min_allowed_success_rate:
            rejection_reasons.append(
                "candidate_success_rate_below_minimum"
                f"(candidate={candidate_success_rate}, minimum={min_allowed_success_rate})"
            )

    baseline_mean_error = _to_finite_number(
        baseline.get("parsed_mean_best_reprojection_error")
    )
    candidate_mean_error = _to_finite_number(
        candidate.get("parsed_mean_best_reprojection_error")
    )
    if baseline_mean_error is not None and candidate_mean_error is not None:
        max_allowed_mean_error = (
            baseline_mean_error * effective_thresholds.max_mean_reprojection_error_ratio
        )
        if candidate_mean_error > max_allowed_mean_error:
            rejection_reasons.append(
                "candidate_mean_reprojection_error_exceeds_limit"
                f"(candidate={candidate_mean_error}, maximum={max_allowed_mean_error})"
            )

    baseline_max_error = _to_finite_number(
        baseline.get("parsed_max_best_reprojection_error")
    )
    candidate_max_error = _to_finite_number(candidate.get("parsed_max_best_reprojection_error"))
    if baseline_max_error is not None and candidate_max_error is not None:
        max_allowed_max_error = (
            baseline_max_error * effective_thresholds.max_max_reprojection_error_ratio
        )
        if candidate_max_error > max_allowed_max_error:
            rejection_reasons.append(
                "candidate_max_reprojection_error_exceeds_limit"
                f"(candidate={candidate_max_error}, maximum={max_allowed_max_error})"
            )

    rejection_reasons = _unique_preserving_order(rejection_reasons)
    comparison = {
        "speedup": None,
        "runtime_reduction_percent": None,
        "candidate_runtime_lower": False,
    }

    if rejection_reasons:
        status = "rejected"
    else:
        if baseline_runtime_num is None or candidate_runtime_num is None:
            status = "rejected"
            rejection_reasons.append("runtime_comparison_unavailable")
        else:
            candidate_runtime_lower = candidate_runtime_num < baseline_runtime_num
            speedup = baseline_runtime_num / candidate_runtime_num
            runtime_reduction_percent = (
                (baseline_runtime_num - candidate_runtime_num) / baseline_runtime_num
            ) * 100.0
            comparison = {
                "speedup": speedup,
                "runtime_reduction_percent": runtime_reduction_percent,
                "candidate_runtime_lower": candidate_runtime_lower,
            }
            status = (
                "accepted_improvement"
                if candidate_runtime_lower
                else "valid_not_improved"
            )

    return {
        "status": status,
        "baseline_run_dir": str(baseline_path),
        "candidate_run_dir": str(candidate_path),
        "audit": audit,
        "audit_issues": _audit_issues(audit),
        "thresholds": asdict(effective_thresholds),
        "rejection_reasons": rejection_reasons,
        "baseline_metrics": _metrics_summary(baseline),
        "candidate_metrics": _metrics_summary(candidate),
        "comparison": comparison,
    }


def _normalized_from_audit(audit: dict[str, Any], role: str) -> dict[str, Any]:
    role_audit = audit.get(role)
    if not isinstance(role_audit, dict):
        return {}
    normalized = role_audit.get("normalized_artifact")
    if isinstance(normalized, dict):
        return normalized
    return {}


def _audit_failed_check_reasons(audit: dict[str, Any]) -> list[str]:
    failed_checks = audit.get("failed_checks")
    if not isinstance(failed_checks, list):
        return []
    return [f"audit_failed_check:{check}" for check in failed_checks]


def _audit_issues(audit: dict[str, Any]) -> dict[str, Any]:
    failed_checks = audit.get("failed_checks")
    warnings = audit.get("warnings")
    checks = audit.get("checks")
    return {
        "failed_checks": list(failed_checks) if isinstance(failed_checks, list) else [],
        "warnings": list(warnings) if isinstance(warnings, list) else [],
        "checks": checks if isinstance(checks, dict) else {},
    }


def _metrics_summary(normalized_artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_ns_per_case_median": normalized_artifact.get(
            "parsed_runtime_ns_per_case_median"
        ),
        "success_rate": normalized_artifact.get("parsed_success_rate"),
        "mean_best_reprojection_error": normalized_artifact.get(
            "parsed_mean_best_reprojection_error"
        ),
        "max_best_reprojection_error": normalized_artifact.get(
            "parsed_max_best_reprojection_error"
        ),
        "correctness_passed": normalized_artifact.get("parsed_correctness_passed"),
    }


def _to_finite_number(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return numeric


def _is_positive_finite_number(value: object) -> bool:
    numeric = _to_finite_number(value)
    return numeric is not None and numeric > 0.0


def _unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate one candidate run against one baseline run."
    )
    parser.add_argument("--baseline-run", required=True, help="Baseline run directory.")
    parser.add_argument("--candidate-run", required=True, help="Candidate run directory.")
    return parser.parse_args(argv)


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(sys.argv[1:] if argv is None else argv)
        baseline_run = _resolve_path(args.baseline_run)
        candidate_run = _resolve_path(args.candidate_run)

        decision = evaluate_candidate_against_baseline(baseline_run, candidate_run)
        decision_json = json.dumps(decision, indent=2, ensure_ascii=False)
        print(decision_json)

        output_path = candidate_run / "candidate_decision.json"
        output_path.write_text(decision_json + "\n", encoding="utf-8")

        status = decision.get("status")
        if status == "rejected":
            return 1
        if status in {"valid_not_improved", "accepted_improvement"}:
            return 0
        return 2
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        return code if code in {0, 1, 2} else 2
    except Exception as exc:
        print(f"candidate_decision_internal_error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())