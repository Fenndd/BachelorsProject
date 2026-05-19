from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import pytest

from orchestrator.experiments import final_validation
from orchestrator.experiments.final_validation import run_final_validation


def _write_source(root: Path) -> None:
    cpp = root / "cpp"
    lambdatwist = cpp / "external" / "lambdatwist"
    core = cpp / "bench" / "families" / "geometric_pose_solvers" / "absolute_pose_solvers" / "core"
    adapter = (
        cpp
        / "bench"
        / "families"
        / "geometric_pose_solvers"
        / "absolute_pose_solvers"
        / "adapters"
        / "lambdatwist_p3p"
    )
    runners = cpp / "bench" / "families" / "geometric_pose_solvers" / "absolute_pose_solvers" / "runners"
    for directory in (lambdatwist, core, adapter, runners):
        directory.mkdir(parents=True, exist_ok=True)
    (lambdatwist / "p3p.cc").write_text("void p3p() {}\n", encoding="utf-8")
    (lambdatwist / "p3p.h").write_text("#pragma once\n", encoding="utf-8")
    (core / "absolute_pose_benchmark.cpp").write_text("void benchmark() {}\n", encoding="utf-8")
    (core / "absolute_pose_benchmark.hpp").write_text("#pragma once\n", encoding="utf-8")
    (adapter / "lambdatwist_p3p_adapter.cpp").write_text("void adapter() {}\n", encoding="utf-8")
    (adapter / "lambdatwist_p3p_adapter.hpp").write_text("#pragma once\n", encoding="utf-8")
    (runners / "lambdatwist_p3p_benchmark.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    (runners / "lambdatwist_p3p_adapter_validator.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    (cpp / "src").mkdir(parents=True, exist_ok=True)
    (cpp / "include").mkdir(parents=True, exist_ok=True)
    (cpp / "tests").mkdir(parents=True, exist_ok=True)
    (cpp / "bench" / "baseline_benchmark.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")


def _benchmark_output(runtime: float, *, correct: bool = True) -> str:
    return "\n".join(
        [
            "solver_name: lambdatwist_p3p",
            "num_problems: 10",
            "total_solutions: 30",
            "solutions_per_problem: 3.0",
            "valid_solutions: 30",
            "valid_solutions_percent: 100.0",
            f"gt_found: {10 if correct else 5}",
            f"gt_found_percent: {100.0 if correct else 50.0}",
            "runtime_ns_total_median: 1000",
            f"runtime_ns_per_problem_median: {runtime}",
            "tolerance: 1e-6",
            "camera_fov: 75",
            "n_point_point: 3",
            "n_point_line: 0",
            "timed_iterations: 10",
            "runtime_unit: ns",
            f"correctness_passed: {str(correct).lower()}",
            "",
        ]
    )


def _fake_executable(build_dir: Path) -> None:
    build_dir.mkdir(parents=True, exist_ok=True)
    for name in ("absolute_pose_lambdatwist_benchmark", "absolute_pose_lambdatwist_benchmark.exe"):
        (build_dir / name).write_text("exe\n", encoding="utf-8")


@pytest.fixture(autouse=True)
def _disable_path_length_preflight_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(final_validation, "WINDOWS_FINAL_VALIDATION_PATH_LENGTH_THRESHOLD", 10000)


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
        group = "baseline" if "b" in _cwd.parts else "final"
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
    assert payload["baseline"]["summary"]["median_runtime_ns_per_problem"] == 100.0
    assert payload["baseline"]["summary"]["mean_runtime_ns_per_problem"] == 100.0
    assert payload["baseline"]["summary"]["min_runtime_ns_per_problem"] == 90.0
    assert payload["baseline"]["summary"]["max_runtime_ns_per_problem"] == 110.0
    assert payload["final"]["summary"]["median_runtime_ns_per_problem"] == 80.0
    assert payload["comparison"]["median_speedup"] == 1.25
    assert payload["comparison"]["median_runtime_reduction_percent"] == 20.0
    assert payload["safety"]["updates_current_best"] is False
    assert payload["diagnostics"]["summary"] == "All repeated validation runs completed successfully."
    assert payload["diagnostics"]["suggested_log_paths"] == []
    assert payload["diagnostics"]["baseline_setup_failed"] is False
    assert payload["diagnostics"]["final_setup_failed"] is False
    assert payload["diagnostics"]["baseline_group_status"] == "completed"
    assert payload["diagnostics"]["final_group_status"] == "completed"
    assert run_counts == {"configure": 2, "build": 2, "benchmark": 10}
    assert report_path == experiment_dir / "val" / "final_validation_report.json"
    assert not (experiment_dir / "validation").exists()
    assert payload["source_layout"]["type"] == "minimal_final_validation_cpp_layout"
    for group, group_dir_name in (("baseline", "b"), ("final", "f")):
        assert payload[group]["setup"]["configure_status"] == "success"
        assert payload[group]["setup"]["build_status"] == "success"
        assert payload[group]["summary"]["benchmark_runs_attempted"] == 5
        group_dir = experiment_dir / "val" / group_dir_name
        cpp = group_dir / "cpp"
        assert (cpp / "CMakeLists.txt").is_file()
        assert (cpp / "external" / "lambdatwist").is_dir()
        assert (cpp / "bench" / "core").is_dir()
        assert (cpp / "bench" / "adapters" / "lambdatwist_p3p").is_dir()
        assert (cpp / "bench" / "runners" / "lambdatwist_p3p_benchmark.cpp").is_file()
        assert not (cpp / "src").exists()
        assert not (cpp / "include").exists()
        assert not (cpp / "tests").exists()
        assert not (cpp / "bench" / "baseline_benchmark.cpp").exists()
        assert not (cpp / "bench" / "families" / "geometric_pose_solvers" / "absolute_pose_solvers").exists()
        cmake_text = (cpp / "CMakeLists.txt").read_text(encoding="utf-8")
        assert 'set(ABSOLUTE_POSE_SOLVERS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/bench")' in cmake_text
        assert "baseline_smoke_test" not in cmake_text
        assert "baseline_benchmark" not in cmake_text
        assert "adapter_validator" not in cmake_text
        assert "absolute_pose_correctness_policy_test" not in cmake_text
        assert (group_dir / "build").is_dir()
        assert (group_dir / "runs" / "run_01.json").is_file()
        assert (group_dir / "logs" / "run_01.log").is_file()
        assert payload[group]["source_dir"].endswith(f"val/{group_dir_name}/cpp")
        assert payload[group]["build_dir"].endswith(f"val/{group_dir_name}/build")
        assert payload[group]["runs_dir"].endswith(f"val/{group_dir_name}/runs")
        assert payload[group]["logs_dir"].endswith(f"val/{group_dir_name}/logs")
        run = json.loads((group_dir / "runs" / "run_01.json").read_text(encoding="utf-8"))
        assert run["validation_mode"] == "benchmark_only"
        assert run["benchmark_run_status"] == "success"
        assert "verification_status" not in run
        assert not (group_dir / "source" / "cpp").exists()
    assert not (experiment_dir / "final_validation").exists()
    assert not (experiment_dir / "val" / "baseline_runs").exists()


def test_critical_validation_paths_scan_real_source_files(tmp_path: Path) -> None:
    source_cpp = tmp_path / "src" / "cpp"
    build_dir = tmp_path / "build"
    logs_dir = tmp_path / "logs"
    nested_source = source_cpp / "solvers" / "future_solver.cc"
    nested_header = source_cpp / "include" / "future_solver.hpp"
    ignored_text = source_cpp / "notes.txt"
    nested_source.parent.mkdir(parents=True, exist_ok=True)
    nested_header.parent.mkdir(parents=True, exist_ok=True)
    nested_source.write_text("int f() { return 1; }\n", encoding="utf-8")
    nested_header.write_text("#pragma once\n", encoding="utf-8")
    ignored_text.write_text("not source\n", encoding="utf-8")

    paths = final_validation._critical_validation_paths(source_cpp, build_dir, logs_dir)
    path_texts = {path.as_posix() for path in paths}
    object_root = build_dir / "CMakeFiles" / f"{final_validation.FAMILY_BENCHMARK_TARGET}.dir"

    assert nested_source.as_posix() in path_texts
    assert nested_header.as_posix() in path_texts
    assert (object_root / "solvers" / "future_solver.cc.obj").as_posix() in path_texts
    assert (object_root / "solvers" / "future_solver.cc.obj.d").as_posix() in path_texts
    assert ignored_text.as_posix() not in path_texts
    assert not any("absolute_pose_lambdatwist_benchmark_adapter.cc" in text for text in path_texts)


def test_default_final_validation_profile_preserves_layout_metadata() -> None:
    profile = final_validation.DEFAULT_FINAL_VALIDATION_PROFILE
    layout = final_validation._source_layout_metadata(profile)

    assert profile.profile_id == "absolute_pose_lambdatwist_p3p"
    assert profile.benchmark_target == "absolute_pose_lambdatwist_benchmark"
    assert layout["type"] == "minimal_final_validation_cpp_layout"
    assert layout["original_absolute_pose_root"] == "bench/families/geometric_pose_solvers/absolute_pose_solvers"
    assert layout["validation_absolute_pose_root"] == "bench"
    assert layout["copied_components"] == [
        "external/lambdatwist",
        "bench/core",
        "bench/adapters/lambdatwist_p3p",
        "bench/runners/lambdatwist_p3p_benchmark.cpp",
    ]


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
            group = "baseline" if "b" in _cwd.parts else "final"
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
    assert payload["diagnostics"]["baseline_group_status"] == "benchmark_failed"
    assert payload["diagnostics"]["final_group_status"] == "benchmark_failed"
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
    assert payload["diagnostics"]["baseline_failed_runs"] == 1
    assert payload["diagnostics"]["final_failed_runs"] == 1
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


def test_final_validation_setup_failure_does_not_create_fake_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", str(repo_root / "eigen"))

    def runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        if "--build" in command:
            return {
                "exit_code": 1,
                "duration_seconds": 0.2,
                "stdout": "",
                "stderr": "fatal error: object path is too long\nCMake Warning: maximum full path exceeded",
            }
        return {"exit_code": 0, "duration_seconds": 0.1, "stdout": "", "stderr": ""}

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
    assert payload["status"] == "incomplete"
    for group in ("baseline", "final"):
        assert payload[group]["setup"]["build_status"] == "failed"
        assert payload[group]["setup"]["failed_step"] == "build_absolute_pose_lambdatwist_benchmark"
        assert payload[group]["runs"] == []
        assert payload[group]["summary"]["benchmark_runs_attempted"] == 0
        assert payload[group]["summary"]["failed_runs"] == 0
        group_dir_name = "b" if group == "baseline" else "f"
        assert not (experiment_dir / "val" / group_dir_name / "runs" / "run_01.json").exists()
    assert payload["diagnostics"]["baseline_setup_failed"] is True
    assert payload["diagnostics"]["final_setup_failed"] is True
    assert payload["diagnostics"]["baseline_group_status"] == "setup_failed"
    assert payload["diagnostics"]["final_group_status"] == "setup_failed"
    assert payload["diagnostics"]["baseline_failed_runs"] == 0
    assert payload["diagnostics"]["final_failed_runs"] == 0
    assert payload["diagnostics"]["dominant_failed_step"] == "build_absolute_pose_lambdatwist_benchmark"
    assert "fatal error" in payload["diagnostics"]["dominant_error_excerpt"]
    assert payload["diagnostics"]["path_length_warning_detected"] is True
    assert payload["diagnostics"]["max_observed_path_length"] > 0


def test_final_validation_path_length_preflight_skips_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    experiment_dir = repo_root / "results" / "experiments" / "exp"
    baseline_source = repo_root
    final_source = experiment_dir / "final_optimized_source"
    _write_source(baseline_source)
    _write_source(final_source)
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", str(repo_root / "eigen"))
    monkeypatch.setattr(final_validation.platform, "system", lambda: "Windows")
    monkeypatch.setattr(final_validation, "WINDOWS_FINAL_VALIDATION_PATH_LENGTH_THRESHOLD", 10)

    def runner(command: Sequence[str], _cwd: Path) -> dict[str, Any]:
        raise AssertionError("path-length preflight should skip CMake")

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
    assert payload["status"] == "incomplete"
    assert payload["baseline"]["setup"]["failed_step"] == "path_length_preflight"
    assert "Maximum observed critical path length" in payload["baseline"]["setup"]["error_message"]
    assert payload["baseline"]["runs"] == []
    assert payload["baseline"]["summary"]["benchmark_runs_attempted"] == 0
    assert not (experiment_dir / "val" / "b" / "runs" / "run_01.json").exists()
    assert (experiment_dir / "val" / "b" / "logs" / "path_length_preflight.log").is_file()
    assert payload["diagnostics"]["dominant_failed_step"] == "path_length_preflight"
    assert payload["diagnostics"]["baseline_setup_failed"] is True
    assert payload["diagnostics"]["baseline_group_status"] == "setup_failed"


def test_final_validation_ignores_legacy_verification_status() -> None:
    runs = [
        {
            "verification_status": "success",
            "correctness_passed": True,
            "runtime_ns_per_problem_median": 10.0,
        },
        {
            "benchmark_run_status": "success",
            "verification_status": "failed",
            "correctness_passed": True,
            "runtime_ns_per_problem_median": 20.0,
        },
    ]

    summary = final_validation._summarize_runs(runs)

    assert summary["successful_runs"] == 1
    assert summary["failed_runs"] == 1
    assert summary["median_runtime_ns_per_problem"] == 20.0


def test_final_validation_diagnostics_do_not_fallback_to_verification_status() -> None:
    diagnostics = final_validation._diagnostics(
        {
            "status": "completed_partial",
            "baseline": {
                "setup": {},
                "runs": [
                    {
                        "verification_status": "success",
                        "correctness_passed": True,
                        "runtime_ns_per_problem_median": 100.0,
                    }
                ],
            },
            "final": {"setup": {}, "runs": []},
        }
    )

    assert diagnostics["baseline_failed_runs"] == 1
    assert diagnostics["baseline_group_status"] == "benchmark_failed"
    assert diagnostics["final_group_status"] == "not_run"
