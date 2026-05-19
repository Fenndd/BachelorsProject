"""Read-only inspection helper for generated experiment reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_PLOTS = (
    "runtime_progress.svg",
    "candidate_runtime_by_iteration.svg",
    "runtime_reduction_by_iteration.svg",
    "correctness_metrics.svg",
    "status_breakdown.svg",
    "candidate_funnel.svg",
    "phase_timings.svg",
    "llm_tokens_by_iteration.svg",
    "llm_latency_by_iteration.svg",
    "failure_reason_breakdown.svg",
    "diff_stats_by_iteration.svg",
)

EXPECTED_SECTIONS = (
    "cover",
    "executive-summary",
    "experiment-configuration",
    "benchmark-configuration",
    "final-comparison",
    "baseline-metrics",
    "reproducibility-environment",
    "runtime-progress",
    "correctness-and-accuracy-safety",
    "status-breakdown",
    "candidate-funnel",
    "failure-analysis",
    "phase-timings",
    "llm-usage",
    "diff-statistics",
    "closed-loop-selection",
    "per-iteration-table",
    "final-best-candidate-summary",
    "reporting-status",
    "artifact-map",
    "iteration-appendix",
)

IMPORTANT_REPORT_DATA_KEYS = (
    "schema_version",
    "report_metadata",
    "experiment",
    "final_result",
    "baseline_metrics",
    "iterations",
    "status_counts",
    "artifacts",
)


def inspect_report(experiment_dir: Path | str) -> dict[str, Any]:
    """Inspect an existing generated report without regenerating or writing files."""

    experiment_path = Path(experiment_dir)
    report_dir = experiment_path / "report"
    report_data_path = report_dir / "report_data.json"
    html_path = report_dir / "report.html"
    pdf_path = report_dir / "report.pdf"
    plots_dir = report_dir / "plots"
    warnings: list[str] = []
    errors: list[str] = []

    result: dict[str, Any] = {
        "status": "ok",
        "experiment_dir": str(experiment_path),
        "report_dir": str(report_dir),
        "files": {},
        "plots": {},
        "sections": {},
        "warnings": warnings,
        "errors": errors,
    }

    if not experiment_path.is_dir():
        errors.append(f"Experiment directory does not exist: {experiment_path}")
    if not report_dir.is_dir():
        errors.append(f"Report directory does not exist: {report_dir}")

    report_data = _inspect_report_data(report_data_path, result, errors)
    html_text = _inspect_html(html_path, result, errors)
    _inspect_pdf(pdf_path, result, warnings, report_data)
    _inspect_plots(plots_dir, result, warnings, errors)
    _inspect_sections(html_text, result, warnings)

    result["status"] = _status(errors, warnings)
    return result


def _inspect_report_data(
    report_data_path: Path,
    result: dict[str, Any],
    errors: list[str],
) -> dict[str, Any] | None:
    warnings = result["warnings"]
    entry: dict[str, Any] = {
        "path": str(report_data_path),
        "exists": report_data_path.is_file(),
        "valid_json": False,
        "json_object": False,
    }
    result["files"]["report_data_json"] = entry
    if not report_data_path.is_file():
        errors.append(f"Missing report_data.json: {report_data_path}")
        return None
    try:
        payload = json.loads(report_data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid report_data.json: {exc}")
        return None
    entry["valid_json"] = True
    if not isinstance(payload, dict):
        errors.append("Invalid report_data.json: top-level payload must be a JSON object")
        return None
    entry["json_object"] = True
    entry["schema_version"] = payload.get("schema_version")
    missing_keys = [key for key in IMPORTANT_REPORT_DATA_KEYS if key not in payload]
    entry["missing_top_level_keys"] = missing_keys
    if "schema_version" not in payload:
        warnings.append("report_data.json is missing schema_version")
    if missing_keys:
        warnings.append(
            "report_data.json is missing important top-level key(s): "
            + ", ".join(missing_keys)
        )
    _inspect_final_selection_semantics(payload, warnings)
    return payload


def _inspect_final_selection_semantics(
    payload: dict[str, Any],
    warnings: list[str],
) -> None:
    final_selection = payload.get("final_selection")
    if not isinstance(final_selection, dict):
        return
    status = final_selection.get("status")
    speedup = final_selection.get("speedup_vs_original_baseline")
    if status == "failed" or (status not in {"completed", "skipped"} and not _is_number(speedup)):
        warnings.append(
            "final_selection comparison metrics are unavailable (status: "
            + str(status) + ")"
        )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _inspect_html(
    html_path: Path,
    result: dict[str, Any],
    errors: list[str],
) -> str | None:
    entry = {"path": str(html_path), "exists": html_path.is_file()}
    result["files"]["report_html"] = entry
    if not html_path.is_file():
        errors.append(f"Missing report.html: {html_path}")
        return None
    return html_path.read_text(encoding="utf-8", errors="replace")


def _inspect_pdf(
    pdf_path: Path,
    result: dict[str, Any],
    warnings: list[str],
    report_data: dict[str, Any] | None,
) -> None:
    exists = pdf_path.is_file()
    result["files"]["report_pdf"] = {"path": str(pdf_path), "exists": exists}
    requested_formats = _requested_report_formats(report_data)
    if not exists and (requested_formats is None or "pdf" in requested_formats):
        warnings.append(f"Missing report.pdf: {pdf_path}")


def _requested_report_formats(report_data: dict[str, Any] | None) -> set[str] | None:
    if not isinstance(report_data, dict):
        return None
    candidates = []
    reporting_status = report_data.get("reporting_status")
    if isinstance(reporting_status, dict):
        candidates.append(reporting_status.get("formats"))
    report_metadata = report_data.get("report_metadata")
    if isinstance(report_metadata, dict):
        reporting = report_metadata.get("reporting")
        if isinstance(reporting, dict):
            candidates.append(reporting.get("formats"))
    for value in candidates:
        if isinstance(value, list):
            return {str(item).strip().lower() for item in value if str(item).strip()}
    return None


def _inspect_plots(
    plots_dir: Path,
    result: dict[str, Any],
    warnings: list[str],
    errors: list[str],
) -> None:
    plots: dict[str, Any] = {
        "directory": str(plots_dir),
        "directory_exists": plots_dir.is_dir(),
        "expected": list(EXPECTED_PLOTS),
        "present": [],
        "missing": [],
    }
    result["plots"] = plots
    for filename in EXPECTED_PLOTS:
        path = plots_dir / filename
        if path.is_file():
            plots["present"].append(filename)
        else:
            plots["missing"].append(filename)
    if len(plots["missing"]) == len(EXPECTED_PLOTS):
        errors.append(f"All expected report plots are missing under: {plots_dir}")
    elif plots["missing"]:
        warnings.append("Missing report plot(s): " + ", ".join(plots["missing"]))


def _inspect_sections(
    html_text: str | None,
    result: dict[str, Any],
    warnings: list[str],
) -> None:
    sections: dict[str, Any] = {
        "expected": list(EXPECTED_SECTIONS),
        "present": [],
        "missing": [],
    }
    result["sections"] = sections
    if html_text is None:
        sections["skipped"] = True
        return
    for section_id in EXPECTED_SECTIONS:
        marker = f'id="{section_id}"'
        if marker in html_text or f"id='{section_id}'" in html_text:
            sections["present"].append(section_id)
        else:
            sections["missing"].append(section_id)
    if sections["missing"]:
        warnings.append("Missing HTML section id(s): " + ", ".join(sections["missing"]))


def _status(errors: list[str], warnings: list[str]) -> str:
    if errors:
        return "failed"
    if warnings:
        return "warning"
    return "ok"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect an existing generated experiment report without regenerating it."
    )
    parser.add_argument(
        "--experiment-dir",
        required=True,
        help="Completed experiment directory containing a report/ subdirectory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the raw JSON inspection result.",
    )
    return parser.parse_args(argv)


def _print_summary(result: dict[str, Any]) -> None:
    print(f"status: {result['status']}")
    print(f"experiment_dir: {result['experiment_dir']}")
    print(f"report_dir: {result['report_dir']}")
    for name, entry in result.get("files", {}).items():
        exists = "present" if entry.get("exists") else "missing"
        print(f"{name}: {exists} ({entry.get('path')})")
    plots = result.get("plots", {})
    if plots:
        print(f"plots_present: {len(plots.get('present', []))}/{len(plots.get('expected', []))}")
    sections = result.get("sections", {})
    if sections:
        print(
            f"sections_present: {len(sections.get('present', []))}/"
            f"{len(sections.get('expected', []))}"
        )
    for warning in result.get("warnings", []):
        print(f"warning: {warning}")
    for error in result.get("errors", []):
        print(f"error: {error}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    result = inspect_report(args.experiment_dir)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_summary(result)
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EXPECTED_PLOTS",
    "EXPECTED_SECTIONS",
    "IMPORTANT_REPORT_DATA_KEYS",
    "inspect_report",
    "main",
]
