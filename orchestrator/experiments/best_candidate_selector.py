"""Experiment-level multi-candidate best result selection.

This module evaluates multiple candidate runs against a single baseline run by
reusing the pairwise decision logic from
orchestrator.benchmarking.candidate_decision. It does not duplicate benchmark
audit gates or correctness/runtime acceptance policy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.benchmarking.candidate_decision import (
    evaluate_candidate_against_baseline,
    write_candidate_decision,
)


def select_best_candidate(
    baseline_run_dir: Path,
    candidate_run_dirs: list[Path],
    *,
    write_candidate_decisions: bool = True,
) -> dict[str, Any]:
    """Evaluate many candidates against one baseline and select the best valid one.

    Selection eligibility is limited to pairwise decisions with status
    "accepted_improvement". The ranking rule then applies deterministic tie-breaks.
    """

    baseline_path = Path(baseline_run_dir)
    candidate_paths = [Path(path) for path in candidate_run_dirs]

    if not candidate_paths:
        return {
            "baseline_run_dir": str(baseline_path),
            "candidate_run_dirs": [],
            "overall_status": "no_candidates",
            "best_candidate_run_dir": None,
            "best_candidate_decision_path": None,
            "counts": {
                "total": 0,
                "rejected": 0,
                "valid_not_improved": 0,
                "accepted_improvement": 0,
            },
            "best_metrics": {
                "runtime_ns_per_case_median": None,
                "speedup": None,
                "runtime_reduction_percent": None,
                "success_rate": None,
                "mean_best_reprojection_error": None,
                "max_best_reprojection_error": None,
            },
            "decisions": [],
        }

    summaries: list[dict[str, Any]] = []
    rejected_count = 0
    valid_not_improved_count = 0
    accepted_improvement_count = 0

    for candidate_path in candidate_paths:
        decision = evaluate_candidate_against_baseline(baseline_path, candidate_path)
        decision_path: Path | None = None
        if write_candidate_decisions and candidate_path.is_dir():
            decision_path = write_candidate_decision(candidate_path, decision)
        summary = _decision_summary(candidate_path, decision, decision_path)
        summaries.append(summary)

        status = summary.get("status")
        if status == "rejected":
            rejected_count += 1
        elif status == "valid_not_improved":
            valid_not_improved_count += 1
        elif status == "accepted_improvement":
            accepted_improvement_count += 1

    best_summary: dict[str, Any] | None = None
    if accepted_improvement_count > 0:
        eligible = [
            (index, summary)
            for index, summary in enumerate(summaries)
            if summary.get("status") == "accepted_improvement"
        ]
        best_summary = min(eligible, key=_ranking_key)[1]

    if accepted_improvement_count > 0:
        overall_status = "best_candidate_found"
    elif valid_not_improved_count > 0:
        overall_status = "no_improvement_found"
    else:
        overall_status = "all_candidates_rejected"

    return {
        "baseline_run_dir": str(baseline_path),
        "candidate_run_dirs": [str(path) for path in candidate_paths],
        "overall_status": overall_status,
        "best_candidate_run_dir": (
            best_summary.get("candidate_run_dir") if best_summary is not None else None
        ),
        "best_candidate_decision_path": (
            best_summary.get("candidate_decision_path") if best_summary is not None else None
        ),
        "counts": {
            "total": len(candidate_paths),
            "rejected": rejected_count,
            "valid_not_improved": valid_not_improved_count,
            "accepted_improvement": accepted_improvement_count,
        },
        "best_metrics": _best_metrics(best_summary),
        "decisions": summaries,
    }


def _decision_summary(
    candidate_run_dir: Path,
    decision: dict[str, Any],
    decision_path: Path | None,
) -> dict[str, Any]:
    candidate_metrics = decision.get("candidate_metrics")
    candidate_metrics = candidate_metrics if isinstance(candidate_metrics, dict) else {}

    comparison = decision.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}

    rejection_reasons = decision.get("rejection_reasons")
    if not isinstance(rejection_reasons, list):
        rejection_reasons = []

    existing_decision_path = candidate_run_dir / "candidate_decision.json"
    if decision_path is not None:
        decision_path_text = str(decision_path)
    elif existing_decision_path.exists():
        decision_path_text = str(existing_decision_path)
    else:
        decision_path_text = None

    return {
        "candidate_run_dir": str(candidate_run_dir),
        "status": decision.get("status"),
        "candidate_decision_path": decision_path_text,
        "runtime_ns_per_case_median": candidate_metrics.get("runtime_ns_per_case_median"),
        "speedup": comparison.get("speedup"),
        "runtime_reduction_percent": comparison.get("runtime_reduction_percent"),
        "success_rate": candidate_metrics.get("success_rate"),
        "mean_best_reprojection_error": candidate_metrics.get(
            "mean_best_reprojection_error"
        ),
        "max_best_reprojection_error": candidate_metrics.get("max_best_reprojection_error"),
        "rejection_reasons": rejection_reasons,
    }


def _best_metrics(best_summary: dict[str, Any] | None) -> dict[str, Any]:
    if best_summary is None:
        return {
            "runtime_ns_per_case_median": None,
            "speedup": None,
            "runtime_reduction_percent": None,
            "success_rate": None,
            "mean_best_reprojection_error": None,
            "max_best_reprojection_error": None,
        }

    return {
        "runtime_ns_per_case_median": best_summary.get("runtime_ns_per_case_median"),
        "speedup": best_summary.get("speedup"),
        "runtime_reduction_percent": best_summary.get("runtime_reduction_percent"),
        "success_rate": best_summary.get("success_rate"),
        "mean_best_reprojection_error": best_summary.get("mean_best_reprojection_error"),
        "max_best_reprojection_error": best_summary.get("max_best_reprojection_error"),
    }


def _finite_or_inf(value: object, *, higher_is_better: bool) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return math.inf if not higher_is_better else -math.inf
    numeric = float(value)
    if not math.isfinite(numeric):
        return math.inf if not higher_is_better else -math.inf
    return numeric


def _ranking_key(item: tuple[int, dict[str, Any]]) -> tuple[float, float, float, float, int]:
    """Return deterministic rank key for accepted improvements.

    Lower tuple values are better.
    """

    input_index, summary = item
    runtime = _finite_or_inf(summary.get("runtime_ns_per_case_median"), higher_is_better=False)
    success_rate = _finite_or_inf(summary.get("success_rate"), higher_is_better=True)
    mean_error = _finite_or_inf(
        summary.get("mean_best_reprojection_error"), higher_is_better=False
    )
    max_error = _finite_or_inf(
        summary.get("max_best_reprojection_error"), higher_is_better=False
    )
    return (runtime, -success_rate, mean_error, max_error, input_index)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select the best candidate among multiple candidate run directories."
    )
    parser.add_argument("--baseline-run", required=True, help="Baseline run directory.")
    parser.add_argument(
        "--candidate-run",
        action="append",
        default=[],
        help="Candidate run directory. Repeat this argument for multiple candidates.",
    )
    parser.add_argument(
        "--output",
        required=False,
        help="Optional path where selection JSON should be written.",
    )
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
        candidate_runs = [_resolve_path(path_text) for path_text in args.candidate_run]

        selection = select_best_candidate(baseline_run, candidate_runs)
        selection_json = json.dumps(selection, indent=2, ensure_ascii=False)
        print(selection_json)

        if args.output:
            output_path = _resolve_path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(selection_json + "\n", encoding="utf-8")

        status = selection.get("overall_status")
        if status in {"best_candidate_found", "no_improvement_found"}:
            return 0
        if status in {"all_candidates_rejected", "no_candidates"}:
            return 1
        return 2
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        return code if code in {0, 1, 2} else 2
    except Exception as exc:
        print(f"best_candidate_selector_internal_error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
