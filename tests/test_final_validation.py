from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import pytest

from orchestrator.experiments.final_validation import run_final_validation


def _write_source(root: Path) -> None:
    path = root / "cpp" / "source.cc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("int x = 1;\n", encoding="utf-8")


def _benchmark_output(runtime: float, *, correct: bool = True) -> str:
    return "\n".join(
        [
            "solver_name: lambdatwist_p3p",
            "num_cases: 10",
            f"success_rate: {1.0 if correct else 0.5}",
            "mean_best_reprojection_error: 1e-12",
            "max_best_reprojection_error: 2e-12",
            "runtime_ns_total_median: 1000",
            f"runtime_ns_per_case_median: {runtime}",
            f"correctness_passed: {str(correct).lower()}",
            "valid_cases: 10",
            "total_solutions: 10",
            "",
        ]
    )


def _fake_executable(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    for name in ("absolute_pose_lambdatwist_benchmark", "absolute_pose_lambdatwist_benchmark.exe"):
        (build_dir / name).write_text("exe\n", encoding="utf-8")


def test_final_validation_aggregates_successful_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", str(repo_root / "eigen"))
    runtimes = {
        "baseline": [100.0, 110.0, 90.0, 102.0, 98.0],
        "final": [80.0, 84.0, 76.0, 82.0, 78.0],
    }
    run_counts = {"configure": 0, "build": 0, "benchmark": 0}
    benchmark_counts = {"baseline": 0, "final": 0}

    def runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        command_text = " ".join(str(part) for part in command)
        if " -S " in f" {command_text} ":
            run_counts["configure"] += 1
            return {"exit_code": 0, "duration_seconds": 0.1, "stdout": "", "stderr": ""}
        if "--build" in command:
            run_counts["build"] += 1
            _fake_executable(Path(command[2]))
            return {"exit_code": 0, "duration_seconds": 0.1, "stdout": "", "stderr": ""}
        group = "baseline" if "baseline" in _cwd.parts else "final"
        index = benchmark_counts[group]
        benchmark_counts[group] += 1
        run_counts["benchmark"] += 1
        return {"exit_code": 0, "duration_seconds": 0.3, "stdout": _benchmark_output(runtimes[group][index]), "stderr": ""}

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
    assert payload["diagnostics"]["summary"] == "All repeated validation runs completed successfully."
    assert run_counts == {"configure": 2, "build": 2, "benchmark": 10}
    assert (experiment_dir / "final_validation" / "baseline" / "source" / "cpp" / "source.cc").is_file()
    assert (experiment_dir / "final_validation" / "baseline" / "build").is_dir()
    assert (experiment_dir / "final_validation" / "baseline" / "runs" / "run_01.json").is_file()
    assert (experiment_dir / "final_validation" / "baseline" / "logs" / "run_01.log").is_file()
    assert not (experiment_dir / "final_validation" / "baseline_runs").exists()


def test_final_validation_records_failed_repetitions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", str(repo_root / "eigen"))
    benchmark_counts = {"baseline": 0, "final": 0}

    def runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        if "--build" in command:
            _fake_executable(Path(command[2]))
        if command and Path(str(command[0])).name.startswith("absolute_pose_lambdatwist_benchmark"):
            group = "baseline" if "baseline" in _cwd.parts else "final"
            benchmark_counts[group] += 1
            return {"exit_code": 0, "duration_seconds": 0.3, "stdout": _benchmark_output(100.0, correct=benchmark_counts[group] != 2), "stderr": ""}
        return {"exit_code": 0, "duration_seconds": 0.1, "stdout": "", "stderr": ""}

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
    assert payload["diagnostics"]["dominant_failed_step"] == "benchmark_correctness_check"
    assert payload["diagnostics"]["suggested_log_paths"]


def test_final_validation_comparison_null_without_correct_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", str(repo_root / "eigen"))

    def runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        if "--build" in command:
            _fake_executable(Path(command[2]))
        if command and Path(str(command[0])).name.startswith("absolute_pose_lambdatwist_benchmark"):
            return {"exit_code": 1, "duration_seconds": 0.3, "stdout": "", "stderr": "boom"}
        return {"exit_code": 0, "duration_seconds": 0.1, "stdout": "", "stderr": ""}

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
    assert payload["diagnostics"]["dominant_failed_step"] == "run_absolute_pose_lambdatwist_benchmark"
    assert payload["diagnostics"]["suggested_log_paths"]


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
