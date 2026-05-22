from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from orchestrator.experiments.outcome_reason import build_outcome_reason


def test_generation_parse_response_maps_to_llm_response_parse_failed() -> None:
    reason = build_outcome_reason(
        status="generation_failed",
        generation={"failed_step": "parse_response"},
    )

    assert reason.category == "generation"
    assert reason.code == "llm_response_parse_failed"
    assert reason.severity == "error"


def test_materialization_fallback_no_match_maps_to_line_range_mismatch() -> None:
    reason = build_outcome_reason(
        status="materialization_failed",
        materialization={
            "failed_step": "line_range_apply",
            "line_range_edit_results": [
                {"status": "failed", "failure_reason": "fallback_no_match"}
            ],
        },
    )

    assert reason.category == "materialization"
    assert reason.code == "line_range_mismatch"


def test_materialization_skips_previous_edit_failed_for_fallback_ambiguous() -> None:
    reason = build_outcome_reason(
        status="materialization_failed",
        materialization={
            "failed_step": "line_range_apply",
            "line_range_edit_results": [
                {"status": "failed", "failure_reason": "previous_edit_failed"},
                {"status": "failed", "failure_reason": "fallback_ambiguous"},
            ],
        },
    )

    assert reason.category == "materialization"
    assert reason.code == "line_range_fallback_ambiguous"


def test_materialization_skips_previous_edit_failed_for_fallback_no_match() -> None:
    reason = build_outcome_reason(
        status="materialization_failed",
        materialization={
            "failed_step": "line_range_apply",
            "line_range_edit_results": [
                {"status": "failed", "failure_reason": "previous_edit_failed"},
                {"status": "failed", "failure_reason": "fallback_no_match"},
            ],
        },
    )

    assert reason.category == "materialization"
    assert reason.code == "line_range_mismatch"


def test_verification_benchmark_correctness_maps_to_benchmark_correctness_failed() -> None:
    reason = build_outcome_reason(
        status="verification_failed",
        verification={"failed_step": "benchmark_correctness_check"},
    )

    assert reason.category == "verification"
    assert reason.code == "benchmark_correctness_failed"


def test_accepted_improvement_reason_is_info_decision() -> None:
    reason = build_outcome_reason(status="accepted_improvement")

    assert reason.category == "decision"
    assert reason.code == "accepted_improvement"
    assert reason.severity == "info"


def test_valid_not_improved_reason_is_info_decision() -> None:
    reason = build_outcome_reason(status="valid_not_improved")

    assert reason.category == "decision"
    assert reason.code == "valid_not_improved"
    assert reason.severity == "info"


def test_decision_success_rate_rejection_maps_to_correctness() -> None:
    reason = build_outcome_reason(
        status="rejected",
        decision_vs_current_best={
            "rejection_reasons": [
                "candidate_success_rate_below_minimum(candidate=0.9, minimum=1.0)"
            ]
        },
    )

    assert reason.category == "decision"
    assert reason.code == "rejected_correctness"
    assert reason.severity == "error"


def test_decision_mean_reprojection_rejection_maps_to_correctness() -> None:
    reason = build_outcome_reason(
        status="rejected",
        decision_vs_current_best={
            "rejection_reasons": [
                "candidate_mean_reprojection_error_exceeds_limit(candidate=2, maximum=1)"
            ]
        },
    )

    assert reason.code == "rejected_correctness"


def test_decision_max_reprojection_rejection_maps_to_correctness() -> None:
    reason = build_outcome_reason(
        status="rejected",
        decision_vs_current_best={
            "rejection_reasons": [
                "candidate_max_reprojection_error_exceeds_limit(candidate=2, maximum=1)"
            ]
        },
    )

    assert reason.code == "rejected_correctness"


def test_decision_runtime_threshold_rejection_maps_to_no_speedup() -> None:
    reason = build_outcome_reason(
        status="rejected",
        decision_vs_current_best={
            "rejection_reasons": ["runtime_improvement_below_minimum_threshold"]
        },
    )

    assert reason.category == "decision"
    assert reason.code == "rejected_no_speedup"


def test_valid_not_improved_status_keeps_valid_not_improved_reason() -> None:
    reason = build_outcome_reason(
        status="valid_not_improved",
        decision_vs_current_best={
            "non_acceptance_reasons": ["runtime_improvement_below_minimum_threshold"]
        },
    )

    assert reason.code == "valid_not_improved"
    assert reason.severity == "info"


def test_decision_runtime_unavailable_maps_to_not_comparable() -> None:
    reason = build_outcome_reason(
        status="rejected",
        decision_vs_current_best={"rejection_reasons": ["runtime_comparison_unavailable"]},
    )

    assert reason.code == "rejected_not_comparable"


def test_decision_audit_failure_maps_to_benchmark_audit_failed() -> None:
    for rejection_reason in ("audit_not_comparable", "audit_failed_check:build_type"):
        reason = build_outcome_reason(
            status="rejected",
            decision_vs_current_best={"rejection_reasons": [rejection_reason]},
        )

        assert reason.category == "decision"
        assert reason.code == "rejected_benchmark_audit_failed"
