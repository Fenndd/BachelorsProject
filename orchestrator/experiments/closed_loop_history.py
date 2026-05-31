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

GENERIC_MATERIALIZATION_GUIDANCE = GUIDANCE_BY_STATUS["materialization_failed"]
AMBIGUOUS_MATERIALIZATION_GUIDANCE = (
    "Previous candidate failed because the same original text occurred in multiple locations. "
    "For repeated code blocks, use the exact intended line range and include enough "
    "surrounding original lines to make the edit unambiguous."
)
LINE_RANGE_MISMATCH_GUIDANCE = (
    "Previous candidate failed because original did not match the source at start_line..end_line. "
    "Use the line numbers shown before the '|' separator and copy original text exactly "
    "from those selected lines."
)
FALLBACK_DISABLED_GUIDANCE = (
    "Previous candidate failed because exact line-range matching failed and fallback was disabled. "
    "Use a precise line range and exact original text."
)
LEADING_WHITESPACE_GUIDANCE = (
    "Previous candidate used different leading indentation than the numbered source. "
    "Copy original indentation from the selected source lines."
)
FALLBACK_NO_MATCH_GUIDANCE = (
    "Previous candidate failed because original text was not found exactly. "
    "Copy original text from the selected numbered source lines."
)
INVALID_LINE_RANGE_GUIDANCE = (
    "Previous candidate used a line range outside the file. Use the integer labels "
    "shown before the '|' separator in the numbered source."
)
INVALID_LINE_RANGE_FALLBACK_GUIDANCE = (
    "Previous candidate relied on exact-search fallback because its line range was outside the file. "
    "Use the exact line labels from the numbered source."
)
BELOW_THRESHOLD_GUIDANCE = (
    "This improvement was too small to accept as reliable; avoid repeating the same "
    "pattern unless combined with a clearer optimization."
)

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
    status = _status_value(record.get("status"))
    if status == "materialization_failed":
        return _materialization_failure_guidance(record)
    if status == "valid_not_improved" and _is_runtime_improvement_below_threshold(record):
        return _append_invalid_line_range_fallback_guidance(record, BELOW_THRESHOLD_GUIDANCE)
    guidance = GUIDANCE_BY_STATUS.get(status)
    if status in {"accepted_improvement", "valid_not_improved"}:
        return _append_invalid_line_range_fallback_guidance(record, guidance)
    return guidance


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
        if _is_runtime_improvement_below_threshold(record):
            below_threshold_result = _below_threshold_result_text(record)
            if below_threshold_result is not None:
                return below_threshold_result
        if speedup is not None:
            if speedup < 1.0:
                return f"{speedup:.2f}x speedup vs current best; {_slower_percent_from_speedup(speedup)} slower"
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
    return f"{speedup:.2f}x speedup vs {reference}; {_slower_percent_from_speedup(speedup)} slower"


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


def _decision_non_acceptance_reasons(decision: Any) -> list[str]:
    if not isinstance(decision, dict):
        return []
    raw_reasons = decision.get("non_acceptance_reasons")
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


def _materialization_failure_guidance(record: dict[str, Any]) -> str:
    match_summary_text = _compact_text(record.get("materialization_match_summary"), max_chars=500)
    if match_summary_text and '"invalid_line_range_fallback_used":true' in match_summary_text.lower():
        return INVALID_LINE_RANGE_FALLBACK_GUIDANCE

    text = " ".join(
        value
        for value in [
            _compact_text(record.get("failure_reason"), max_chars=500),
            _compact_text(record.get("materialization_diagnostics"), max_chars=500),
            _compact_text(record.get("materialization"), max_chars=500),
        ]
        if value
    ).lower()
    if "invalid_line_range_exact_search_fallback" in text:
        return INVALID_LINE_RANGE_FALLBACK_GUIDANCE
    if any(token in text for token in ["line_range_leading_whitespace_mismatch", "line_range_surrounding_whitespace_mismatch"]):
        return LEADING_WHITESPACE_GUIDANCE
    if "fallback_no_match" in text or "not found by exact-search fallback" in text:
        return FALLBACK_NO_MATCH_GUIDANCE
    if "invalid_line_range" in text or "line range is outside" in text or "line range outside" in text:
        return INVALID_LINE_RANGE_GUIDANCE
    if any(token in text for token in ["ambiguous", "multiple matches", "occurs multiple", "repeated text"]):
        return AMBIGUOUS_MATERIALIZATION_GUIDANCE
    if "fallback" in text and "disabled" in text:
        return FALLBACK_DISABLED_GUIDANCE
    if any(
        token in text
        for token in [
            "line range mismatch",
            "line_range_mismatch",
            "original text did not match",
            "original did not match",
            "line range did not match",
            "did not match line range",
        ]
    ):
        return LINE_RANGE_MISMATCH_GUIDANCE
    return GENERIC_MATERIALIZATION_GUIDANCE


def _used_invalid_line_range_fallback(record: dict[str, Any]) -> bool:
    match_summary = record.get("materialization_match_summary")
    return isinstance(match_summary, dict) and match_summary.get("invalid_line_range_fallback_used") is True


def _append_invalid_line_range_fallback_guidance(
    record: dict[str, Any],
    guidance: str | None,
) -> str | None:
    if not _used_invalid_line_range_fallback(record):
        return guidance
    if not guidance:
        return INVALID_LINE_RANGE_FALLBACK_GUIDANCE
    return f"{guidance} {INVALID_LINE_RANGE_FALLBACK_GUIDANCE}"


def _is_runtime_improvement_below_threshold(record: dict[str, Any]) -> bool:
    decision = record.get("decision_vs_current_best")
    if "runtime_improvement_below_minimum_threshold" in _decision_non_acceptance_reasons(decision):
        return True
    return "runtime_improvement_below_minimum_threshold" in _decision_rejection_reasons(decision)


def _below_threshold_result_text(record: dict[str, Any]) -> str | None:
    decision = record.get("decision_vs_current_best")
    if not isinstance(decision, dict):
        return None
    comparison = decision.get("comparison")
    if not isinstance(comparison, dict):
        return None
    runtime_reduction = _float_or_none(comparison.get("runtime_reduction_percent"))
    if runtime_reduction is None:
        return None
    threshold = None
    thresholds = decision.get("thresholds")
    if isinstance(thresholds, dict):
        threshold = _float_or_none(thresholds.get("min_runtime_reduction_percent"))
    if threshold is None:
        threshold = 1.0
    return (
        f"{runtime_reduction:.1f}% faster than current best, below the "
        f"{threshold:.1f}% acceptance threshold"
    )


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _percent(value: float) -> str:
    return f"{abs(value) * 100:.1f}%"


def _slower_percent_from_speedup(speedup: float) -> str:
    return _percent((1.0 / speedup) - 1.0)


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
