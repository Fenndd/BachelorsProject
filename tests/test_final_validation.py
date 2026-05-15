from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from orchestrator.experiments.final_validation import run_final_validation


def _write_source(root: Path) -> None:
    path = root / "cpp" / "source.cc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("int x = 1;\n", encoding="utf-8")


def _write_verification(run_dir: Path, runtime: float, *, correct: bool = True) -> None:
    payload = {
        "overall_status": "success" if correct else "failed",
        "candidate_run_id": run_dir.name,
        "failed_step": None if correct else "benchmark_correctness_check",
        "error_message": None if correct else "correctness failed",
        "steps": [{"name": "run", "status": "success", "duration_seconds": 0.2}],
        "benchmark": {
            "parsed_runtime_ns_per_case_median": runtime,
            "parsed_correctness_passed": correct,
            "parsed_success_rate": 1.0 if correct else 0.5,
            "parsed_mean_best_reprojection_error": 1e-12,
            "parsed_max_best_reprojection_error": 2e-12,
            "parsed_valid_cases": 10,
            "parsed_total_solutions": 10,
        },
    }
    run_dir.joinpath("verification.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def test_final_validation_aggregates_successful_runs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)
    runtimes = {
        "baseline": [100.0, 110.0, 90.0, 102.0, 98.0],
        "final": [80.0, 84.0, 76.0, 82.0, 78.0],
    }

    def runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        run_dir = Path(command[-1])
        group = "baseline" if "baseline_runs" in run_dir.parts else "final"
        index = int(run_dir.name.split("_")[-1]) - 1
        _write_verification(run_dir, runtimes[group][index])
        return {"exit_code": 0, "duration_seconds": 0.3, "stdout": "", "stderr": ""}

    report_path = run_final_validation(
        experiment_dir=experiment_dir,
        experiment_id="exp",
        repo_root=repo_root,
        baseline_source_dir=baseline_source,
        final_source_dir=final_source,
        benchmark_repetitions=5,
        command_runner=runner,
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["baseline"]["summary"]["median_runtime_ns_per_case"] == 100.0
    assert payload["baseline"]["summary"]["mean_runtime_ns_per_case"] == 100.0
    assert payload["baseline"]["summary"]["min_runtime_ns_per_case"] == 90.0
    assert payload["baseline"]["summary"]["max_runtime_ns_per_case"] == 110.0
    assert payload["final"]["summary"]["median_runtime_ns_per_case"] == 80.0
    assert payload["comparison"]["median_speedup"] == 1.25
    assert payload["comparison"]["median_runtime_reduction_percent"] == 20.0
    assert payload["safety"]["updates_current_best"] is False


def test_final_validation_records_failed_repetitions(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)

    def runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        run_dir = Path(command[-1])
        index = int(run_dir.name.split("_")[-1])
        _write_verification(run_dir, 100.0, correct=index != 2)
        return {"exit_code": 0, "duration_seconds": 0.3, "stdout": "", "stderr": ""}

    report_path = run_final_validation(
        experiment_dir=experiment_dir,
        experiment_id="exp",
        repo_root=repo_root,
        baseline_source_dir=baseline_source,
        final_source_dir=final_source,
        benchmark_repetitions=2,
        command_runner=runner,
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed_partial"
    assert payload["baseline"]["summary"]["successful_runs"] == 1
    assert payload["baseline"]["summary"]["failed_runs"] == 1
    assert payload["final"]["summary"]["successful_runs"] == 1


def test_final_validation_comparison_null_without_correct_runs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)

    def runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        _write_verification(Path(command[-1]), 100.0, correct=False)
        return {"exit_code": 1, "duration_seconds": 0.3, "stdout": "", "stderr": ""}

    report_path = run_final_validation(
        experiment_dir=experiment_dir,
        experiment_id="exp",
        repo_root=repo_root,
        baseline_source_dir=baseline_source,
        final_source_dir=final_source,
        benchmark_repetitions=1,
        command_runner=runner,
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "incomplete"
    assert payload["comparison"]["median_speedup"] is None
    assert payload["comparison"]["median_runtime_reduction_percent"] is None


def test_final_validation_disabled_is_skipped(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)

    def fail_runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        raise AssertionError("disabled final validation should not run verifier")

    report_path = run_final_validation(
        experiment_dir=experiment_dir,
        experiment_id="exp",
        repo_root=repo_root,
        baseline_source_dir=baseline_source,
        final_source_dir=final_source,
        enabled=False,
        benchmark_repetitions=5,
        command_runner=fail_runner,
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["enabled"] is False
    assert payload["status"] == "skipped"
