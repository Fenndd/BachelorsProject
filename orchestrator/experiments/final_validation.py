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
SOURCE_FILE_SUFFIXES_FOR_PATH_PREFLIGHT = {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh"}

WINDOWS_FINAL_VALIDATION_PATH_LENGTH_THRESHOLD = 240


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

    validation_dir = experiment_dir / "validation"
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
            "baseline": _empty_group(validation_dir / "baseline" / "cpp", repo_root),
            "final": _empty_group(validation_dir / "final" / "cpp", repo_root),
            "comparison": _empty_comparison(),
            "safety": _safety_block(),
            "statistics_note": "Runtime standard deviation uses population std (statistics.pstdev).",
        }
        payload["diagnostics"] = _diagnostics(payload)
        _write_json(report_path, payload)
        return report_path

    runner = command_runner or _run_subprocess_command
    baseline_group = _run_group(
        validation_dir=validation_dir,
        group_name="baseline",
        source_dir=baseline_source_dir,
        repetitions=benchmark_repetitions,
        repo_root=repo_root,
        runner=runner,
    )
    final_group = _run_group(
        validation_dir=validation_dir,
        group_name="final",
        source_dir=final_source_dir,
        repetitions=benchmark_repetitions,
        repo_root=repo_root,
        runner=runner,
    )

    baseline_summary = baseline_group["summary"]
    final_summary = final_group["summary"]
    comparison = _comparison(baseline_summary, final_summary)
    payload = {
        "schema_version": "final_validation.v1",
        "enabled": True,
        "benchmark_repetitions": benchmark_repetitions,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "baseline": baseline_group,
        "final": final_group,
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
) -> dict[str, Any]:
    group_dir = validation_dir / group_name
    if group_dir.exists():
        shutil.rmtree(group_dir)
    source_cpp = group_dir / "cpp"
    build_dir = group_dir / "build"
    runs_dir = group_dir / "runs"
    logs_dir = group_dir / "logs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    try:
        _copy_source_tree(source_dir / "cpp", source_cpp)
        setup = _empty_setup()
        preflight_failure = _path_length_preflight(
            source_cpp=source_cpp,
            build_dir=build_dir,
            logs_dir=logs_dir,
            repo_root=repo_root,
        )
        if preflight_failure is not None:
            setup.update(preflight_failure)
        else:
            setup = _configure_and_build_group(
                group_dir=group_dir,
                source_cpp=source_cpp,
                build_dir=build_dir,
                logs_dir=logs_dir,
                repo_root=repo_root,
                runner=runner,
            )
    except Exception as exc:
        setup = _empty_setup()
        setup.update({
            "failed_step": "prepare_source",
            "error_message": str(exc),
        })

    if setup.get("failed_step"):
        return _group_payload(source_cpp, repo_root, setup, [])

    try:
        benchmark_executable = _find_executable(build_dir, FAMILY_BENCHMARK_TARGET)
    except OSError as exc:
        setup.update({
            "failed_step": "find_benchmark_executable",
            "error_message": str(exc),
        })
        return _group_payload(source_cpp, repo_root, setup, [])
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
    return _group_payload(source_cpp, repo_root, setup, runs)


def _configure_and_build_group(
    *,
    group_dir: Path,
    source_cpp: Path,
    build_dir: Path,
    logs_dir: Path,
    repo_root: Path,
    runner: CommandRunner,
) -> dict[str, Any]:
    setup = _empty_setup()
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
        setup.update({
            "failed_step": "environment",
            "error_message": "EIGEN3_INCLUDE_DIR is not set.",
        })
        return setup

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
    setup["configure_status"] = _stage_status(configure_stage)
    setup["configure_duration_seconds"] = _number_or_none(configure_stage.get("duration_seconds"))
    setup["configure_log_path"] = _display_path(logs_dir / "configure_cmake.log", repo_root)
    if configure_stage.get("exit_code") != 0:
        setup.update(_setup_failure("configure_cmake", configure_stage))
        return setup

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
    setup["build_status"] = _stage_status(build_stage)
    setup["build_duration_seconds"] = _number_or_none(build_stage.get("duration_seconds"))
    setup["build_log_path"] = _display_path(logs_dir / "build_absolute_pose_lambdatwist_benchmark.log", repo_root)
    if build_stage.get("exit_code") != 0:
        setup.update(_setup_failure("build_absolute_pose_lambdatwist_benchmark", build_stage))
        return setup
    return setup


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


def _empty_setup() -> dict[str, Any]:
    return {
        "configure_status": "not_run",
        "configure_duration_seconds": None,
        "configure_log_path": None,
        "build_status": "not_run",
        "build_duration_seconds": None,
        "build_log_path": None,
        "failed_step": None,
        "error_message": None,
    }


