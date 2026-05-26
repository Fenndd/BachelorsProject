"""Tests for the single-run final benchmark comparison module."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

import json
import os
from pathlib import Path

import pytest

from orchestrator.experiments.final_selection_report import (
    FINAL_SELECTION_REPORT_FILENAME,
    run_final_selection_report,
)
from orchestrator.core.benchmarking.candidate_decision import CandidateDecisionThresholds
from orchestrator.core.benchmarking.solver_registry import SolverBenchmarkDescriptor


from orchestrator.tests.conftest import TARGET_FILE, write_json, make_benchmark_payload


def _baseline_dir(tmp_path: Path, runtime: float = 1000.0) -> Path:
    baseline = tmp_path / "results" / "runs" / "baseline"
    write_json(baseline / "metrics.json", make_benchmark_payload(runtime))
    return baseline


def _final_source_dir(tmp_path: Path) -> Path:
    src = tmp_path / "final_optimized_source"
    (src / "cpp").mkdir(parents=True, exist_ok=True)
    return src


def _experiment_dir(tmp_path: Path, experiment_id: str = "exp_001") -> Path:
    d = tmp_path / "results" / "experiments" / experiment_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_baseline_is_best_writes_skipped_report(tmp_path: Path) -> None:
    exp_dir = _experiment_dir(tmp_path)
    baseline = _baseline_dir(tmp_path, runtime=1000.0)
    src = _final_source_dir(tmp_path)

    report_path = run_final_selection_report(
        experiment_dir=exp_dir,
        experiment_id="exp_001",
        repo_root=tmp_path,
        baseline_run_dir=baseline,
        final_source_dir=src,
        final_best_run_dir=baseline,
        target_file=TARGET_FILE,
        final_best_is_baseline=True,
    )

    assert report_path == exp_dir / FINAL_SELECTION_REPORT_FILENAME
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["report_type"] == "single_run_final_selection_report"
    assert report["final_best_is_baseline"] is True
    assert report["status"] == "skipped"
    assert report["comparison"]["speedup"] == 1.0
    assert report["comparison"]["runtime_reduction_percent"] == 0.0
    assert report["decision_vs_original_baseline"] is None


def test_baseline_is_best_sets_comparison_from_baseline_metrics(tmp_path: Path) -> None:
    exp_dir = _experiment_dir(tmp_path)
    baseline = _baseline_dir(tmp_path, runtime=800.0)
    src = _final_source_dir(tmp_path)

    report_path = run_final_selection_report(
        experiment_dir=exp_dir,
        experiment_id="exp_001",
        repo_root=tmp_path,
        baseline_run_dir=baseline,
        final_source_dir=src,
        final_best_run_dir=baseline,
        target_file=TARGET_FILE,
        final_best_is_baseline=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["comparison"]["baseline_runtime_ns_per_problem_median"] == 800.0
    assert report["comparison"]["final_runtime_ns_per_problem_median"] == 800.0


def test_non_baseline_without_eigen_fails_with_environment_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EIGEN3_INCLUDE_DIR", raising=False)
    exp_dir = _experiment_dir(tmp_path)
    baseline = _baseline_dir(tmp_path)
    src = _final_source_dir(tmp_path)

    report_path = run_final_selection_report(
        experiment_dir=exp_dir,
        experiment_id="exp_001",
        repo_root=tmp_path,
        baseline_run_dir=baseline,
        final_source_dir=src,
        final_best_run_dir=baseline,
        target_file=TARGET_FILE,
        final_best_is_baseline=False,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["failed_step"] == "environment"
    assert "EIGEN3_INCLUDE_DIR" in report["error_message"]


def test_report_structure_has_required_fields(tmp_path: Path) -> None:
    exp_dir = _experiment_dir(tmp_path)
    baseline = _baseline_dir(tmp_path)
    src = _final_source_dir(tmp_path)

    report_path = run_final_selection_report(
        experiment_dir=exp_dir,
        experiment_id="exp_001",
        repo_root=tmp_path,
        baseline_run_dir=baseline,
        final_source_dir=src,
        final_best_run_dir=baseline,
        target_file=TARGET_FILE,
        final_best_is_baseline=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    for key in ("report_type", "metric_source", "final_best_is_baseline", "status",
                "baseline_benchmark", "final_benchmark", "comparison", "artifacts"):
        assert key in report, f"Missing key: {key}"
    for key in ("speedup", "runtime_reduction_percent",
                "baseline_runtime_ns_per_problem_median",
                "final_runtime_ns_per_problem_median", "candidate_runtime_lower"):
        assert key in report["comparison"], f"Missing comparison key: {key}"


def test_report_file_written_at_experiment_dir_root(tmp_path: Path) -> None:
    exp_dir = _experiment_dir(tmp_path)
    baseline = _baseline_dir(tmp_path)
    src = _final_source_dir(tmp_path)

    report_path = run_final_selection_report(
        experiment_dir=exp_dir,
        experiment_id="exp_001",
        repo_root=tmp_path,
        baseline_run_dir=baseline,
        final_source_dir=src,
        final_best_run_dir=baseline,
        target_file=TARGET_FILE,
        final_best_is_baseline=True,
    )

    assert report_path.parent == exp_dir
    assert report_path.name == FINAL_SELECTION_REPORT_FILENAME


def test_baseline_missing_metrics_still_writes_report(tmp_path: Path) -> None:
    exp_dir = _experiment_dir(tmp_path)
    baseline = tmp_path / "results" / "runs" / "baseline"
    baseline.mkdir(parents=True, exist_ok=True)
    src = _final_source_dir(tmp_path)

    report_path = run_final_selection_report(
        experiment_dir=exp_dir,
        experiment_id="exp_001",
        repo_root=tmp_path,
        baseline_run_dir=baseline,
        final_source_dir=src,
        final_best_run_dir=baseline,
        target_file=TARGET_FILE,
        final_best_is_baseline=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "skipped"
    assert report["comparison"]["speedup"] == 1.0


class _FakeParser:
    """Callable that returns a parse-success dict for benchmark output."""

    def __call__(self, _stdout: str) -> dict:
        return {"parse_success": True, "missing_fields": []}


def _fake_decision(
    _baseline: str, _candidate: str, thresholds: CandidateDecisionThresholds | None = None,
) -> dict:
    return {
        "status": "accepted_improvement",
        "comparison": {
            "speedup": 1.2,
            "runtime_reduction_percent": 16.0,
            "candidate_runtime_lower": True,
            "reference_gt_found_percent": 100.0,
            "candidate_gt_found_percent": 100.0,
            "gt_found_delta_points": 0.0,
            "gt_found_drop_points": 0.0,
            "gt_found_gate_enabled": thresholds is not None and thresholds.gt_found_max_drop_points is not None,
            "gt_found_max_drop_points": (
                thresholds.gt_found_max_drop_points if thresholds else None
            ),
        },
        "rejection_reasons": [],
    }


_FAKE_RUN_COMMAND_RETURN = (
    {"name": "fake", "status": "success", "exit_code": 0, "duration_seconds": 0.0},
    None,  # error_message
    "",     # stdout
)


def test_gt_found_max_drop_points_passed_to_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify run_final_selection_report passes gt_found_max_drop_points."""
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", "/fake/eigen")
    exp_dir = _experiment_dir(tmp_path)
    baseline = _baseline_dir(tmp_path, runtime=1000.0)
    src = _final_source_dir(tmp_path)
    build_dir = tmp_path / "workspace" / "experiments" / "exp_001" / "final_selection_build"
    build_dir.mkdir(parents=True, exist_ok=True)

    captured_thresholds: list = []

    def _capturing_decision(
        baseline_run_dir, candidate_run_dir, thresholds=None,
    ):
        captured_thresholds.append(
            thresholds.gt_found_max_drop_points if thresholds else None
        )
        return _fake_decision(baseline_run_dir, candidate_run_dir, thresholds)

    fake_descriptor = SolverBenchmarkDescriptor(
        solver_id="lambdatwist_p3p",
        family="absolute_pose_solvers",
        parser=_FakeParser(),
        benchmark_target="fake_benchmark",
        adapter_validator_target=None,
        benchmark_step_name="fake_benchmark_step",
        adapter_validator_step_name=None,
        default_target_file=TARGET_FILE,
        default_allowed_files=(TARGET_FILE,),
    )

    monkeypatch.setattr(
        "orchestrator.experiments.final_selection_report.evaluate_candidate_against_baseline",
        _capturing_decision,
    )
    monkeypatch.setattr(
        "orchestrator.experiments.final_selection_report.run_command",
        lambda *a, **kw: _FAKE_RUN_COMMAND_RETURN,
    )
    monkeypatch.setattr(
        "orchestrator.experiments.final_selection_report.find_executable",
        lambda *a: build_dir / "fake_exe",
    )
    monkeypatch.setattr(
        "orchestrator.experiments.final_selection_report.benchmark_artifact_from_parse",
        lambda *a: make_benchmark_payload(runtime=800.0)["benchmark"],
    )

    report_path = run_final_selection_report(
        experiment_dir=exp_dir,
        experiment_id="exp_001",
        repo_root=tmp_path,
        baseline_run_dir=baseline,
        final_source_dir=src,
        final_best_run_dir=baseline,
        target_file=TARGET_FILE,
        final_best_is_baseline=False,
        gt_found_max_drop_points=2.5,
        descriptor=fake_descriptor,
    )

    assert captured_thresholds == [2.5]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "completed"


