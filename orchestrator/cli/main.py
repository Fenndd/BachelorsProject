"""Minimal baseline automation entry point.

This script automates the current baseline flow:
1. CMake configure
2. CMake build (adapter validator and family benchmark targets)
3. Run the Lambda Twist P3P adapter validator executable
4. Run the Lambda Twist P3P family benchmark executable
5. Parse the family benchmark output into structured metrics

Each execution also writes persistent run artifacts under results/runs/<run_id>/.

On Windows outside CLion, CMake may need explicit toolchain environment
variables such as CMAKE_EXE, CMAKE_GENERATOR, CMAKE_CXX_COMPILER, and
CMAKE_MAKE_PROGRAM.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.core.benchmarking.benchmark_artifacts import (
    benchmark_artifact_from_parse,
    benchmark_required_fields,
    empty_benchmark_artifact,
)
from orchestrator.core.benchmarking.solver_registry import (
    SolverBenchmarkDescriptor,
    default_solver_descriptor,
)
from orchestrator.storage import RunStorage

DESCRIPTOR: SolverBenchmarkDescriptor = default_solver_descriptor()
_REQUIRED_FIELDS: list[str] = benchmark_required_fields()

EXPECTED_STEPS = [
    "configure_cmake",
    f"build_{DESCRIPTOR.adapter_validator_target}",
    f"build_{DESCRIPTOR.benchmark_target}",
    f"run_{DESCRIPTOR.adapter_validator_target}",
    f"run_{DESCRIPTOR.benchmark_target}",
    f"parse_{DESCRIPTOR.benchmark_target}",
    "benchmark_correctness_check",
]

PARSE_FAMILY_BENCHMARK_STEP = f"parse_{DESCRIPTOR.benchmark_target}"
BENCHMARK_CORRECTNESS_CHECK_STEP = "benchmark_correctness_check"


def _format_command(command: Sequence[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else str(part) for part in command)


def _run_git_command(repo_root: Path, args: Sequence[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _get_repository_info(repo_root: Path) -> dict[str, Any]:
    git_commit = _run_git_command(repo_root, ["rev-parse", "HEAD"])
    git_branch = _run_git_command(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    git_status = _run_git_command(repo_root, ["status", "--porcelain"])

    return {
        "git_commit": git_commit or "unknown",
        "git_branch": git_branch or "unknown",
        "dirty_worktree": None if git_status is None else bool(git_status),
    }


def _build_metadata(
    run_id: str,
    started_at: datetime,
    cmake_exe: str,
    cmake_generator: str | None,
    cmake_cxx_compiler: str | None,
    cmake_make_program: str | None,
    eigen_include_dir: str | None,
    cmake_build_type: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "scenario": "baseline",
        "case_study": "p3p_solver",
        "baseline": "lambda_twist",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": None,
        "repository": _get_repository_info(REPO_ROOT),
        "environment": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "cmake_exe": cmake_exe,
            "cmake_generator": cmake_generator,
            "cmake_cxx_compiler": cmake_cxx_compiler,
            "cmake_make_program": cmake_make_program,
            "eigen3_include_dir": eigen_include_dir,
            "cmake_build_type": cmake_build_type,
        },
    }


def _run_step(
    storage: RunStorage,
    run_dir: Path,
    step_name: str,
    title: str,
    command: Sequence[str],
    cwd: Path,
) -> tuple[dict[str, Any], str | None, str]:
    print(f"\n[STEP] {title}")
    print(f"[CMD ] {_format_command(command)}")
    print(f"[CWD ] {cwd}")

    started = time.perf_counter()
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        duration_seconds = round(time.perf_counter() - started, 3)
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode
    except FileNotFoundError:
        duration_seconds = round(time.perf_counter() - started, 3)
        stdout = ""
        stderr = (
            f"Required command not found: '{command[0]}'. "
            "Make sure it is installed and available in PATH."
        )
        exit_code = None
        storage.save_log(run_dir, step_name, command, cwd, exit_code, stdout, stderr)
        return (
            {
                "name": step_name,
                "status": "failed",
                "exit_code": exit_code,
                "duration_seconds": duration_seconds,
            },
            stderr,
            stdout,
        )

    storage.save_log(run_dir, step_name, command, cwd, exit_code, stdout, stderr)

    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

    status = "success" if exit_code == 0 else "failed"
    error_message = None
    if exit_code != 0:
        error_message = f"Step failed with exit code {exit_code}: {_format_command(command)}"

    return (
        {
            "name": step_name,
            "status": status,
            "exit_code": exit_code,
            "duration_seconds": duration_seconds,
        },
        error_message,
        stdout,
    )


def _find_executable(build_dir: Path, executable_name: str) -> Path:
    candidates = sorted(build_dir.rglob(f"{executable_name}.exe"))
    if not candidates:
        candidates = sorted(build_dir.rglob(executable_name))

    if not candidates:
        raise RuntimeError(
            f"Could not find {executable_name} executable after build. "
            f"Checked under: {build_dir}"
        )

    return max(candidates, key=lambda path: path.stat().st_mtime)


def _skipped_step(step_name: str) -> dict[str, Any]:
    return {
        "name": step_name,
        "status": "skipped",
        "exit_code": None,
        "duration_seconds": None,
    }


def _complete_steps_with_skipped(
    step_statuses: list[dict[str, Any]], failed_step: str | None
) -> list[dict[str, Any]]:
    recorded_names = {step["name"] for step in step_statuses}
    if failed_step == "environment":
        return [_skipped_step(step_name) for step_name in EXPECTED_STEPS]

    completed = list(step_statuses)
    for step_name in EXPECTED_STEPS:
        if step_name not in recorded_names:
            completed.append(_skipped_step(step_name))
    return completed


def _build_status(
    step_statuses: list[dict[str, Any]],
    failed_step: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    return {
        "overall_status": "failed" if failed_step else "success",
        "failed_step": failed_step,
        "error_message": error_message,
        "steps": _complete_steps_with_skipped(step_statuses, failed_step),
    }


def _step_succeeded(step_statuses: list[dict[str, Any]], step_name: str) -> bool:
    return any(
        step["name"] == step_name and step["status"] == "success"
        for step in step_statuses
    )


def _empty_benchmark_parse_result(
    raw_output_available: bool,
    parse_errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "raw_output_available": raw_output_available,
        "parse_success": False,
        "missing_fields": list(_REQUIRED_FIELDS),
        "parse_errors": [] if parse_errors is None else parse_errors,
        "metrics": {},
    }


def _benchmark_parse_result_from_output(output: str) -> dict[str, Any]:
    parse_result = DESCRIPTOR.parser(output)
    return {
        "raw_output_available": True,
        "parse_success": parse_result["parse_success"],
        "missing_fields": parse_result["missing_fields"],
        "parse_errors": parse_result["parse_errors"],
        "metrics": parse_result["metrics"],
    }


def _build_parse_error_message(benchmark_parse_result: dict[str, Any]) -> str:
    return (
        "Could not parse family benchmark output. "
        f"Missing fields: {benchmark_parse_result['missing_fields']}; "
        f"parse errors: {benchmark_parse_result['parse_errors']}"
    )


def _correctness_error_message(benchmark_parse_result: dict[str, Any]) -> str:
    parsed_metrics = benchmark_parse_result["metrics"]
    return (
        "Family benchmark parsed successfully, but correctness_passed=false. "
        "The baseline is not usable for comparison. "
        f"gt_found_percent={parsed_metrics.get('gt_found_percent')!r}, "
        "valid_solutions_percent="
        f"{parsed_metrics.get('valid_solutions_percent')!r}, "
        "runtime_ns_per_problem_median="
        f"{parsed_metrics.get('runtime_ns_per_problem_median')!r}."
    )


def _run_benchmark_parse_step(
    storage: RunStorage,
    run_dir: Path,
    benchmark_stdout: str,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    print(f"\n[STEP] Parse {DESCRIPTOR.benchmark_target} output")
    input_log_path = run_dir / "logs" / f"run_{DESCRIPTOR.benchmark_target}.log"
    started = time.perf_counter()
    benchmark_parse_result = _benchmark_parse_result_from_output(benchmark_stdout)
    duration_seconds = round(time.perf_counter() - started, 3)

    parse_success = benchmark_parse_result["parse_success"]
    status = "success" if parse_success else "failed"
    step_status = {
        "name": PARSE_FAMILY_BENCHMARK_STEP,
        "status": status,
        "exit_code": None,
        "duration_seconds": duration_seconds,
    }
    error_message = None if parse_success else _build_parse_error_message(benchmark_parse_result)

    log_stdout = "\n".join(
        [
            f"input_log_path: {input_log_path}",
            f"raw_output_available: {benchmark_parse_result['raw_output_available']}",
            f"parse_success: {benchmark_parse_result['parse_success']}",
            f"missing_fields: {benchmark_parse_result['missing_fields']}",
            f"parse_errors: {benchmark_parse_result['parse_errors']}",
            "",
        ]
    )
    storage.save_log(
        run_dir,
        PARSE_FAMILY_BENCHMARK_STEP,
        f"parse stdout from {input_log_path}",
        REPO_ROOT,
        None,
        log_stdout,
        "" if error_message is None else error_message,
    )

    print(f"[PARSE] success={str(parse_success).lower()}")
    if benchmark_parse_result["missing_fields"]:
        print(f"[PARSE] missing fields: {benchmark_parse_result['missing_fields']}")
    if benchmark_parse_result["parse_errors"]:
        print(f"[PARSE] parse errors: {benchmark_parse_result['parse_errors']}")

    return step_status, benchmark_parse_result, error_message


def _run_benchmark_correctness_check_step(
    storage: RunStorage,
    run_dir: Path,
    benchmark_parse_result: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    print("\n[STEP] Check parsed benchmark correctness")
    started = time.perf_counter()
    correctness_passed = benchmark_parse_result["metrics"].get("correctness_passed")
    duration_seconds = round(time.perf_counter() - started, 3)
    passed = correctness_passed is True
    status = "success" if passed else "failed"
    error_message = None if passed else _correctness_error_message(
        benchmark_parse_result
    )
    step_status = {
        "name": BENCHMARK_CORRECTNESS_CHECK_STEP,
        "status": status,
        "exit_code": None,
        "duration_seconds": duration_seconds,
    }
    storage.save_log(
        run_dir,
        BENCHMARK_CORRECTNESS_CHECK_STEP,
        "check parsed correctness_passed metric",
        REPO_ROOT,
        None,
        "\n".join(
            [
                f"parse_success: {benchmark_parse_result['parse_success']}",
                f"correctness_passed: {correctness_passed}",
                f"status: {status}",
                "",
            ]
        ),
        "" if error_message is None else error_message,
    )
    print(f"[CHECK] correctness_passed={_format_metric_value(correctness_passed)}")
    return step_status, error_message


def _format_metric_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _build_metrics(
    step_statuses: list[dict[str, Any]],
    cmake_build_type: str,
    benchmark_parse_result: dict[str, Any],
) -> dict[str, Any]:
    build_success = all(
        _step_succeeded(step_statuses, step_name)
        for step_name in [
            "configure_cmake",
            f"build_{DESCRIPTOR.adapter_validator_target}",
            f"build_{DESCRIPTOR.benchmark_target}",
        ]
    )
    adapter_validation_success = _step_succeeded(
        step_statuses, f"run_{DESCRIPTOR.adapter_validator_target}"
    )
    family_benchmark_success = _step_succeeded(
        step_statuses, f"run_{DESCRIPTOR.benchmark_target}"
    )

    if benchmark_parse_result.get("raw_output_available") is not True:
        benchmark = empty_benchmark_artifact(
            DESCRIPTOR,
            raw_output_available=benchmark_parse_result.get("raw_output_available", False),
            build_type=cmake_build_type,
        )
    else:
        benchmark = benchmark_artifact_from_parse(benchmark_parse_result, DESCRIPTOR, cmake_build_type)

    return {
        "build_success": build_success,
        "adapter_validation_success": adapter_validation_success,
        "family_benchmark_success": family_benchmark_success,
        "benchmark_success": family_benchmark_success,
        "benchmark": benchmark,
        "correctness": {
            "adapter_validation_passed": adapter_validation_success,
        },
    }


def _format_duration(duration_seconds: float | None) -> str:
    if duration_seconds is None:
        return "n/a"
    return f"{duration_seconds:.3f}s"


def _build_summary(
    run_dir: Path,
    metadata: dict[str, Any],
    status: dict[str, Any],
    metrics: dict[str, Any],
    cmake_build_type: str,
) -> str:
    step_by_name = {step["name"]: step for step in status["steps"]}
    adapter_validation_status = step_by_name[
        f"run_{DESCRIPTOR.adapter_validator_target}"
    ]["status"]
    family_benchmark_status = step_by_name[
        f"run_{DESCRIPTOR.benchmark_target}"
    ]["status"]

    lines = [
        f"Run: {metadata['run_id']}",
        "Scenario: baseline",
        "Case study: p3p_solver",
        f"Baseline: {DESCRIPTOR.solver_id}",
        f"Overall status: {status['overall_status']}",
        f"Failed step: {status['failed_step'] or 'none'}",
        f"Error message: {status['error_message'] or 'none'}",
        f"Build type: {cmake_build_type}",
        f"Started at: {metadata['started_at']}",
        f"Finished at: {metadata['finished_at']}",
        "",
        "Steps:",
    ]

    for step in status["steps"]:
        lines.append(
            f"- {step['name']}: {step['status']} "
            f"({_format_duration(step['duration_seconds'])})"
        )

    benchmark = metrics["benchmark"]
    lines.extend(
        [
            "",
            f"Logs directory: {run_dir / 'logs'}",
            f"Adapter validation status: {adapter_validation_status}",
            f"Family benchmark status: {family_benchmark_status}",
            "Benchmark parse status: "
            f"{_format_metric_value(benchmark['parse_success'])}",
            f"Adapter validation log: logs/run_{DESCRIPTOR.adapter_validator_target}.log",
            f"Family benchmark raw output log: logs/run_{DESCRIPTOR.benchmark_target}.log",
            f"Family benchmark parse log: logs/parse_{DESCRIPTOR.benchmark_target}.log",
            "",
            "Family benchmark:",
            f"- solver: {_format_metric_value(benchmark['parsed_solver_name'])}",
            f"- problems: {_format_metric_value(benchmark['parsed_num_problems'])}",
            f"- solutions/problem: {_format_metric_value(benchmark['parsed_solutions_per_problem'])}",
            f"- valid solutions: {_format_metric_value(benchmark['parsed_valid_solutions_percent'])}%",
            f"- GT found: {_format_metric_value(benchmark['parsed_gt_found_percent'])}%",
            f"- correctness passed: {_format_metric_value(benchmark['parsed_correctness_passed'])}",
            "- median runtime total: "
            f"{_format_metric_value(benchmark['parsed_runtime_ns_total_median'])} ns",
            "- median runtime per problem: "
            f"{_format_metric_value(benchmark['parsed_runtime_ns_per_problem_median'])} ns",
            "",
        ]
    )
    if benchmark["missing_fields"]:
        lines.append(f"- missing fields: {', '.join(benchmark['missing_fields'])}")
    if benchmark["parse_errors"]:
        lines.append(f"- parse errors: {'; '.join(benchmark['parse_errors'])}")
    return "\n".join(lines)


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def _build_index_record(
    metadata: dict[str, Any],
    status: dict[str, Any],
    metrics: dict[str, Any],
    run_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    repository = metadata["repository"]
    benchmark = metrics["benchmark"]
    return {
        "run_id": metadata["run_id"],
        "scenario": metadata["scenario"],
        "case_study": metadata["case_study"],
        "baseline": metadata["baseline"],
        "overall_status": status["overall_status"],
        "failed_step": status["failed_step"],
        "started_at": metadata["started_at"],
        "finished_at": metadata["finished_at"],
        "git_commit": repository["git_commit"],
        "git_branch": repository["git_branch"],
        "dirty_worktree": repository["dirty_worktree"],
        "build_success": metrics["build_success"],
        "benchmark_success": metrics["benchmark_success"],
        "adapter_validation_success": metrics["adapter_validation_success"],
        "family_benchmark_success": metrics["family_benchmark_success"],
        "benchmark_raw_output_available": benchmark["raw_output_available"],
        "benchmark_runtime_ms": None,
        "family_benchmark_raw_output_available": benchmark["raw_output_available"],
        "family_benchmark_parse_success": benchmark["parse_success"],
        "family_benchmark_solver": benchmark["parsed_solver_name"],
        "family_benchmark_num_problems": benchmark["parsed_num_problems"],
        "family_benchmark_total_solutions": benchmark["parsed_total_solutions"],
        "family_benchmark_solutions_per_problem": benchmark[
            "parsed_solutions_per_problem"
        ],
        "family_benchmark_valid_solutions_percent": benchmark[
            "parsed_valid_solutions_percent"
        ],
        "family_benchmark_gt_found_percent": benchmark["parsed_gt_found_percent"],
        "family_benchmark_runtime_ns_total_median": benchmark[
            "parsed_runtime_ns_total_median"
        ],
        "family_benchmark_runtime_ns_per_problem_median": benchmark[
            "parsed_runtime_ns_per_problem_median"
        ],
        "family_benchmark_correctness_passed": benchmark["parsed_correctness_passed"],
        "run_dir": _display_path(run_dir, repo_root),
    }


def _write_final_artifacts(
    storage: RunStorage,
    run_dir: Path,
    metadata: dict[str, Any],
    step_statuses: list[dict[str, Any]],
    failed_step: str | None,
    error_message: str | None,
    cmake_build_type: str,
    benchmark_parse_result: dict[str, Any],
) -> dict[str, Any]:
    metadata["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    status = _build_status(step_statuses, failed_step, error_message)
    metrics = _build_metrics(step_statuses, cmake_build_type, benchmark_parse_result)
    summary = _build_summary(run_dir, metadata, status, metrics, cmake_build_type)

    storage.save_metadata(run_dir, metadata)
    storage.save_status(run_dir, status)
    storage.save_metrics(run_dir, metrics)
    storage.save_summary(run_dir, summary)
    index_record = _build_index_record(metadata, status, metrics, run_dir, REPO_ROOT)
    index_path = storage.append_index_record(index_record)
    print(f"[Index] Appended run record to {_display_path(index_path, REPO_ROOT)}")
    return status


def main() -> int:
    source_dir = REPO_ROOT / "cpp"
    build_dir = source_dir / "build"

    cmake_exe = os.environ.get("CMAKE_EXE", "cmake")
    cmake_generator = os.environ.get("CMAKE_GENERATOR")
    cmake_cxx_compiler = os.environ.get("CMAKE_CXX_COMPILER")
    cmake_make_program = os.environ.get("CMAKE_MAKE_PROGRAM")
    eigen_include_dir = os.environ.get("EIGEN3_INCLUDE_DIR")
    cmake_build_type = os.environ.get(
        "BENCHMARK_CMAKE_BUILD_TYPE",
        os.environ.get("CMAKE_BUILD_TYPE", "Release"),
    )

    storage = RunStorage(REPO_ROOT / "results")
    started_at = datetime.now().astimezone()
    run_id = storage.build_run_id("baseline", started_at)
    run_dir = storage.create_run_directory("baseline", run_id)
    print(f"[RUN ] Artifacts directory: {run_dir}")

    metadata = _build_metadata(
        run_id,
        started_at,
        cmake_exe,
        cmake_generator,
        cmake_cxx_compiler,
        cmake_make_program,
        eigen_include_dir,
        cmake_build_type,
    )
    storage.save_metadata(run_dir, metadata)

    step_statuses: list[dict[str, Any]] = []
    benchmark_parse_result = _empty_benchmark_parse_result(
        False, ["family benchmark was not executed"]
    )

    if not eigen_include_dir:
        error_message = (
            "EIGEN3_INCLUDE_DIR environment variable is not set. "
            "Set it to the Eigen include root directory containing Eigen/."
        )
        status = _write_final_artifacts(
            storage,
            run_dir,
            metadata,
            step_statuses,
            "environment",
            error_message,
            cmake_build_type,
            benchmark_parse_result,
        )
        print(f"ERROR: {error_message}")
        print('Example (PowerShell): $env:EIGEN3_INCLUDE_DIR="C:\\path\\to\\eigen"')
        print(f"[DONE] Final status: {status['overall_status']}")
        print(f"[RUN ] Artifacts saved to: {run_dir}")
        return 1

    configure_command = [
        cmake_exe,
        "-S",
        str(source_dir),
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

    command_steps: list[tuple[str, str, Sequence[str]]] = [
        ("configure_cmake", "Configure CMake project", configure_command),
        (
            f"build_{DESCRIPTOR.adapter_validator_target}",
            f"Build {DESCRIPTOR.adapter_validator_target} target",
            [
                cmake_exe,
                "--build",
                str(build_dir),
                "--target",
                DESCRIPTOR.adapter_validator_target,
                "--config",
                cmake_build_type,
            ],
        ),
        (
            f"build_{DESCRIPTOR.benchmark_target}",
            f"Build {DESCRIPTOR.benchmark_target} target",
            [
                cmake_exe,
                "--build",
                str(build_dir),
                "--target",
                DESCRIPTOR.benchmark_target,
                "--config",
                cmake_build_type,
            ],
        ),
    ]

    failed_step: str | None = None
    error_message: str | None = None

    for step_name, title, command in command_steps:
        step_status, step_error, _stdout = _run_step(
            storage, run_dir, step_name, title, command, REPO_ROOT
        )
        step_statuses.append(step_status)
        if step_error:
            failed_step = step_name
            error_message = step_error
            break

    run_targets = [
        (
            f"run_{DESCRIPTOR.adapter_validator_target}",
            f"Run {DESCRIPTOR.adapter_validator_target} executable",
            DESCRIPTOR.adapter_validator_target,
        ),
        (
            f"run_{DESCRIPTOR.benchmark_target}",
            f"Run {DESCRIPTOR.benchmark_target} executable",
            DESCRIPTOR.benchmark_target,
        ),
    ]

    if failed_step is None:
        benchmark_stdout = ""
        for step_name, title, executable_name in run_targets:
            try:
                executable = _find_executable(build_dir, executable_name)
            except RuntimeError as exc:
                failed_step = step_name
                error_message = str(exc)
                storage.save_log(
                    run_dir,
                    step_name,
                    f"find executable {executable_name}",
                    REPO_ROOT,
                    None,
                    "",
                    error_message,
                )
                step_statuses.append(
                    {
                        "name": step_name,
                        "status": "failed",
                        "exit_code": None,
                        "duration_seconds": None,
                    }
                )
                print(f"\n[STEP] {title}")
                print(f"ERROR: {error_message}", file=sys.stderr)
                break

            step_status, step_error, stdout = _run_step(
                storage, run_dir, step_name, title, [str(executable)], REPO_ROOT
            )
            step_statuses.append(step_status)
            if step_name == "run_absolute_pose_lambdatwist_benchmark":
                benchmark_stdout = stdout
                benchmark_parse_result = _empty_benchmark_parse_result(
                    True, ["family benchmark output was not parsed"]
                )
            if step_error:
                failed_step = step_name
                error_message = step_error
                break

        if failed_step is None:
            step_status, benchmark_parse_result, parse_error = _run_benchmark_parse_step(
                storage,
                run_dir,
                benchmark_stdout,
            )
            step_statuses.append(step_status)
            if parse_error:
                failed_step = PARSE_FAMILY_BENCHMARK_STEP
                error_message = parse_error
            else:
                step_status, correctness_error = _run_benchmark_correctness_check_step(
                    storage,
                    run_dir,
                    benchmark_parse_result,
                )
                step_statuses.append(step_status)
                if correctness_error:
                    failed_step = BENCHMARK_CORRECTNESS_CHECK_STEP
                    error_message = correctness_error

    status = _write_final_artifacts(
        storage,
        run_dir,
        metadata,
        step_statuses,
        failed_step,
        error_message,
        cmake_build_type,
        benchmark_parse_result,
    )
    print(f"\n[DONE] Final status: {status['overall_status']}")

    if failed_step:
        print(f"ERROR: {error_message}")
        print(f"[RUN ] Artifacts saved to: {run_dir}")
        return 1

    print("Baseline flow completed successfully.")
    print(f"[RUN ] Artifacts saved to: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
