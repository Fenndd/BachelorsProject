"""Final repeated benchmark validation for closed-loop experiments.

This module is final-evaluation only. It creates one isolated source/build tree
per validation group and repeats only benchmark execution. It does not change
promotion decisions, current_best_source, or the main cpp/ tree.
"""

from __future__ import annotations

import fnmatch
import json
import os
import platform
import shutil
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from orchestrator.benchmarking import parse_absolute_pose_benchmark_output
from orchestrator.execution.candidate_benchmark_verification import (
    BENCHMARK_CORRECTNESS_CHECK_STEP,
    FAMILY_BENCHMARK_TARGET,
    PARSE_FAMILY_BENCHMARK_STEP,
)


SOURCE_TREE_IGNORE_NAMES = {
    "build",
    "build-codex",
    "build-pre-step-11-cleanup",
    "cmake-build-debug",
    "cmake-build-release",
    "CMakeFiles",
    "Testing",
}
SOURCE_TREE_IGNORE_PATTERNS = {
    "CMakeCache.txt",
    "build.ninja",
    ".ninja_*",
    "*.exe",
    "*.dll",
    "*.lib",
    "*.a",
    "*.obj",
    "*.o",
    "*.pdb",
    "*.ilk",
}


CommandRunner = Callable[[Sequence[str], Path], dict[str, Any]]


def run_final_validation(
    *,
    experiment_dir: Path,
    experiment_id: str,
    repo_root: Path,
    baseline_source_dir: Path,
    final_source_dir: Path,
    enabled: bool = True,
    benchmark_repetitions: int = 5,
    command_runner: CommandRunner | None = None,
) -> Path:
    """Run repeated final validation and write final_validation_report.json."""

    if benchmark_repetitions <= 0:
        raise ValueError("benchmark_repetitions must be a positive integer")

    validation_dir = experiment_dir / "final_validation"
    report_path = validation_dir / "final_validation_report.json"
    validation_dir.mkdir(parents=True, exist_ok=True)
    started_at = _now_iso()

    if not enabled:
        payload = {
            "schema_version": "final_validation.v1",
            "enabled": False,
            "status": "skipped",
            "benchmark_repetitions": benchmark_repetitions,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "baseline": _empty_group(baseline_source_dir),
            "final": _empty_group(final_source_dir),
            "comparison": _empty_comparison(),
            "safety": _safety_block(),
            "statistics_note": "Runtime standard deviation uses population std (statistics.pstdev).",
        }
        payload["diagnostics"] = _diagnostics(payload)
        _write_json(report_path, payload)
        return report_path

    runner = command_runner or _run_subprocess_command
    baseline_runs = _run_group(
        validation_dir=validation_dir,
        group_name="baseline",
        source_dir=baseline_source_dir,
        repetitions=benchmark_repetitions,
        repo_root=repo_root,
        runner=runner,
    )
    final_runs = _run_group(
        validation_dir=validation_dir,
        group_name="final",
        source_dir=final_source_dir,
        repetitions=benchmark_repetitions,
        repo_root=repo_root,
        runner=runner,
    )

    baseline_summary = _summarize_runs(baseline_runs)
    final_summary = _summarize_runs(final_runs)
    comparison = _comparison(baseline_summary, final_summary)
    payload = {
        "schema_version": "final_validation.v1",
        "enabled": True,
        "benchmark_repetitions": benchmark_repetitions,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "baseline": {
            "source_dir": _display_path(validation_dir / "baseline" / "source", repo_root),
            "runs": baseline_runs,
            "summary": baseline_summary,
        },
        "final": {
            "source_dir": _display_path(validation_dir / "final" / "source", repo_root),
            "runs": final_runs,
            "summary": final_summary,
        },
        "comparison": comparison,
        "safety": _safety_block(),
        "statistics_note": "Runtime standard deviation uses population std (statistics.pstdev).",
    }
    payload["status"] = _validation_status(
        baseline_summary,
        final_summary,
        comparison,
        benchmark_repetitions,
    )
    payload["diagnostics"] = _diagnostics(payload)
    _write_json(report_path, payload)
    return report_path


