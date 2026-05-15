from __future__ import annotations

import json
from pathlib import Path

from orchestrator.experiments.closed_loop_state import IterationStatus
from orchestrator.reporting import (
    ReportArtifactMap,
    ReportIterationSummary,
    ReportReasonSummaryItem,
    default_status_counts,
    make_empty_report_data,
    to_report_dict,
    write_report_data,
)


TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


def test_make_empty_report_data_uses_current_report_schema() -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)

    assert report_data.schema_version == "report.v2"
    assert report_data.report_metadata.report_profile == "single_experiment"


def test_default_status_counts_includes_every_closed_loop_status() -> None:
    counts = default_status_counts()

    assert counts == {status.value: 0 for status in IterationStatus}


def test_write_report_data_creates_report_data_json(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    path = tmp_path / "reports" / "report_data.json"

    output_path = write_report_data(path, report_data)

    assert output_path == path
    assert path.is_file()


def test_json_output_contains_required_top_level_sections(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    path = write_report_data(tmp_path / "report_data.json", report_data)

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert list(payload) == [
        "schema_version",
        "report_metadata",
        "experiment",
        "final_result",
        "baseline_metrics",
        "iterations",
        "status_counts",
        "artifacts",
        "llm",
        "experiment_config_details",
        "benchmark_config",
        "closed_loop_selection",
        "final_best_candidate",
        "reporting_status",
        "reason_summary",
        "reason_code_counts",
        "experiment_metadata",
    ]
    assert payload["schema_version"] == "report.v2"
    assert payload["report_metadata"]["report_profile"] == "single_experiment"
    assert payload["experiment"]["experiment_id"] == "exp_001"
    assert payload["experiment"]["target_file"] == TARGET_FILE
    assert payload["final_result"]["final_best_iteration"] == 0
    assert payload["baseline_metrics"]["runtime_ns_per_case_median"] is None
    assert payload["iterations"] == []
    assert payload["status_counts"] == {status.value: 0 for status in IterationStatus}
    assert payload["artifacts"]["report_html"] is None


def test_path_values_are_serialized_as_strings(tmp_path: Path) -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.artifacts = ReportArtifactMap(
        experiment_dir=tmp_path / "experiments" / "exp_001",
        report_data=tmp_path / "reports" / "report_data.json",
    )
    report_data.iterations.append(
        ReportIterationSummary(
            iteration=1,
            status="accepted_improvement",
            candidate_run_dir=tmp_path / "results" / "runs" / "candidate_001",
        )
    )

    payload = to_report_dict(report_data)

    assert isinstance(payload["artifacts"]["experiment_dir"], str)
    assert isinstance(payload["artifacts"]["report_data"], str)
    assert isinstance(payload["iterations"][0]["candidate_run_dir"], str)


def test_optional_runtime_and_correctness_fields_can_be_none() -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.iterations.append(
        ReportIterationSummary(
            iteration=1,
            status="valid_not_improved",
            runtime_ns_per_case_median=None,
            correctness_passed=None,
        )
    )

    payload = to_report_dict(report_data)

    assert payload["baseline_metrics"]["runtime_ns_per_case_median"] is None
    assert payload["baseline_metrics"]["correctness_passed"] is None
    assert payload["final_result"]["correctness_preserved"] is None
    assert payload["iterations"][0]["runtime_ns_per_case_median"] is None
    assert payload["iterations"][0]["correctness_passed"] is None


def test_reason_summary_defaults_to_empty_list() -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)

    payload = to_report_dict(report_data)

    assert payload["reason_summary"] == []


def test_reason_summary_item_round_trips_through_to_report_dict() -> None:
    report_data = make_empty_report_data("exp_001", TARGET_FILE)
    report_data.reason_summary = [
        ReportReasonSummaryItem(reason="runtime_not_improved", count=2, iterations=[1, 3]),
        ReportReasonSummaryItem(reason="no_op", count=1, iterations=[2]),
    ]

    payload = to_report_dict(report_data)

    assert len(payload["reason_summary"]) == 2
    assert payload["reason_summary"][0] == {
        "reason": "runtime_not_improved",
        "count": 2,
        "iterations": [1, 3],
    }
    assert payload["reason_summary"][1]["reason"] == "no_op"


def test_materialization_failed_iteration_with_no_runtime_serializes() -> None:
    iteration = ReportIterationSummary(
        iteration=2,
        status="materialization_failed",
        candidate_summary=None,
        expected_effect=None,
        risk_level=None,
        runtime_ns_per_case_median=None,
        correctness_passed=None,
        promoted=False,
        reason="Patch could not be applied.",
        candidate_run_dir=None,
    )

    payload = to_report_dict(iteration)

    assert payload["status"] == "materialization_failed"
    assert payload["runtime_ns_per_case_median"] is None
    assert payload["correctness_passed"] is None
    assert payload["promoted"] is False
    json.dumps(payload)