def _stage_status(stage: dict[str, Any]) -> str:
    return "success" if stage.get("exit_code") == 0 else "failed"


def _setup_failure(step: str, stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "failed_step": step,
        "error_message": _stage_error(stage),
    }


def _group_payload(
    source_cpp: Path,
    repo_root: Path,
    setup: dict[str, Any],
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = _summarize_runs(runs)
    summary["benchmark_runs_attempted"] = len(runs)
    return {
        "source_dir": _display_path(source_cpp, repo_root),
        "setup": setup,
        "runs": runs,
        "summary": summary,
    }


def _path_length_preflight(
    *,
    source_cpp: Path,
    build_dir: Path,
    logs_dir: Path,
    repo_root: Path,
) -> dict[str, Any] | None:
    critical_paths = _critical_validation_paths(source_cpp, build_dir, logs_dir)
    max_length = max((len(str(path)) for path in critical_paths), default=0)
    if platform.system() != "Windows" or max_length <= WINDOWS_FINAL_VALIDATION_PATH_LENGTH_THRESHOLD:
        return None
    message = (
        "Final validation path is too long for Windows/MinGW/CMake. "
        f"Maximum observed critical path length is {max_length}, safe threshold is "
        f"{WINDOWS_FINAL_VALIDATION_PATH_LENGTH_THRESHOLD}. Move the repository or results "
        "directory to a shorter path and rerun final validation."
    )
    diagnostics_path = logs_dir / "path_length_preflight.log"
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics_path.write_text(message + "\n", encoding="utf-8")
    return {
        "configure_status": "skipped",
        "configure_log_path": _display_path(diagnostics_path, repo_root),
        "build_status": "not_run",
        "failed_step": "path_length_preflight",
        "error_message": message,
    }


def _critical_validation_paths(source_cpp: Path, build_dir: Path, logs_dir: Path) -> list[Path]:
    paths = [
        source_cpp,
        build_dir,
        logs_dir / "configure_cmake.log",
        logs_dir / "build_absolute_pose_lambdatwist_benchmark.log",
    ]
    object_root = build_dir / "CMakeFiles" / f"{FAMILY_BENCHMARK_TARGET}.dir"
    if not source_cpp.is_dir():
        return paths
    for source_file in sorted(source_cpp.rglob("*")):
        if not source_file.is_file() or source_file.suffix.lower() not in SOURCE_FILE_SUFFIXES_FOR_PATH_PREFLIGHT:
            continue
        try:
            relative_source = source_file.relative_to(source_cpp)
        except ValueError:
            continue
        object_path = object_root / Path(str(relative_source) + ".obj")
        paths.extend([source_file, object_path, Path(str(object_path) + ".d")])
    return paths


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
    benchmark_run_status = "failed" if failed_step else "success"
    return {
        "run_index": run_index,
        "validation_run_id": validation_run_id,
        "validation_mode": "benchmark_only",
        "group": group_name,
        "group_dir": _display_path(group_dir, repo_root),
        "run_dir": _display_path(group_dir, repo_root),
        "benchmark_log_path": None if log_path is None else _display_path(log_path, repo_root),
        "benchmark_run_status": benchmark_run_status,
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
        "validation_mode": "benchmark_only",
        "group": group_name,
        "group_dir": _display_path(group_dir, repo_root),
        "run_dir": _display_path(group_dir, repo_root),
        "benchmark_log_path": _display_path(log_path, repo_root) if isinstance(log_path, Path) else None,
        "benchmark_run_status": "failed",
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
    setup_blocks = _group_setups(payload)
    failed_runs = [
        run for run in [*baseline_runs, *final_runs]
        if run.get("benchmark_run_status", run.get("verification_status")) != "success"
        or run.get("correctness_passed") is not True
    ]
    failed_steps = [
        str(run.get("failed_step"))
        for run in failed_runs
        if isinstance(run.get("failed_step"), str) and run.get("failed_step")
    ]
    failed_steps.extend(
        str(setup.get("failed_step"))
        for setup in setup_blocks
        if isinstance(setup.get("failed_step"), str) and setup.get("failed_step")
    )
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

    should_suggest_logs = status in {"incomplete", "completed_partial"} or bool(failed_steps)
    suggested_logs = []
    diagnostic_texts: list[str] = []
    observed_paths: list[str] = []
    for setup in setup_blocks:
        for key in ("configure_log_path", "build_log_path"):
            log_path = setup.get(key)
            if isinstance(log_path, str) and log_path:
                observed_paths.append(log_path)
                if should_suggest_logs and log_path not in suggested_logs and setup.get("failed_step"):
                    suggested_logs.append(log_path)
                diagnostic_texts.append(_read_text_if_available(log_path))
        if isinstance(setup.get("error_message"), str):
            diagnostic_texts.append(str(setup["error_message"]))
    runs_for_suggestions = failed_runs if should_suggest_logs else []
    for run in runs_for_suggestions:
        log_path = run.get("benchmark_log_path")
        if isinstance(log_path, str) and log_path and log_path not in suggested_logs:
            suggested_logs.append(log_path)
        if isinstance(log_path, str) and log_path:
            observed_paths.append(log_path)
            diagnostic_texts.append(_read_text_if_available(log_path))
        if isinstance(run.get("error_message"), str):
            diagnostic_texts.append(str(run["error_message"]))
        if len(suggested_logs) >= 4:
            break
    observed_paths.extend(_collect_path_strings(payload))
    combined_diagnostics = "\n".join(text for text in diagnostic_texts if text)
    observed_max = max((len(path) for path in observed_paths), default=0)
    diagnostic_max = _max_path_length_from_text(combined_diagnostics)

    return {
        "summary": summary,
        "dominant_failed_step": dominant_failed_step,
        "dominant_error_excerpt": _dominant_error_excerpt(combined_diagnostics),
        "path_length_warning_detected": _path_length_warning_detected(combined_diagnostics),
        "max_observed_path_length": max(observed_max, diagnostic_max or 0),
        "baseline_failed_runs": len([
            run for run in baseline_runs
            if run.get("benchmark_run_status", run.get("verification_status")) != "success"
            or run.get("correctness_passed") is not True
        ]),
        "final_failed_runs": len([
            run for run in final_runs
            if run.get("benchmark_run_status", run.get("verification_status")) != "success"
            or run.get("correctness_passed") is not True
        ]),
        "suggested_log_paths": suggested_logs,
    }


def _group_runs(payload: dict[str, Any], group_name: str) -> list[dict[str, Any]]:
    group = payload.get(group_name)
    if not isinstance(group, dict) or not isinstance(group.get("runs"), list):
        return []
    return [run for run in group["runs"] if isinstance(run, dict)]


def _group_setups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    setups: list[dict[str, Any]] = []
    for group_name in ("baseline", "final"):
        group = payload.get(group_name)
        if isinstance(group, dict) and isinstance(group.get("setup"), dict):
            setups.append(group["setup"])
    return setups


def _read_text_if_available(path_text: str) -> str:
    path = Path(path_text)
    if not path.is_file():
        path = Path.cwd() / path_text
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:12000]
    except OSError:
        return ""


def _dominant_error_excerpt(text: str) -> str | None:
    if not text:
        return None
    interesting = (
        "fatal error", "error:", "undefined reference", "cmake error", "mingw32-make",
        "ninja: build stopped", "path is too long", "maximum full path",
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lower = line.lower()
        if any(token in lower for token in interesting):
            return line[:500]
    return lines[0][:500] if lines else None


def _path_length_warning_detected(text: str) -> bool:
    lower = text.lower()
    return "maximum full path" in lower or "object file directory" in lower or "path is too long" in lower


def _max_path_length_from_text(text: str) -> int | None:
    import re

    matches = [
        int(match.group(1))
        for match in re.finditer(r"maximum observed critical path length is (\d+)", text, flags=re.IGNORECASE)
    ]
    return max(matches) if matches else None


def _collect_path_strings(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            paths.extend(_collect_path_strings(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_collect_path_strings(item))
    elif isinstance(value, str) and ("/" in value or "\\" in value):
        paths.append(value)
    return paths


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
        "benchmark_runs_attempted": len(runs),
        "median_runtime_ns_per_case": statistics.median(runtimes) if runtimes else None,
        "mean_runtime_ns_per_case": statistics.fmean(runtimes) if runtimes else None,
        "min_runtime_ns_per_case": min(runtimes) if runtimes else None,
        "max_runtime_ns_per_case": max(runtimes) if runtimes else None,
        "std_runtime_ns_per_case": statistics.pstdev(runtimes) if len(runtimes) > 1 else (0.0 if runtimes else None),
        "all_correctness_passed": None if not runs else all(run.get("correctness_passed") is True for run in runs),
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


def _empty_group(source_dir: Path, repo_root: Path) -> dict[str, Any]:
    return {
        "source_dir": _display_path(source_dir, repo_root),
        "setup": _empty_setup(),
        "runs": [],
        "summary": _summarize_runs([]),
    }


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