def _run_group(
    *,
    validation_dir: Path,
    group_name: str,
    source_dir: Path,
    repetitions: int,
    repo_root: Path,
    runner: CommandRunner,
) -> list[dict[str, Any]]:
    group_dir = validation_dir / group_name
    if group_dir.exists():
        shutil.rmtree(group_dir)
    source_cpp = group_dir / "source" / "cpp"
    build_dir = group_dir / "build"
    runs_dir = group_dir / "runs"
    logs_dir = group_dir / "logs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    try:
        _copy_source_tree(source_dir / "cpp", source_cpp)
        setup_failure = _configure_and_build_group(
            group_dir=group_dir,
            source_cpp=source_cpp,
            build_dir=build_dir,
            logs_dir=logs_dir,
            repo_root=repo_root,
            runner=runner,
        )
    except Exception as exc:
        setup_failure = {
            "failed_step": "prepare_source",
            "error_message": str(exc),
            "log_path": None,
        }

    if setup_failure is not None:
        return [
            _failed_run(
                run_index=index,
                group_name=group_name,
                group_dir=group_dir,
                log_path=setup_failure.get("log_path"),
                failed_step=_string_or_none(setup_failure.get("failed_step")) or "configure_cmake",
                error_message=_string_or_none(setup_failure.get("error_message")),
                repo_root=repo_root,
            )
            for index in range(1, repetitions + 1)
        ]

    try:
        benchmark_executable = _find_executable(build_dir, FAMILY_BENCHMARK_TARGET)
    except OSError as exc:
        return [
            _failed_run(
                run_index=index,
                group_name=group_name,
                group_dir=group_dir,
                log_path=None,
                failed_step="run_absolute_pose_lambdatwist_benchmark",
                error_message=str(exc),
                repo_root=repo_root,
            )
            for index in range(1, repetitions + 1)
        ]
    runs: list[dict[str, Any]] = []
    for index in range(1, repetitions + 1):
        runs.append(
            _run_benchmark_repetition(
                run_index=index,
                group_name=group_name,
                group_dir=group_dir,
                runs_dir=runs_dir,
                logs_dir=logs_dir,
                benchmark_executable=benchmark_executable,
                repo_root=repo_root,
                runner=runner,
            )
        )
    return runs


def _configure_and_build_group(
    *,
    group_dir: Path,
    source_cpp: Path,
    build_dir: Path,
    logs_dir: Path,
    repo_root: Path,
    runner: CommandRunner,
) -> dict[str, Any] | None:
    cmake_exe = os.environ.get("CMAKE_EXE", "cmake")
    cmake_generator = os.environ.get("CMAKE_GENERATOR")
    cmake_cxx_compiler = os.environ.get("CMAKE_CXX_COMPILER")
    cmake_make_program = os.environ.get("CMAKE_MAKE_PROGRAM")
    eigen_include_dir = os.environ.get("EIGEN3_INCLUDE_DIR")
    cmake_build_type = os.environ.get(
        "BENCHMARK_CMAKE_BUILD_TYPE",
        os.environ.get("CMAKE_BUILD_TYPE", "Release"),
    )

    if not eigen_include_dir:
        return {
            "failed_step": "environment",
            "error_message": "EIGEN3_INCLUDE_DIR is not set.",
            "log_path": None,
        }

    configure_command = [
        cmake_exe,
        "-S",
        str(source_cpp),
        "-B",
        str(build_dir),
        f"-DEIGEN3_INCLUDE_DIR={eigen_include_dir}",
    ]
    if cmake_generator:
        configure_command.extend(["-G", cmake_generator])
    if cmake_cxx_compiler:
        configure_command.append(f"-DCMAKE_CXX_COMPILER={cmake_cxx_compiler}")
    if cmake_make_program:
        configure_command.append(f"-DCMAKE_MAKE_PROGRAM={cmake_make_program}")
    configure_command.append(f"-DCMAKE_BUILD_TYPE={cmake_build_type}")

    configure_stage = _run_command(
        configure_command,
        group_dir,
        logs_dir / "configure_cmake.log",
        runner,
    )
    if configure_stage.get("exit_code") != 0:
        return _setup_failure("configure_cmake", configure_stage, logs_dir / "configure_cmake.log")

    build_command = [
        cmake_exe,
        "--build",
        str(build_dir),
        "--target",
        FAMILY_BENCHMARK_TARGET,
        "--config",
        cmake_build_type,
    ]
    build_stage = _run_command(
        build_command,
        group_dir,
        logs_dir / "build_absolute_pose_lambdatwist_benchmark.log",
        runner,
    )
    if build_stage.get("exit_code") != 0:
        return _setup_failure(
            "build_absolute_pose_lambdatwist_benchmark",
            build_stage,
            logs_dir / "build_absolute_pose_lambdatwist_benchmark.log",
        )
    return None


