"""Compact benchmark-aware history for closed-loop optimization prompts.

The helpers in this module intentionally produce small deterministic plain-text
summaries. They never include full source code, diffs, candidate JSON,
verification JSON, benchmark logs, audit objects, or stack traces.
"""

from __future__ import annotations

import json
from typing import Any


INCLUDED_STATUSES = {
    "accepted_improvement",
    "valid_not_improved",
    "rejected",
    "materialization_failed",
    "verification_failed",
}

FAILED_WITH_CANDIDATE_STATUSES = {
    "materialization_failed",
    "verification_failed",
}

GUIDANCE_BY_STATUS = {
    "accepted_improvement": (
        "This improvement is already included in the current source; build on top "
        "of it and do not re-apply the same edit."
    ),
    "valid_not_improved": (
        "Do not repeat this optimization pattern because it was not faster than "
        "the current best."
    ),
    "rejected": "Avoid this change pattern because it failed correctness or selection gates.",
    "materialization_failed": (
        "When using line_range_edits, copy original text exactly from the numbered "
        "source and keep line ranges precise."
    ),
    "verification_failed": (
        "Avoid changes that break build, solver API, benchmark execution, or "
        "metrics generation."
    ),
}

STATUS_LABELS = {
    "accepted_improvement": "accepted improvement",
    "valid_not_improved": "valid but not improved",
    "rejected": "rejected",
    "materialization_failed": "materialization failed",
    "verification_failed": "verification failed",
}


def should_include_in_closed_loop_history(record: dict[str, Any]) -> bool:
    """Return whether a closed-loop iteration record is useful future context."""

    status = _status_value(record.get("status"))
    if status not in INCLUDED_STATUSES:
        return False

    candidate_summary = _compact_text(record.get("candidate_summary"))
    has_candidate_info = bool(record.get("candidate_run_dir")) or bool(candidate_summary)
    if status in FAILED_WITH_CANDIDATE_STATUSES and not has_candidate_info:
        return False

    return _has_useful_pattern_information(record)


def build_history_guidance(record: dict[str, Any]) -> str | None:
    """Build deterministic guidance for one history record, if included."""

    if not should_include_in_closed_loop_history(record):
        return None
    return GUIDANCE_BY_STATUS.get(_status_value(record.get("status")))


def summarize_closed_loop_record_for_history(record: dict[str, Any]) -> dict[str, Any]:
    """Return a compact structured summary used by the text renderer."""

    status = _status_value(record.get("status"))
    summary = {
        "iteration": record.get("iteration"),
        "status": status,
        "label": STATUS_LABELS.get(status, status.replace("_", " ")),
        "idea": _idea_text(record),
        "result": _result_text(record),
        "reason": _reason_text(record),
        "guidance": build_history_guidance(record),
    }
    if record.get("candidate_expected_effect") is not None:
        summary["expected_effect"] = _compact_text(record.get("candidate_expected_effect"))
    if record.get("candidate_risk_level") is not None:
        summary["risk_level"] = _compact_text(record.get("candidate_risk_level"))
    return summary


