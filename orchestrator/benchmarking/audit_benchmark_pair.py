"""CLI for auditing baseline/candidate benchmark artifact comparability."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.benchmarking.benchmark_artifact_audit import (
    audit_comparable_benchmark_pair,
    load_baseline_benchmark_artifact,
    load_candidate_benchmark_artifact,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit whether baseline and candidate benchmark artifacts are comparable."
    )
    parser.add_argument("--baseline-run", required=True, help="Baseline run directory.")
    parser.add_argument("--candidate-run", required=True, help="Candidate run directory.")
    return parser.parse_args(argv)


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _format_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _print_summary(
    baseline_run: Path,
    candidate_run: Path,
    audit: dict,
) -> None:
    baseline = audit["baseline"]["normalized_artifact"]
    candidate = audit["candidate"]["normalized_artifact"]
    print(f"Baseline run: {baseline_run}")
    print(f"Candidate run: {candidate_run}")
    print(f"Comparable: {_format_value(audit['comparable'])}")
    print(f"Family: {_format_value(baseline.get('family'))}")
    print(f"Solver: {_format_value(baseline.get('solver'))}")
    print(f"Num cases: {_format_value(baseline.get('parsed_num_cases'))}")
    print(
        "Baseline runtime ns per case: "
        f"{_format_value(baseline.get('parsed_runtime_ns_per_case_median'))}"
    )
    print(
        "Candidate runtime ns per case: "
        f"{_format_value(candidate.get('parsed_runtime_ns_per_case_median'))}"
    )
    failed_checks = audit["failed_checks"]
    warnings = audit["warnings"]
    print("Failed checks: " + (", ".join(failed_checks) if failed_checks else "none"))
    print("Warnings: " + (", ".join(warnings) if warnings else "none"))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    baseline_run = _resolve_path(args.baseline_run)
    candidate_run = _resolve_path(args.candidate_run)

    baseline_artifact = load_baseline_benchmark_artifact(baseline_run)
    candidate_artifact = load_candidate_benchmark_artifact(candidate_run)
    audit = audit_comparable_benchmark_pair(baseline_artifact, candidate_artifact)

    output_path = candidate_run / "benchmark_artifact_audit.json"
    output_path.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    _print_summary(baseline_run, candidate_run, audit)
    print(f"Audit artifact: {output_path}")
    return 0 if audit["comparable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
