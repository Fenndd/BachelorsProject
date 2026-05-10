"""Pairwise reference-vs-candidate benchmark decision helpers.

This module evaluates exactly one candidate run against exactly one explicit
reference run. The reference may be the original baseline or a previously
verified candidate. Baseline-vs-candidate helpers remain available for backward
compatibility with the original selection path.
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
    audit_comparable_benchmark_artifacts,
    load_candidate_benchmark_artifact,
    load_reference_benchmark_artifact,
)


REFERENCE_KIND_BASELINE = "baseline"
REFERENCE_KIND_VERIFIED_CANDIDATE = "verified_candidate"
ALLOWED_REFERENCE_KINDS = {
    REFERENCE_KIND_BASELINE,
    REFERENCE_KIND_VERIFIED_CANDIDATE,
}


@dataclass(frozen=True)
class CandidateDecisionThresholds:
    """Conservative correctness-tolerance thresholds for pairwise decision."""

    allowed_success_rate_drop: float = 0.0
    max_mean_reprojection_error_ratio: float = 1.05
    max_max_reprojection_error_ratio: float = 1.05
    min_runtime_reduction_percent: float = 0.5
    absolute_reprojection_error_tolerance: float = 1.0e-10


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

    decision = evaluate_candidate_against_reference(
        baseline_run_dir,
        candidate_run_dir,
        reference_kind=REFERENCE_KIND_BASELINE,
        thresholds=thresholds,
    )
    decision["baseline_run_dir"] = decision["reference_run_dir"]
    decision["baseline_metrics"] = decision["reference_metrics"]
    if isinstance(decision.get("audit"), dict):
        decision["audit"].setdefault("baseline", decision["audit"].get("reference"))
    return decision


def evaluate_candidate_against_reference(
    reference_run_dir: Path,
    candidate_run_dir: Path,
    reference_kind: str,
    thresholds: CandidateDecisionThresholds | None = None,
) -> dict[str, Any]:
    """Evaluate one candidate run against one explicit reference run.

    ``reference_kind`` must be ``baseline`` or ``verified_candidate``. Baseline
    references load ``metrics.json``; verified-candidate references load
    ``verification.json``. Candidate metrics are always loaded from
    ``verification.json``.
    """

    _validate_reference_kind(reference_kind)

    reference_path = Path(reference_run_dir)
    candidate_path = Path(candidate_run_dir)
    effective_thresholds = thresholds or CandidateDecisionThresholds()

    reference_artifact = load_reference_benchmark_artifact(reference_path, reference_kind)
    candidate_artifact = load_candidate_benchmark_artifact(candidate_path)
    audit = audit_comparable_benchmark_artifacts(reference_artifact, candidate_artifact)

    reference = _normalized_from_audit(audit, "reference")
    candidate = _normalized_from_audit(audit, "candidate")

    rejection_reasons: list[str] = []
    if audit.get("comparable") is not True:
        rejection_reasons.append("audit_not_comparable")
        rejection_reasons.extend(_audit_failed_check_reasons(audit))

    if candidate.get("parsed_correctness_passed") is not True:
        rejection_reasons.append("candidate_correctness_not_true")
    if reference.get("parsed_correctness_passed") is not True:
        rejection_reasons.append("reference_correctness_not_true")

    reference_runtime = reference.get("parsed_runtime_ns_per_case_median")
    candidate_runtime = candidate.get("parsed_runtime_ns_per_case_median")
    reference_runtime_num = _to_finite_number(reference_runtime)
    candidate_runtime_num = _to_finite_number(candidate_runtime)

    if not _is_positive_finite_number(reference_runtime):
        rejection_reasons.append("reference_runtime_invalid")
    if not _is_positive_finite_number(candidate_runtime):
        rejection_reasons.append("candidate_runtime_invalid")

    reference_success_rate = _to_finite_number(reference.get("parsed_success_rate"))
    candidate_success_rate = _to_finite_number(candidate.get("parsed_success_rate"))
    if reference_success_rate is not None and candidate_success_rate is not None:
        min_allowed_success_rate = (
            reference_success_rate - effective_thresholds.allowed_success_rate_drop
        )
        if candidate_success_rate < min_allowed_success_rate:
            rejection_reasons.append(
                "candidate_success_rate_below_minimum"
                f"(candidate={candidate_success_rate}, minimum={min_allowed_success_rate})"
            )

    reference_mean_error = _to_finite_number(
        reference.get("parsed_mean_best_reprojection_error")
    )
    candidate_mean_error = _to_finite_number(
        candidate.get("parsed_mean_best_reprojection_error")
    )
    if reference_mean_error is not None and candidate_mean_error is not None:
        max_allowed_mean_error = max(
            reference_mean_error * effective_thresholds.max_mean_reprojection_error_ratio,
            effective_thresholds.absolute_reprojection_error_tolerance,
        )
        if candidate_mean_error > max_allowed_mean_error:
            rejection_reasons.append(
                "candidate_mean_reprojection_error_exceeds_limit"
                f"(candidate={candidate_mean_error}, maximum={max_allowed_mean_error})"
            )

    reference_max_error = _to_finite_number(
        reference.get("parsed_max_best_reprojection_error")
    )
    candidate_max_error = _to_finite_number(candidate.get("parsed_max_best_reprojection_error"))
    if reference_max_error is not None and candidate_max_error is not None:
        max_allowed_max_error = max(
            reference_max_error * effective_thresholds.max_max_reprojection_error_ratio,
            effective_thresholds.absolute_reprojection_error_tolerance,
        )
        if candidate_max_error > max_allowed_max_error:
            rejection_reasons.append(
                "candidate_max_reprojection_error_exceeds_limit"
                f"(candidate={candidate_max_error}, maximum={max_allowed_max_error})"
            )

    rejection_reasons = _unique_preserving_order(rejection_reasons)
    non_acceptance_reasons: list[str] = []
    comparison = {
        "speedup": None,
        "runtime_reduction_percent": None,
        "candidate_runtime_lower": False,
    }

    if rejection_reasons:
        status = "rejected"
    else:
        if reference_runtime_num is None or candidate_runtime_num is None:
            status = "rejected"
            rejection_reasons.append("runtime_comparison_unavailable")
        else:
            candidate_runtime_lower = candidate_runtime_num < reference_runtime_num
            speedup = reference_runtime_num / candidate_runtime_num
            runtime_reduction_percent = (
                (reference_runtime_num - candidate_runtime_num) / reference_runtime_num
            ) * 100.0
            comparison = {
                "speedup": speedup,
                "runtime_reduction_percent": runtime_reduction_percent,
                "candidate_runtime_lower": candidate_runtime_lower,
            }
            if (
                candidate_runtime_lower
                and runtime_reduction_percent
                >= effective_thresholds.min_runtime_reduction_percent
            ):
                status = "accepted_improvement"
            else:
                status = "valid_not_improved"
                if candidate_runtime_lower:
                    non_acceptance_reasons.append(
                        "runtime_improvement_below_minimum_threshold"
                    )

    return {
        "status": status,
        "reference_kind": reference_kind,
        "reference_run_dir": str(reference_path),
        "candidate_run_dir": str(candidate_path),
        "audit": audit,
        "audit_issues": _audit_issues(audit),
        "thresholds": asdict(effective_thresholds),
        "rejection_reasons": rejection_reasons,
        "non_acceptance_reasons": _unique_preserving_order(non_acceptance_reasons),
        "reference_metrics": _metrics_summary(reference),
        "candidate_metrics": _metrics_summary(candidate),
        "comparison": comparison,
    }


def write_candidate_decision(
    candidate_run_dir: Path,
    decision: dict[str, Any],
    filename: str = "candidate_decision.json",
) -> Path:
    """Write a pairwise candidate decision artifact and return its path."""

    candidate_path = Path(candidate_run_dir)
    safe_filename = _validate_decision_filename(filename)
    output_path = candidate_path / safe_filename
    output_path.write_text(
        json.dumps(decision, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def _validate_reference_kind(reference_kind: str) -> None:
    if reference_kind not in ALLOWED_REFERENCE_KINDS:
        raise ValueError(
            "invalid reference_kind "
            f"{reference_kind!r}; expected one of: baseline, verified_candidate"
        )


def _validate_decision_filename(filename: str) -> str:
    if not isinstance(filename, str) or not filename:
        raise ValueError("decision filename must be a non-empty string")
    filename_path = Path(filename)
    if filename_path.is_absolute():
        raise ValueError(f"unsafe decision filename {filename!r}: absolute paths are not allowed")
    if filename_path.name != filename:
        raise ValueError(
            f"unsafe decision filename {filename!r}: path separators are not allowed"
        )
    if "/" in filename or "\\" in filename:
        raise ValueError(
            f"unsafe decision filename {filename!r}: path separators are not allowed"
        )
    if filename in {".", ".."} or ".." in filename_path.parts:
        raise ValueError(f"unsafe decision filename {filename!r}: traversal is not allowed")
    return filename


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
        description="Evaluate one candidate run against one baseline or reference run."
    )
    parser.add_argument(
        "--baseline-run",
        required=False,
        help="Baseline run directory for backward-compatible baseline-vs-candidate mode.",
    )
    parser.add_argument(
        "--reference-run",
        required=False,
        help="Reference run directory for generic reference-vs-candidate mode.",
    )
    parser.add_argument(
        "--reference-kind",
        choices=sorted(ALLOWED_REFERENCE_KINDS),
        default=None,
        help="Reference artifact kind for --reference-run.",
    )
    parser.add_argument("--candidate-run", required=True, help="Candidate run directory.")
    parser.add_argument(
        "--output-filename",
        default="candidate_decision.json",
        help="Decision artifact filename to write inside the candidate run directory.",
    )
    args = parser.parse_args(argv)
    if args.baseline_run and args.reference_run:
        parser.error("use either --baseline-run or --reference-run, not both")
    if args.reference_run and not args.reference_kind:
        parser.error("--reference-kind is required when --reference-run is used")
    if args.reference_kind and not args.reference_run:
        parser.error("--reference-kind requires --reference-run")
    if not args.baseline_run and not args.reference_run:
        parser.error("one of --baseline-run or --reference-run is required")
    return args


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(sys.argv[1:] if argv is None else argv)
        candidate_run = _resolve_path(args.candidate_run)

        if args.baseline_run:
            baseline_run = _resolve_path(args.baseline_run)
            decision = evaluate_candidate_against_baseline(baseline_run, candidate_run)
        else:
            reference_run = _resolve_path(args.reference_run)
            decision = evaluate_candidate_against_reference(
                reference_run,
                candidate_run,
                reference_kind=args.reference_kind,
            )
        decision_json = json.dumps(decision, indent=2, ensure_ascii=False)
        print(decision_json)
        write_candidate_decision(candidate_run, decision, filename=args.output_filename)

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