def test_gt_found_max_drop_points_none_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When not passed, gt_found_max_drop_points defaults to None."""
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", "/fake/eigen")
    exp_dir = _experiment_dir(tmp_path)
    baseline = _baseline_dir(tmp_path, runtime=1000.0)
    src = _final_source_dir(tmp_path)
    build_dir = tmp_path / "workspace" / "experiments" / "exp_001" / "final_selection_build"
    build_dir.mkdir(parents=True, exist_ok=True)

    captured_thresholds: list = []

    def _capturing_decision(
        baseline_run_dir, candidate_run_dir, thresholds=None,
    ):
        captured_thresholds.append(
            thresholds.gt_found_max_drop_points if thresholds else None
        )
        return _fake_decision(baseline_run_dir, candidate_run_dir, thresholds)

    fake_descriptor = SolverBenchmarkDescriptor(
        solver_id="lambdatwist_p3p",
        family="absolute_pose_solvers",
        parser=_FakeParser(),
        benchmark_target="fake_benchmark",
        adapter_validator_target=None,
        benchmark_step_name="fake_benchmark_step",
        adapter_validator_step_name=None,
        default_target_file=TARGET_FILE,
        default_allowed_files=(TARGET_FILE,),
    )

    monkeypatch.setattr(
        "orchestrator.experiments.final_selection_report.evaluate_candidate_against_baseline",
        _capturing_decision,
    )
    monkeypatch.setattr(
        "orchestrator.experiments.final_selection_report.run_command",
        lambda *a, **kw: _FAKE_RUN_COMMAND_RETURN,
    )
    monkeypatch.setattr(
        "orchestrator.experiments.final_selection_report.find_executable",
        lambda *a: build_dir / "fake_exe",
    )
    monkeypatch.setattr(
        "orchestrator.experiments.final_selection_report.benchmark_artifact_from_parse",
        lambda *a: make_benchmark_payload(runtime=800.0)["benchmark"],
    )

    report_path = run_final_selection_report(
        experiment_dir=exp_dir,
        experiment_id="exp_001",
        repo_root=tmp_path,
        baseline_run_dir=baseline,
        final_source_dir=src,
        final_best_run_dir=baseline,
        target_file=TARGET_FILE,
        final_best_is_baseline=False,
        descriptor=fake_descriptor,
    )

    assert captured_thresholds == [None]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "completed"
