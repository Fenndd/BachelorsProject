from __future__ import annotations

from orchestrator.experiments.closed_loop_history import (
    build_closed_loop_history_context,
    build_history_guidance,
    should_include_in_closed_loop_history,
)


def _record(status: str, **overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "iteration": 1,
        "status": status,
        "candidate_run_dir": "results/runs/candidate_1",
        "candidate_summary": "Use Eigen noalias for pose.R assignment",
        "candidate_expected_effect": "runtime reduction",
        "candidate_risk_level": "low",
        "speedup_vs_current_best": 1.03,
        "speedup_vs_original_baseline": 1.03,
        "decision_vs_current_best": {
            "status": status,
            "rejection_reasons": [],
        },
        "failure_reason": None,
    }
    record.update(overrides)
    return record


def test_inclusion_rules_for_required_statuses() -> None:
    assert should_include_in_closed_loop_history(_record("accepted_improvement"))
    assert should_include_in_closed_loop_history(_record("valid_not_improved"))
    assert should_include_in_closed_loop_history(_record("rejected"))
    assert should_include_in_closed_loop_history(_record("materialization_failed"))
    assert should_include_in_closed_loop_history(_record("verification_failed"))

    assert not should_include_in_closed_loop_history(_record("no_op"))
    assert not should_include_in_closed_loop_history(
        _record(
            "generation_failed",
            candidate_run_dir=None,
            candidate_summary=None,
            failure_reason="LLM API failed",
        )
    )
    assert not should_include_in_closed_loop_history(
        _record("generation_failed", candidate_summary="Candidate existed but parse failed")
    )


def test_failed_statuses_require_candidate_information() -> None:
    assert not should_include_in_closed_loop_history(
        _record("materialization_failed", candidate_run_dir=None, candidate_summary=None)
    )
    assert should_include_in_closed_loop_history(
        _record("materialization_failed", candidate_run_dir=None, candidate_summary="Replace pose block")
    )
    assert not should_include_in_closed_loop_history(
        _record("verification_failed", candidate_run_dir=None, candidate_summary=None)
    )


def test_valid_not_improved_requires_useful_pattern_information() -> None:
    assert should_include_in_closed_loop_history(
        _record(
            "valid_not_improved",
            candidate_run_dir=None,
            candidate_summary="Try cached arithmetic",
            candidate_expected_effect=None,
            speedup_vs_current_best=None,
        )
    )
    assert should_include_in_closed_loop_history(
        _record(
            "valid_not_improved",
            candidate_run_dir=None,
            candidate_summary=None,
            candidate_expected_effect=None,
            speedup_vs_current_best=0.99,
        )
    )
    assert not should_include_in_closed_loop_history(
        _record(
            "valid_not_improved",
            candidate_run_dir=None,
            candidate_summary=None,
            candidate_expected_effect=None,
            speedup_vs_current_best=None,
        )
    )
    assert not should_include_in_closed_loop_history(_record("no_op"))
    assert not should_include_in_closed_loop_history(
        _record("generation_failed", candidate_run_dir=None, candidate_summary=None)
    )


def test_history_text_contains_compact_benchmark_aware_entries() -> None:
    records = [
        _record("accepted_improvement", iteration=1),
        _record(
            "valid_not_improved",
            iteration=2,
            candidate_summary="Cache lambda1*x[0] as an Eigen vector",
            speedup_vs_current_best=0.94,
        ),
        _record(
            "materialization_failed",
            iteration=3,
            candidate_summary="Replace pose construction block",
            failure_reason="original text did not match requested line range",
        ),
        _record("no_op", iteration=4, candidate_summary="No useful change"),
    ]

    context = build_closed_loop_history_context(records)

    assert context is not None
    assert "Closed-loop optimization history:" in context
    assert "Iteration 1: accepted improvement." in context
    assert "Use Eigen noalias for pose.R assignment" in context
    assert "1.03x speedup vs previous best" in context
    assert "runtime reduction" in context
    assert "already included in the current source" in context
    assert "Iteration 2: valid but not improved." in context
    assert "0.94x speedup vs current best" in context
    assert "6.4% slower" in context
    assert "Do not repeat this optimization pattern" in context
    assert "Iteration 3: materialization failed." in context
    assert "original text did not match requested line range" in context
    assert "copy original text exactly" in context
    assert "Iteration 4" not in context


def test_valid_not_improved_uses_runtime_slowdown_percent_from_speedup() -> None:
    context = build_closed_loop_history_context(
        [
            _record("valid_not_improved", iteration=1, speedup_vs_current_best=0.5),
            _record("valid_not_improved", iteration=2, speedup_vs_current_best=0.8),
            _record("valid_not_improved", iteration=3, speedup_vs_current_best=0.95),
        ]
    )

    assert context is not None
    assert "100.0% slower" in context
    assert "25.0% slower" in context
    assert "5.3% slower" in context


def test_valid_not_improved_below_runtime_threshold_has_specific_history() -> None:
    context = build_closed_loop_history_context(
        [
            _record(
                "valid_not_improved",
                speedup_vs_current_best=1.001,
                decision_vs_current_best={
                    "status": "valid_not_improved",
                    "rejection_reasons": [],
                    "non_acceptance_reasons": ["runtime_improvement_below_minimum_threshold"],
                    "thresholds": {"min_runtime_reduction_percent": 0.5},
                    "comparison": {
                        "speedup": 1.001,
                        "runtime_reduction_percent": 0.1,
                        "candidate_runtime_lower": True,
                    },
                },
            )
        ]
    )

    assert context is not None
    assert "0.1% faster than current best, below the 0.5% acceptance threshold" in context
    assert "too small to accept as reliable" in context