def _copy_source_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Source cpp directory not found: {source}")
    shutil.copytree(source, destination, ignore=_source_tree_ignore)


def _source_tree_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in SOURCE_TREE_IGNORE_NAMES:
            ignored.add(name)
        elif any(fnmatch.fnmatch(name, pattern) for pattern in SOURCE_TREE_IGNORE_PATTERNS):
            ignored.add(name)
    return ignored


def _run_subprocess_command(command: Sequence[str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    except OSError as exc:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error_message": str(exc),
        }


def _run_command(
    command: Sequence[str],
    cwd: Path,
    log_path: Path,
    runner: CommandRunner,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        stage = runner(command, cwd)
    except Exception as exc:
        stage = {"exit_code": None, "stdout": "", "stderr": str(exc), "error_message": str(exc)}
    duration = stage.get("duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        stage["duration_seconds"] = round(time.perf_counter() - started, 3)
    _write_command_log(log_path, command, cwd, stage)
    return stage


def _write_command_log(
    path: Path,
    command: Sequence[str] | str,
    cwd: Path,
    stage: dict[str, Any],
) -> None:
    command_text = command if isinstance(command, str) else _format_command(command)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"COMMAND: {command_text}",
                f"CWD: {cwd}",
                f"EXIT_CODE: {stage.get('exit_code')}",
                "",
                "STDOUT:",
                str(stage.get("stdout") or ""),
                "",
                "STDERR:",
                str(stage.get("stderr") or stage.get("error_message") or ""),
                "",
            ]
        ),
        encoding="utf-8",
    )


def _setup_failure(step: str, stage: dict[str, Any], log_path: Path) -> dict[str, Any]:
    return {
        "failed_step": step,
        "error_message": _stage_error(stage),
        "log_path": log_path,
    }


def _run_benchmark_repetition(
    *,
    run_index: int,
    group_name: str,
    group_dir: Path,
    runs_dir: Path,
    logs_dir: Path,
    benchmark_executable: Path,
    repo_root: Path,
    runner: CommandRunner,
) -> dict[str, Any]:
    validation_run_id = f"final_validation_{group_name}_{run_index:02d}"
    log_path = logs_dir / f"run_{run_index:02d}.log"
    stage = _run_command([str(benchmark_executable)], group_dir, log_path, runner)
    run = _run_from_benchmark_stage(
        run_index=run_index,
        validation_run_id=validation_run_id,
        group_name=group_name,
        group_dir=group_dir,
        log_path=log_path,
        stage=stage,
        repo_root=repo_root,
    )
    _write_json(runs_dir / f"run_{run_index:02d}.json", run)
    return run


