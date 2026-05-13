from __future__ import annotations

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