def build_closed_loop_history_context(records: list[dict[str, Any]]) -> str | None:
    """Build compact plain-text history for all meaningful previous records."""

    included_records = [record for record in records if should_include_in_closed_loop_history(record)]
    if not included_records:
        return None

    lines = [
        "Closed-loop optimization history:",
        "The current source already includes all accepted improvements listed below.",
        "Use this history to avoid repeating failed or slower optimization patterns.",
        "",
    ]
    for index, record in enumerate(included_records):
        summary = summarize_closed_loop_record_for_history(record)
        iteration = summary.get("iteration")
        iteration_text = iteration if iteration is not None else index + 1
        lines.append(f"Iteration {iteration_text}: {summary['label']}.")
        lines.append(f"Idea: {summary['idea']}.")
        if summary.get("result"):
            lines.append(f"Result: {summary['result']}.")
        if summary.get("reason"):
            lines.append(f"Reason: {summary['reason']}.")
        if summary.get("expected_effect"):
            lines.append(f"Expected effect: {summary['expected_effect']}.")
        if summary.get("risk_level"):
            lines.append(f"Risk level: {summary['risk_level']}.")
        lines.append(f"Guidance: {summary['guidance']}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _status_value(value: Any) -> str:
    if hasattr(value, "value"):
        enum_value = getattr(value, "value")
        return str(enum_value) if enum_value is not None else ""
    return str(value) if value is not None else ""


def _has_useful_pattern_information(record: dict[str, Any]) -> bool:
    status = _status_value(record.get("status"))
    if _compact_text(record.get("candidate_summary")):
        return True
    if _compact_text(record.get("candidate_expected_effect")):
        return True
    if status in {"rejected", "materialization_failed", "verification_failed"}:
        return bool(_reason_text(record))
    if status == "accepted_improvement":
        return record.get("speedup_vs_current_best") is not None or record.get("candidate_run_dir") is not None
    if status == "valid_not_improved":
        return record.get("candidate_run_dir") is not None or record.get("speedup_vs_current_best") is not None
    return False


def _idea_text(record: dict[str, Any]) -> str:
    summary = _compact_text(record.get("candidate_summary"))
    if summary:
        return summary
    expected_effect = _compact_text(record.get("candidate_expected_effect"))
    if expected_effect:
        return f"Candidate expected effect: {expected_effect}"
    return "Optimization candidate pattern from this iteration"


def _result_text(record: dict[str, Any]) -> str | None:
    status = _status_value(record.get("status"))
    speedup = _float_or_none(record.get("speedup_vs_current_best"))
    baseline_speedup = _float_or_none(record.get("speedup_vs_original_baseline"))

    if status == "accepted_improvement":
        if speedup is not None:
            return _speedup_sentence(speedup, "previous best")
        if baseline_speedup is not None:
            return _speedup_sentence(baseline_speedup, "original baseline")
        return "accepted and already included in the current source"

    if status == "valid_not_improved":
        if speedup is not None:
            if speedup < 1.0:
                return f"{speedup:.2f}x speedup vs current best; {_percent(1.0 - speedup)} slower"
            return f"{speedup:.2f}x speedup vs current best; correct but not faster than current best"
        return "correct but not faster than current best"

    if status == "rejected":
        if speedup is not None:
            return f"{speedup:.2f}x speedup vs current best, but selection/correctness gates rejected it"
        return "selection/correctness gates rejected it"

    return None


def _speedup_sentence(speedup: float, reference: str) -> str:
    if speedup >= 1.0:
        return f"{speedup:.2f}x speedup vs {reference}; {_percent(1.0 - (1.0 / speedup))} runtime reduction"
    return f"{speedup:.2f}x speedup vs {reference}; {_percent(1.0 - speedup)} slower"


def _reason_text(record: dict[str, Any]) -> str | None:
    status = _status_value(record.get("status"))
    if status == "rejected":
        reasons = _decision_rejection_reasons(record.get("decision_vs_current_best"))
        if reasons:
            return "; ".join(reasons)
    failure_reason = _compact_text(record.get("failure_reason"))
    if failure_reason:
        return failure_reason
    if status == "rejected":
        return "selection/correctness gates failed"
    return None


def _decision_rejection_reasons(decision: Any) -> list[str]:
    if not isinstance(decision, dict):
        return []
    raw_reasons = decision.get("rejection_reasons")
    if not isinstance(raw_reasons, list):
        return []
    reasons: list[str] = []
    for reason in raw_reasons:
        text = _compact_text(reason)
        if text:
            reasons.append(text)
        if len(reasons) >= 3:
            break
    return reasons


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _percent(value: float) -> str:
    return f"{abs(value) * 100:.1f}%"


def _compact_text(value: Any, max_chars: int = 220) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        text = str(value)
    elif isinstance(value, dict):
        # Candidate summaries may be dicts in older tests/artifacts. Keep only a
        # compact one-line representation and never pretty-print JSON.
        if isinstance(value.get("summary"), str):
            text = value["summary"]
        else:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    else:
        text = str(value)

    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("```"):
            continue
        if line.startswith(("diff --git", "@@", "+++", "---")):
            continue
        if line.startswith(("+", "-")) and len(line) > 1:
            continue
        cleaned_lines.append(line)
        if len(" ".join(cleaned_lines)) >= max_chars:
            break

    compact = " ".join(cleaned_lines)
    compact = " ".join(compact.split())
    if not compact:
        return None
    if len(compact) > max_chars:
        return compact[: max_chars - 1].rstrip() + "…"
    return compact