def _run_from_benchmark_stage(
    *,
    run_index: int,
    validation_run_id: str,
    group_name: str,
    group_dir: Path,
    log_path: Path | None,
    stage: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    failed_step: str | None = None
    error_message: str | None = None
    benchmark = _empty_benchmark(raw_output_available=bool(stage.get("stdout")))
    parse_status = "not_run"

    if stage.get("exit_code") != 0:
        failed_step = "run_absolute_pose_lambdatwist_benchmark"
        error_message = _stage_error(stage)
    else:
        parse_result = parse_absolute_pose_benchmark_output(str(stage.get("stdout") or ""))
        benchmark = _benchmark_from_parse(str(stage.get("stdout") or ""), parse_result)
        parse_status = "success" if parse_result["parse_success"] else "failed"
        if not parse_result["parse_success"]:
            failed_step = PARSE_FAMILY_BENCHMARK_STEP
            error_message = (
                "Could not parse family benchmark output. "
                f"Missing fields: {parse_result['missing_fields']}; "
                f"parse errors: {parse_result['parse_errors']}"
            )
        elif benchmark.get("parsed_correctness_passed") is not True:
            failed_step = BENCHMARK_CORRECTNESS_CHECK_STEP
            error_message = _build_benchmark_correctness_error_message(benchmark)

    verification_status = "failed" if failed_step else "success"
    return {
        "run_index": run_index,
        "validation_run_id": validation_run_id,
        "group": group_name,
        "group_dir": _display_path(group_dir, repo_root),
        "run_dir": _display_path(group_dir, repo_root),
        "benchmark_log_path": None if log_path is None else _display_path(log_path, repo_root),
        "benchmark_parse_status": parse_status,
        "verification_status": verification_status,
        "correctness_passed": _bool_or_none(benchmark.get("parsed_correctness_passed")),
        "runtime_ns_per_case_median": _number_or_none(benchmark.get("parsed_runtime_ns_per_case_median")),
        "success_rate": _number_or_none(benchmark.get("parsed_success_rate")),
        "mean_best_reprojection_error": _number_or_none(benchmark.get("parsed_mean_best_reprojection_error")),
        "max_best_reprojection_error": _number_or_none(benchmark.get("parsed_max_best_reprojection_error")),
        "total_solutions": _int_or_none(benchmark.get("parsed_total_solutions")),
        "valid_cases": _int_or_none(benchmark.get("parsed_valid_cases")),
        "failed_step": failed_step,
        "error_message": error_message,
    }


def _failed_run(
    *,
    run_index: int,
    group_name: str,
    group_dir: Path,
    log_path: Any,
    failed_step: str,
    error_message: str | None,
    repo_root: Path,
) -> dict[str, Any]:
    validation_run_id = f"final_validation_{group_name}_{run_index:02d}"
    run = {
        "run_index": run_index,
        "validation_run_id": validation_run_id,
        "group": group_name,
        "group_dir": _display_path(group_dir, repo_root),
        "run_dir": _display_path(group_dir, repo_root),
        "benchmark_log_path": _display_path(log_path, repo_root) if isinstance(log_path, Path) else None,
        "benchmark_parse_status": "not_run",
        "verification_status": "failed",
        "correctness_passed": None,
        "runtime_ns_per_case_median": None,
        "success_rate": None,
        "mean_best_reprojection_error": None,
        "max_best_reprojection_error": None,
        "total_solutions": None,
        "valid_cases": None,
        "failed_step": failed_step,
        "error_message": error_message,
    }
    _write_json(group_dir / "runs" / f"run_{run_index:02d}.json", run)
    return run


def _find_executable(build_dir: Path, executable_name: str) -> Path:
    expected_name = f"{executable_name}.exe" if platform.system() == "Windows" else executable_name
    candidates = sorted(build_dir.rglob(expected_name))
    if not candidates and expected_name.endswith(".exe"):
        candidates = sorted(build_dir.rglob(executable_name))
    if not candidates:
        raise FileNotFoundError(
            f"Could not find {executable_name} executable under build directory: {build_dir}"
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _format_command(command: Sequence[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def _stage_error(stage: dict[str, Any]) -> str:
    return (
        _string_or_none(stage.get("error_message"))
        or _string_or_none(stage.get("stderr"))
        or f"Command exited with code {stage.get('exit_code')}"
    )


def _empty_benchmark(raw_output_available: bool = False) -> dict[str, Any]:
    return {
        "family": "absolute_pose_solvers",
        "solver": "lambdatwist_p3p",
        "runtime_unit": "ns",
        "raw_output_available": raw_output_available,
        "parse_success": False,
        "missing_fields": [
            "solver_name",
            "num_cases",
            "success_rate",
            "mean_best_reprojection_error",
            "max_best_reprojection_error",
            "runtime_ns_total_median",
            "runtime_ns_per_case_median",
            "correctness_passed",
        ],
        "parse_errors": [],
        "parsed_solver_name": None,
        "parsed_num_cases": None,
        "parsed_success_rate": None,
        "parsed_mean_best_reprojection_error": None,
        "parsed_max_best_reprojection_error": None,
        "parsed_runtime_ns_total_median": None,
        "parsed_runtime_ns_per_case_median": None,
        "parsed_correctness_passed": None,
        "parsed_valid_cases": None,
        "parsed_total_solutions": None,
        "benchmark_options": None,
    }


def _benchmark_from_parse(stdout: str, parse_result: dict[str, Any]) -> dict[str, Any]:
    parsed_metrics = parse_result["metrics"]
    benchmark = _empty_benchmark(raw_output_available=bool(stdout))
    benchmark.update(
        {
            "parse_success": parse_result["parse_success"],
            "missing_fields": parse_result["missing_fields"],
            "parse_errors": parse_result["parse_errors"],
            "parsed_solver_name": parsed_metrics.get("solver_name"),
            "parsed_num_cases": parsed_metrics.get("num_cases"),
            "parsed_success_rate": parsed_metrics.get("success_rate"),
            "parsed_mean_best_reprojection_error": parsed_metrics.get("mean_best_reprojection_error"),
            "parsed_max_best_reprojection_error": parsed_metrics.get("max_best_reprojection_error"),
            "parsed_runtime_ns_total_median": parsed_metrics.get("runtime_ns_total_median"),
            "parsed_runtime_ns_per_case_median": parsed_metrics.get("runtime_ns_per_case_median"),
            "parsed_correctness_passed": parsed_metrics.get("correctness_passed"),
            "parsed_valid_cases": parsed_metrics.get("valid_cases"),
            "parsed_total_solutions": parsed_metrics.get("total_solutions"),
        }
    )
    return benchmark


def _build_benchmark_correctness_error_message(benchmark: dict[str, Any]) -> str:
    return (
        "Family benchmark parsed successfully, but correctness_passed=false. "
        f"success_rate={benchmark.get('parsed_success_rate')!r}, "
        "mean_best_reprojection_error="
        f"{benchmark.get('parsed_mean_best_reprojection_error')!r}, "
        "max_best_reprojection_error="
        f"{benchmark.get('parsed_max_best_reprojection_error')!r}."
    )


def _diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    status = _string_or_none(payload.get("status")) or "skipped"
    baseline_runs = _group_runs(payload, "baseline")
    final_runs = _group_runs(payload, "final")
    failed_runs = [
        run for run in [*baseline_runs, *final_runs]
        if run.get("verification_status") != "success" or run.get("correctness_passed") is not True
    ]
    failed_steps = [
        str(run.get("failed_step"))
        for run in failed_runs
        if isinstance(run.get("failed_step"), str) and run.get("failed_step")
    ]
    dominant_failed_step = None
    if failed_steps:
        dominant_failed_step = max(sorted(set(failed_steps)), key=failed_steps.count)

    if status == "completed":
        summary = "All repeated validation runs completed successfully."
    elif status == "completed_partial":
        summary = "Repeated validation comparison is available, but some runs failed or failed correctness."
    elif status == "incomplete":
        summary = "Repeated validation could not produce comparison metrics."
    elif status == "skipped":
        summary = "Repeated validation was skipped."
    else:
        summary = "Repeated validation status is unavailable."

    suggested_logs = []
    for run in failed_runs or [*baseline_runs[:1], *final_runs[:1]]:
        log_path = run.get("benchmark_log_path")
        if isinstance(log_path, str) and log_path and log_path not in suggested_logs:
            suggested_logs.append(log_path)
        if len(suggested_logs) >= 4:
            break

    return {
        "summary": summary,
        "dominant_failed_step": dominant_failed_step,
        "baseline_failed_runs": len([
            run for run in baseline_runs
            if run.get("verification_status") != "success" or run.get("correctness_passed") is not True
        ]),
        "final_failed_runs": len([
            run for run in final_runs
            if run.get("verification_status") != "success" or run.get("correctness_passed") is not True
        ]),
        "suggested_log_paths": suggested_logs,
    }


def _group_runs(payload: dict[str, Any], group_name: str) -> list[dict[str, Any]]:
    group = payload.get(group_name)
    if not isinstance(group, dict) or not isinstance(group.get("runs"), list):
        return []
    return [run for run in group["runs"] if isinstance(run, dict)]


def _summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    correct = [
        run for run in runs
        if run.get("verification_status") == "success"
        and run.get("correctness_passed") is True
        and isinstance(run.get("runtime_ns_per_case_median"), (int, float))
        and not isinstance(run.get("runtime_ns_per_case_median"), bool)
    ]
    runtimes = [float(run["runtime_ns_per_case_median"]) for run in correct]
    success_rates = [
        float(run["success_rate"])
        for run in correct
        if isinstance(run.get("success_rate"), (int, float)) and not isinstance(run.get("success_rate"), bool)
    ]
    return {
        "successful_runs": len(correct),
        "failed_runs": len(runs) - len(correct),
        "median_runtime_ns_per_case": statistics.median(runtimes) if runtimes else None,
        "mean_runtime_ns_per_case": statistics.fmean(runtimes) if runtimes else None,
        "min_runtime_ns_per_case": min(runtimes) if runtimes else None,
        "max_runtime_ns_per_case": max(runtimes) if runtimes else None,
        "std_runtime_ns_per_case": statistics.pstdev(runtimes) if len(runtimes) > 1 else (0.0 if runtimes else None),
        "all_correctness_passed": bool(runs) and all(run.get("correctness_passed") is True for run in runs),
        "success_rate_min": min(success_rates) if success_rates else None,
        "success_rate_mean": statistics.fmean(success_rates) if success_rates else None,
    }


def _comparison(baseline: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    baseline_median = _number_or_none(baseline.get("median_runtime_ns_per_case"))
    final_median = _number_or_none(final.get("median_runtime_ns_per_case"))
    baseline_mean = _number_or_none(baseline.get("mean_runtime_ns_per_case"))
    final_mean = _number_or_none(final.get("mean_runtime_ns_per_case"))
    return {
        "median_speedup": _speedup(baseline_median, final_median),
        "median_runtime_reduction_percent": _reduction_percent(baseline_median, final_median),
        "mean_speedup": _speedup(baseline_mean, final_mean),
        "mean_runtime_reduction_percent": _reduction_percent(baseline_mean, final_mean),
        "baseline_reference": "original_baseline",
        "final_reference": "final_optimized_source",
    }


def _validation_status(
    baseline_summary: dict[str, Any],
    final_summary: dict[str, Any],
    comparison: dict[str, Any],
    repetitions: int,
) -> str:
    baseline_successful = _int_or_zero(baseline_summary.get("successful_runs"))
    final_successful = _int_or_zero(final_summary.get("successful_runs"))
    baseline_failed = _int_or_zero(baseline_summary.get("failed_runs"))
    final_failed = _int_or_zero(final_summary.get("failed_runs"))
    if comparison.get("median_speedup") is None:
        return "incomplete"
    if (
        baseline_failed == 0
        and final_failed == 0
        and baseline_successful == repetitions
        and final_successful == repetitions
    ):
        return "completed"
    return "completed_partial"


def _empty_group(source_dir: Path) -> dict[str, Any]:
    return {"source_dir": str(source_dir), "runs": [], "summary": _summarize_runs([])}


def _empty_comparison() -> dict[str, Any]:
    return {
        "median_speedup": None,
        "median_runtime_reduction_percent": None,
        "mean_speedup": None,
        "mean_runtime_reduction_percent": None,
        "baseline_reference": "original_baseline",
        "final_reference": "final_optimized_source",
    }


def _safety_block() -> dict[str, bool]:
    return {
        "updates_current_best": False,
        "changes_promotion_decision": False,
        "modifies_main_cpp_tree": False,
    }


def _speedup(baseline: float | None, final: float | None) -> float | None:
    if baseline is None or final is None or final == 0:
        return None
    return baseline / final


def _reduction_percent(baseline: float | None, final: float | None) -> float | None:
    if baseline is None or final is None or baseline == 0:
        return None
    return ((baseline - final) / baseline) * 100.0


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


__all__ = ["run_final_validation"]
