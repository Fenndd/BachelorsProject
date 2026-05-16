"""Normalized outcome reasons for closed-loop experiment iterations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CATEGORY_GENERATION = "generation"
CATEGORY_NO_OP = "no_op"
CATEGORY_MATERIALIZATION = "materialization"
CATEGORY_VERIFICATION = "verification"
CATEGORY_DECISION = "decision"
CATEGORY_UNKNOWN = "unknown"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"

CODE_GENERATION_FAILED = "generation_failed"
CODE_LLM_REQUEST_FAILED = "llm_request_failed"
CODE_LLM_RESPONSE_PARSE_FAILED = "llm_response_parse_failed"
CODE_CANDIDATE_JSON_INVALID = "candidate_json_invalid"
CODE_CANDIDATE_ARTIFACTS_MISSING = "candidate_artifacts_missing"
CODE_CANDIDATE_RUN_DIR_PARSE_FAILED = "candidate_run_dir_parse_failed"
CODE_NO_OP_CANDIDATE = "no_op_candidate"
CODE_EMPTY_EDIT_PAYLOAD = "empty_edit_payload"
CODE_MATERIALIZATION_FAILED = "materialization_failed"
CODE_SCOPE_VIOLATION = "scope_violation"
CODE_DIFF_APPLY_FAILED = "diff_apply_failed"
CODE_LINE_RANGE_MISMATCH = "line_range_mismatch"
CODE_LINE_RANGE_FALLBACK_AMBIGUOUS = "line_range_fallback_ambiguous"
CODE_TARGET_FILE_MISSING = "target_file_missing"
CODE_NO_FILES_CHANGED = "no_files_changed"
CODE_VERIFICATION_FAILED = "verification_failed"
CODE_CONFIGURE_FAILED = "configure_failed"
CODE_BUILD_FAILED = "build_failed"
CODE_SMOKE_TEST_FAILED = "smoke_test_failed"
CODE_ADAPTER_VALIDATION_FAILED = "adapter_validation_failed"
CODE_BENCHMARK_EXECUTION_FAILED = "benchmark_execution_failed"
CODE_BENCHMARK_PARSE_FAILED = "benchmark_parse_failed"
CODE_BENCHMARK_CORRECTNESS_FAILED = "benchmark_correctness_failed"
CODE_METRICS_MISSING = "metrics_missing"
CODE_ACCEPTED_IMPROVEMENT = "accepted_improvement"
CODE_VALID_NOT_IMPROVED = "valid_not_improved"
CODE_REJECTED_CORRECTNESS = "rejected_correctness"
CODE_REJECTED_NOT_COMPARABLE = "rejected_not_comparable"
CODE_REJECTED_NO_SPEEDUP = "rejected_no_speedup"
CODE_REJECTED_BENCHMARK_AUDIT_FAILED = "rejected_benchmark_audit_failed"
CODE_DECISION_ARTIFACT_MISSING = "decision_artifact_missing"
CODE_UNKNOWN_REASON = "unknown_reason"


@dataclass(frozen=True)
class OutcomeReason:
    category: str
    code: str
    severity: str
    message: str
    source_artifact: str | None = None


def outcome_reason_to_dict(reason: OutcomeReason | None) -> dict[str, Any] | None:
    return None if reason is None else asdict(reason)


def build_outcome_reason(
    *,
    status: str,
    record: dict[str, Any] | None = None,
    candidate_run_dir: str | Path | None = None,
    candidate: dict[str, Any] | None = None,
    generation: dict[str, Any] | None = None,
    materialization: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    decision_vs_current_best: dict[str, Any] | None = None,
    source_artifacts: dict[str, str | None] | None = None,
) -> OutcomeReason:
    """Build a stable normalized reason from existing iteration artifacts."""

    record = record or {}
    source_artifacts = source_artifacts or {}
    if status == "accepted_improvement":
        return OutcomeReason(
            CATEGORY_DECISION,
            CODE_ACCEPTED_IMPROVEMENT,
            SEVERITY_INFO,
            "Candidate improved over current best and was promoted into experiment-local current_best_source.",
            _source(source_artifacts, "decision_vs_current_best"),
        )
    if status == "valid_not_improved":
        return OutcomeReason(
            CATEGORY_DECISION,
            CODE_VALID_NOT_IMPROVED,
            SEVERITY_INFO,
            "Candidate preserved correctness but did not improve over current best.",
            _source(source_artifacts, "decision_vs_current_best"),
        )
    if status == "rejected":
        return _decision_reason(decision_vs_current_best, source_artifacts)
    if status == "no_op":
        return _no_op_reason(candidate, record, source_artifacts)
    if status == "generation_failed":
        return _generation_reason(generation, record, source_artifacts, candidate_run_dir)
    if status == "materialization_failed":
        return _materialization_reason(materialization, record, source_artifacts)
    if status == "verification_failed":
        return _verification_reason(verification, record, source_artifacts)
    return OutcomeReason(
        CATEGORY_UNKNOWN,
        CODE_UNKNOWN_REASON,
        SEVERITY_WARNING,
        "Iteration outcome reason could not be classified.",
        None,
    )


def _generation_reason(
    generation: dict[str, Any] | None,
    record: dict[str, Any],
    source_artifacts: dict[str, str | None],
    candidate_run_dir: str | Path | None,
) -> OutcomeReason:
    failed_step = _lower_text(_first_value((generation or {}).get("failed_step"), record.get("failed_step")))
    message = "Candidate generation failed."
    code = CODE_GENERATION_FAILED
    if failed_step == "llm_request":
        code = CODE_LLM_REQUEST_FAILED
        message = "LLM request failed during candidate generation."
    elif failed_step == "parse_response":
        code = CODE_LLM_RESPONSE_PARSE_FAILED
        message = "LLM response could not be parsed as a valid candidate."
    elif failed_step == "parse_candidate_run_dir":
        code = CODE_CANDIDATE_RUN_DIR_PARSE_FAILED
        message = "Candidate run directory could not be parsed from generation output."
    elif failed_step in {"read_candidate_status", "read_candidate_run"}:
        code = CODE_CANDIDATE_ARTIFACTS_MISSING
        message = "Candidate generation artifacts were missing or unreadable."
    elif failed_step in {"read_candidate_json", "candidate_json_invalid"}:
        code = CODE_CANDIDATE_JSON_INVALID
        message = "Generated candidate JSON was invalid."
    elif "save_artifacts" in failed_step:
        code = CODE_CANDIDATE_ARTIFACTS_MISSING
        message = "Candidate generation artifacts could not be saved."
    return OutcomeReason(
        CATEGORY_GENERATION,
        code,
        SEVERITY_ERROR,
        message,
        _source(source_artifacts, "status") if candidate_run_dir is not None else None,
    )


def _no_op_reason(
    candidate: dict[str, Any] | None,
    record: dict[str, Any],
    source_artifacts: dict[str, str | None],
) -> OutcomeReason:
    candidate = candidate or {}
    expected_effect = _first_value(candidate.get("expected_effect"), record.get("candidate_expected_effect"))
    has_empty_payload = _candidate_edit_payload_empty(candidate)
    code = CODE_EMPTY_EDIT_PAYLOAD if has_empty_payload else CODE_NO_OP_CANDIDATE
    message = "Candidate declared no expected effect and did not include edits." if expected_effect == "none" and has_empty_payload else "Candidate was classified as a no-op."
    return OutcomeReason(
        CATEGORY_NO_OP,
        code,
        SEVERITY_INFO,
        message,
        _source(source_artifacts, "candidate"),
    )


def _materialization_reason(
    materialization: dict[str, Any] | None,
    record: dict[str, Any],
    source_artifacts: dict[str, str | None],
) -> OutcomeReason:
    materialization = materialization or {}
    failed_step = _lower_text(_first_value(materialization.get("failed_step"), record.get("failed_step")))
    error_text = _lower_text(_first_value(materialization.get("error_message"), record.get("failure_reason")))
    edit_failure = _line_range_failure_reason(materialization)
    code = CODE_MATERIALIZATION_FAILED
    message = "Candidate materialization failed."
    if "scope" in failed_step or "scope" in error_text or "allowed" in error_text:
        code = CODE_SCOPE_VIOLATION
        message = "Candidate attempted to modify files outside the allowed scope."
    elif edit_failure == "fallback_no_match" or "fallback_no_match" in error_text:
        code = CODE_LINE_RANGE_MISMATCH
        message = "Line-range edit original text did not match the target source."
    elif edit_failure == "fallback_ambiguous" or "fallback_ambiguous" in error_text:
        code = CODE_LINE_RANGE_FALLBACK_AMBIGUOUS
        message = "Line-range fallback matched multiple locations and was ambiguous."
    elif edit_failure == "target_file_missing" or "target_file_missing" in error_text:
        code = CODE_TARGET_FILE_MISSING
        message = "Materialization target file was missing."
    elif edit_failure in {"invalid_line_range", "fallback_not_allowed"}:
        code = CODE_LINE_RANGE_MISMATCH
        message = "Line-range edit could not be matched to the target source."
    elif "no target file hash changed" in error_text or "no_files_changed" in error_text:
        code = CODE_NO_FILES_CHANGED
        message = "Candidate applied without changing any target file."
    elif "git_apply" in failed_step or "git apply" in error_text:
        code = CODE_DIFF_APPLY_FAILED
        message = "Candidate diff could not be applied."
    return OutcomeReason(
        CATEGORY_MATERIALIZATION,
        code,
        SEVERITY_ERROR,
        message,
        _source(source_artifacts, "materialization"),
    )


def _verification_reason(
    verification: dict[str, Any] | None,
    record: dict[str, Any],
    source_artifacts: dict[str, str | None],
) -> OutcomeReason:
    verification = verification or {}
    failed_step = _lower_text(_first_value(verification.get("failed_step"), record.get("failed_step")))
    code = CODE_VERIFICATION_FAILED
    message = "Candidate verification failed."
    if failed_step == "configure_cmake":
        code = CODE_CONFIGURE_FAILED
        message = "Candidate failed CMake configuration."
    elif failed_step.startswith("build_"):
        code = CODE_BUILD_FAILED
        message = "Candidate failed to build."
    elif failed_step == "run_baseline_smoke_test":
        code = CODE_SMOKE_TEST_FAILED
        message = "Candidate failed the baseline smoke test."
    elif "adapter_validator" in failed_step or "adapter_validation" in failed_step:
        code = CODE_ADAPTER_VALIDATION_FAILED
        message = "Candidate failed adapter validation."
    elif failed_step.startswith("run_") and "benchmark" in failed_step:
        code = CODE_BENCHMARK_EXECUTION_FAILED
        message = "Candidate benchmark execution failed."
    elif "parse" in failed_step and "benchmark" in failed_step:
        code = CODE_BENCHMARK_PARSE_FAILED
        message = "Candidate benchmark output could not be parsed."
    elif failed_step == "benchmark_correctness_check":
        code = CODE_BENCHMARK_CORRECTNESS_FAILED
        message = "Candidate failed benchmark correctness check."
    elif verification and _benchmark_metrics_missing(verification):
        code = CODE_METRICS_MISSING
        message = "Candidate verification metrics were missing."
    return OutcomeReason(
        CATEGORY_VERIFICATION,
        code,
        SEVERITY_ERROR,
        message,
        _source(source_artifacts, "verification"),
    )


def _decision_reason(
    decision: dict[str, Any] | None,
    source_artifacts: dict[str, str | None],
) -> OutcomeReason:
    if not isinstance(decision, dict):
        return OutcomeReason(
            CATEGORY_DECISION,
            CODE_DECISION_ARTIFACT_MISSING,
            SEVERITY_ERROR,
            "Decision artifact was missing or unreadable.",
            _source(source_artifacts, "decision_vs_current_best"),
        )
    reasons = _reason_list(decision.get("rejection_reasons")) + _reason_list(decision.get("non_acceptance_reasons"))
    raw_audit = decision.get("audit")
    audit: dict[str, Any] = raw_audit if isinstance(raw_audit, dict) else {}
    code = CODE_REJECTED_NOT_COMPARABLE
    message = "Candidate was rejected by the current-best decision gate."
    if any(_is_correctness_decision_reason(reason) for reason in reasons):
        code = CODE_REJECTED_CORRECTNESS
        message = "Candidate was rejected because correctness or accuracy thresholds were not preserved."
    elif audit.get("comparable") is False or any(
        reason == "audit_not_comparable" or reason.startswith("audit_failed_check:")
        for reason in reasons
    ):
        code = CODE_REJECTED_BENCHMARK_AUDIT_FAILED
        message = "Candidate was rejected because benchmark artifact audit failed."
    elif any(reason == "runtime_comparison_unavailable" for reason in reasons):
        code = CODE_REJECTED_NOT_COMPARABLE
        message = "Candidate was rejected because benchmark artifacts were not comparable."
    elif any("runtime" in reason or "speedup" in reason for reason in reasons):
        code = CODE_REJECTED_NO_SPEEDUP
        message = "Candidate was rejected because runtime did not improve enough."
    elif any("not_comparable" in reason or "comparable" in reason for reason in reasons):
        code = CODE_REJECTED_NOT_COMPARABLE
        message = "Candidate was rejected because benchmark artifacts were not comparable."
    return OutcomeReason(
        CATEGORY_DECISION,
        code,
        SEVERITY_ERROR,
        message,
        _source(source_artifacts, "decision_vs_current_best"),
    )


def _is_correctness_decision_reason(reason: str) -> bool:
    return (
        "correctness" in reason
        or reason.startswith("candidate_success_rate_below_minimum")
        or reason.startswith("candidate_mean_reprojection_error_exceeds_limit")
        or reason.startswith("candidate_max_reprojection_error_exceeds_limit")
    )


def _line_range_failure_reason(materialization: dict[str, Any]) -> str | None:
    results = materialization.get("line_range_edit_results")
    if not isinstance(results, list):
        return None
    ignored = {"previous_edit_failed", "not_attempted"}
    for result in results:
        if not isinstance(result, dict):
            continue
        reason = result.get("failure_reason")
        if isinstance(reason, str) and reason and reason not in ignored:
            return reason
    return None


def _candidate_edit_payload_empty(candidate: dict[str, Any]) -> bool:
    candidate_type = candidate.get("candidate_type", "unified_diff")
    if candidate_type == "line_range_edits":
        edits = candidate.get("edits")
        return isinstance(edits, list) and len(edits) == 0
    diff_text = candidate.get("unified_diff")
    return not isinstance(diff_text, str) or not diff_text.strip()


def _benchmark_metrics_missing(verification: dict[str, Any]) -> bool:
    benchmark = verification.get("benchmark")
    if not isinstance(benchmark, dict):
        return True
    return benchmark.get("parsed_runtime_ns_per_case_median") is None or benchmark.get("parsed_correctness_passed") is None


def _reason_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


def _source(source_artifacts: dict[str, str | None], key: str) -> str | None:
    value = source_artifacts.get(key)
    return value if isinstance(value, str) and value else None


def _lower_text(value: Any) -> str:
    return value.lower() if isinstance(value, str) else ""


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


__all__ = [
    "OutcomeReason",
    "build_outcome_reason",
    "outcome_reason_to_dict",
]
