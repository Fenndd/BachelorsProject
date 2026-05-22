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