def test_valid_not_improved_below_runtime_threshold_legacy_rejection_reason_fallback() -> None:
    context = build_closed_loop_history_context(
        [
            _record(
                "valid_not_improved",
                speedup_vs_current_best=1.001,
                decision_vs_current_best={
                    "status": "valid_not_improved",
                    "rejection_reasons": ["runtime_improvement_below_minimum_threshold"],
                    "thresholds": {"min_runtime_reduction_percent": 0.5},
                    "comparison": {
                        "speedup": 1.001,
                        "runtime_reduction_percent": 0.1,
                        "candidate_runtime_lower": True,
                    },
                },
            )
        ]
    )

    assert context is not None
    assert "0.1% faster than current best, below the 0.5% acceptance threshold" in context


def test_valid_not_improved_without_threshold_reason_uses_normal_guidance() -> None:
    context = build_closed_loop_history_context(
        [
            _record(
                "valid_not_improved",
                speedup_vs_current_best=1.0,
                decision_vs_current_best={
                    "status": "valid_not_improved",
                    "rejection_reasons": [],
                    "non_acceptance_reasons": [],
                    "thresholds": {"min_runtime_reduction_percent": 0.5},
                    "comparison": {
                        "speedup": 1.0,
                        "runtime_reduction_percent": 0.0,
                        "candidate_runtime_lower": False,
                    },
                },
            )
        ]
    )

    assert context is not None
    assert "correct but not faster than current best" in context
    assert "Do not repeat this optimization pattern" in context


def test_accepted_result_text_uses_runtime_slowdown_percent_from_speedup() -> None:
    context = build_closed_loop_history_context(
        [_record("accepted_improvement", speedup_vs_current_best=0.5)]
    )

    assert context is not None
    assert "0.50x speedup vs previous best; 100.0% slower" in context


def test_history_text_uses_rejection_reasons_and_verification_guidance() -> None:
    context = build_closed_loop_history_context(
        [
            _record(
                "rejected",
                iteration=1,
                decision_vs_current_best={"rejection_reasons": ["audit failed", "correctness gate failed"]},
            ),
            _record(
                "verification_failed",
                iteration=2,
                candidate_summary="Change solver API return shape",
                failure_reason="benchmark metrics missing",
            ),
        ]
    )

    assert context is not None
    assert "audit failed; correctness gate failed" in context
    assert "Avoid this change pattern because it failed correctness or selection gates" in context
    assert "benchmark metrics missing" in context
    assert "Avoid changes that break build, solver API, benchmark execution, or metrics generation" in context


def test_materialization_failed_ambiguous_gets_repeated_code_guidance() -> None:
    guidance = build_history_guidance(
        _record(
            "materialization_failed",
            failure_reason="exact-search fallback is ambiguous because original text occurs multiple times",
        )
    )

    assert guidance is not None
    assert "same original text occurred in multiple locations" in guidance
    assert "include enough surrounding original lines" in guidance


def test_materialization_failed_line_range_mismatch_gets_exact_line_guidance() -> None:
    guidance = build_history_guidance(
        _record(
            "materialization_failed",
            failure_reason="original text did not match requested line range",
        )
    )

    assert guidance is not None
    assert "original did not match the source at start_line..end_line" in guidance
    assert "line numbers shown before the '|' separator" in guidance


def test_materialization_failed_fallback_disabled_gets_precise_range_guidance() -> None:
    guidance = build_history_guidance(
        _record(
            "materialization_failed",
            failure_reason="line range did not match and exact-search fallback is disabled",
        )
    )

    assert guidance is not None
    assert "fallback was disabled" in guidance
    assert "precise line range and exact original text" in guidance


def test_generic_materialization_failed_keeps_generic_guidance() -> None:
    guidance = build_history_guidance(
        _record("materialization_failed", failure_reason="target file missing")
    )

    assert guidance is not None
    assert "copy original text exactly" in guidance


def test_history_text_does_not_include_full_diff_or_json_dump() -> None:
    context = build_closed_loop_history_context(
        [
            _record(
                "accepted_improvement",
                candidate_summary=(
                    "Improve arithmetic\n"
                    "```diff\n"
                    "diff --git a/file b/file\n"
                    "@@ -1,2 +1,2 @@\n"
                    "-old line\n"
                    "+new line\n"
                    "```"
                ),
            )
        ]
    )

    assert context is not None
    assert "Improve arithmetic" in context
    assert "diff --git" not in context
    assert "@@" not in context
    assert "-old line" not in context
    assert "+new line" not in context
    assert "candidate.json" not in context


def test_full_meaningful_history_has_no_sliding_window() -> None:
    records = [
        _record("valid_not_improved", iteration=index, candidate_summary=f"idea {index}")
        for index in range(1, 6)
    ]

    context = build_closed_loop_history_context(records)

    assert context is not None
    for index in range(1, 6):
        assert f"Iteration {index}:" in context
        assert f"idea {index}" in context


def test_guidance_is_none_for_excluded_record() -> None:
    assert build_history_guidance(_record("no_op")) is None