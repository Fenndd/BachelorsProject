"""Benchmark-family verifier for one materialized candidate workspace.

This verifier never calls an LLM and never modifies the main project source
tree. It operates only on the isolated workspace recorded in a candidate run's
materialization.json.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from orchestrator.benchmarking import parse_absolute_pose_benchmark_output


DEFAULT_BUILD_DIR_NAME = "build"
ADAPTER_VALIDATOR_TARGET = "absolute_pose_lambdatwist_adapter_validator"
FAMILY_BENCHMARK_TARGET = "absolute_pose_lambdatwist_benchmark"

EXPECTED_STEPS = [
    "configure_cmake",
    "build_baseline_smoke_test",
    "build_absolute_pose_lambdatwist_adapter_validator",
    "build_absolute_pose_lambdatwist_benchmark",
    "run_baseline_smoke_test",
    "run_absolute_pose_lambdatwist_adapter_validator",
    "run_absolute_pose_lambdatwist_benchmark",
    "parse_absolute_pose_lambdatwist_benchmark",
]

BENCHMARK_REQUIRED_FIELDS = [
    "solver_name",
    "num_cases",
    "success_rate",
    "mean_best_reprojection_error",
    "max_best_reprojection_error",
    "runtime_ns_total_median",
    "runtime_ns_per_case_median",
    "correctness_passed",
]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one materialized candidate with the absolute-pose benchmark "
            "family path."
        )
    )
    parser.add_argument(
        "--candidate-run",
        required=True,
        help="Path to a candidate run directory containing materialization.json.",
    )
    parser.add_argument(
        "--cmake-exe",
        default=os.environ.get("CMAKE_EXE", "cmake"),
        help="cmake executable to use.",
    )
    parser.add_argument(
        "--cmake-generator",
        default=os.environ.get("CMAKE_GENERATOR"),
        help="Optional CMake generator.",
    )
    parser.add_argument(
        "--cmake-cxx-compiler",
        default=os.environ.get("CMAKE_CXX_COMPILER"),
        help="Optional C++ compiler path for CMake.",
    )
    parser.add_argument(
        "--cmake-make-program",
        default=os.environ.get("CMAKE_MAKE_PROGRAM"),
        help="Optional make program path for CMake.",
    )
    parser.add_argument(
        "--eigen-include-dir",
        default=os.environ.get("EIGEN3_INCLUDE_DIR"),
        help="Eigen include root containing Eigen/Core.",
    )
    parser.add_argument(
        "--build-dir-name",
        default=DEFAULT_BUILD_DIR_NAME,
        help="Build directory name inside the candidate cpp directory.",
    )
    return parser.parse_args(argv)


def _resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _format_command(command: Sequence[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def _format_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _step_status(
    name: str,
    status: str,
    exit_code: int | None,
    duration_seconds: float | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
    }


def _skipped_step(name: str) -> dict[str, Any]:
    return _step_status(name, "skipped", None, None)


def _complete_steps(step_statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = list(step_statuses)
    recorded_names = {step["name"] for step in completed}
    for step_name in EXPECTED_STEPS:
        if step_name not in recorded_names:
            completed.append(_skipped_step(step_name))
    return completed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_step_log(
    log_path: Path,
    step: str,
    command: Sequence[str] | str,
    cwd: Path,
    exit_code: int | None,
    stdout: str,
    stderr: str,
) -> None:
    command_text = command if isinstance(command, str) else _format_command(command)
    lines = [
        f"STEP: {step}",
        f"COMMAND: {command_text}",
        f"CWD: {cwd}",
        f"EXIT_CODE: {exit_code}",
        "",
        "STDOUT:",
        stdout,
        "",
        "STDERR:",
        stderr,
        "",
    ]
    log_path.write_text("\n".join(lines), encoding="utf-8")


def _run_command(
    step_name: str,
    title: str,
    command: Sequence[str],
    cwd: Path,
    log_path: Path,
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
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except (OSError, ValueError) as exc:
        duration_seconds = round(time.perf_counter() - started, 3)
        exit_code = None
        stdout = ""
        if isinstance(exc, FileNotFoundError):
            stderr = (
                f"Required command not found: '{command[0]}'. "
                "Make sure it is installed and available in PATH."
            )
        else:
            stderr = f"Could not start command '{command[0]}': {exc}"

    _write_step_log(log_path, step_name, command, cwd, exit_code, stdout, stderr)

    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)

    status = "success" if exit_code == 0 else "failed"
    error_message = None
    if exit_code != 0:
        error_message = f"Step failed with exit code {exit_code}: {_format_command(command)}"

    return (
        _step_status(step_name, status, exit_code, duration_seconds),
        error_message,
        stdout,
    )


def _find_executable(build_dir: Path, executable_name: str) -> Path:
    platform_name = platform.system()
    expected_name = f"{executable_name}.exe" if platform_name == "Windows" else executable_name
    candidates = sorted(build_dir.rglob(expected_name))
    if not candidates and expected_name.endswith(".exe"):
        candidates = sorted(build_dir.rglob(executable_name))
    if not candidates:
        raise FileNotFoundError(
            f"Could not find {executable_name} executable under build directory: {build_dir}"
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _empty_benchmark(raw_output_available: bool = False) -> dict[str, Any]:
    return {
        "family": "absolute_pose_solvers",
        "solver": "lambdatwist_p3p",
        "runtime_unit": "ns",
        "raw_output_available": raw_output_available,
        "parse_success": False,
        "missing_fields": list(BENCHMARK_REQUIRED_FIELDS),
        "parse_errors": [],
        "parsed_solver_name": None,
        "parsed_num_cases": None,
        "parsed_success_rate": None,
        "parsed_mean_best_reprojection_error": None,
        "parsed_max_best_reprojection_error": None,
        "parsed_runtime_ns_total_median": None,
        "parsed_runtime_ns_per_case_median": None,
        "parsed_correctness_passed": None,
    }


def _benchmark_from_parse(
    stdout: str,
    parse_result: dict[str, Any],
) -> dict[str, Any]:
    parsed_metrics = parse_result["metrics"]
    return {
        "family": "absolute_pose_solvers",
        "solver": "lambdatwist_p3p",
        "runtime_unit": "ns",
        "raw_output_available": True,
        "parse_success": parse_result["parse_success"],
        "missing_fields": parse_result["missing_fields"],
        "parse_errors": parse_result["parse_errors"],
        "parsed_solver_name": parsed_metrics.get("solver_name"),
        "parsed_num_cases": parsed_metrics.get("num_cases"),
        "parsed_success_rate": parsed_metrics.get("success_rate"),
        "parsed_mean_best_reprojection_error": parsed_metrics.get(
            "mean_best_reprojection_error"
        ),
        "parsed_max_best_reprojection_error": parsed_metrics.get(
            "max_best_reprojection_error"
        ),
        "parsed_runtime_ns_total_median": parsed_metrics.get(
            "runtime_ns_total_median"
        ),
        "parsed_runtime_ns_per_case_median": parsed_metrics.get(
            "runtime_ns_per_case_median"
        ),
        "parsed_correctness_passed": parsed_metrics.get("correctness_passed"),
    }


def _build_verification(
    overall_status: str,
    failed_step: str | None,
    error_message: str | None,
    candidate_run_id: str,
    workspace_path: Path | None,
    source_dir: Path | None,
    build_dir: Path | None,
    eigen_include_dir: Path | None,
    steps: list[dict[str, Any]],
    adapter_validation: dict[str, Any],
    benchmark: dict[str, Any],
) -> dict[str, Any]:
    return {
        "overall_status": overall_status,
        "failed_step": failed_step,
        "error_message": error_message,
        "candidate_run_id": candidate_run_id,
        "workspace_path": None if workspace_path is None else _display_path(workspace_path),
        "source_dir": None if source_dir is None else _display_path(source_dir),
        "build_dir": None if build_dir is None else _display_path(build_dir),
        "eigen_include_dir": None
        if eigen_include_dir is None
        else _display_path(eigen_include_dir),
        "steps": steps,
        "adapter_validation": adapter_validation,
        "benchmark": benchmark,
    }


def _step_success(steps: list[dict[str, Any]], step_name: str) -> bool:
    return any(step["name"] == step_name and step["status"] == "success" for step in steps)


def _format_duration(duration_seconds: float | None) -> str:
    if duration_seconds is None:
        return "n/a"
    return f"{duration_seconds:.3f}s"


def _build_summary(verification: dict[str, Any], logs_dir: Path) -> str:
    steps = verification["steps"]
    benchmark = verification["benchmark"]
    lines = [
        f"Candidate run id: {verification['candidate_run_id']}",
        f"Workspace path: {verification['workspace_path'] or 'unknown'}",
        f"Source dir: {verification['source_dir'] or 'unknown'}",
        f"Build dir: {verification['build_dir'] or 'unknown'}",
        f"Overall status: {verification['overall_status']}",
        f"Failed step: {verification['failed_step'] or 'none'}",
        f"Error message: {verification['error_message'] or 'none'}",
        "",
        "Steps:",
    ]
    for step in steps:
        lines.append(
            f"- {step['name']}: {step['status']} "
            f"({_format_duration(step['duration_seconds'])})"
        )

    lines.extend(
        [
            "",
            f"Logs directory: {logs_dir}",
            f"Smoke test status: {_status_for_step(steps, 'run_baseline_smoke_test')}",
            "Adapter validator status: "
            f"{_status_for_step(steps, 'run_absolute_pose_lambdatwist_adapter_validator')}",
            "Family benchmark status: "
            f"{_status_for_step(steps, 'run_absolute_pose_lambdatwist_benchmark')}",
            f"Benchmark parse status: {_format_value(benchmark['parse_success'])}",
            "",
            "Family benchmark:",
            f"- solver: {_format_value(benchmark['parsed_solver_name'])}",
            f"- cases: {_format_value(benchmark['parsed_num_cases'])}",
            f"- success rate: {_format_value(benchmark['parsed_success_rate'])}",
            f"- correctness passed: {_format_value(benchmark['parsed_correctness_passed'])}",
            "- mean best reprojection error: "
            f"{_format_value(benchmark['parsed_mean_best_reprojection_error'])}",
            "- max best reprojection error: "
            f"{_format_value(benchmark['parsed_max_best_reprojection_error'])}",
            "- median runtime total: "
            f"{_format_value(benchmark['parsed_runtime_ns_total_median'])} ns",
            "- median runtime per case: "
            f"{_format_value(benchmark['parsed_runtime_ns_per_case_median'])} ns",
        ]
    )
    if benchmark["missing_fields"]:
        lines.append(f"- missing fields: {', '.join(benchmark['missing_fields'])}")
    if benchmark["parse_errors"]:
        lines.append(f"- parse errors: {'; '.join(benchmark['parse_errors'])}")
    lines.append("")
    return "\n".join(lines)


def _status_for_step(steps: list[dict[str, Any]], step_name: str) -> str:
    for step in steps:
        if step["name"] == step_name:
            return str(step["status"])
    return "unknown"


def _save_artifacts(
    candidate_run_dir: Path,
    verification: dict[str, Any],
    logs_dir: Path,
) -> None:
    _write_json(candidate_run_dir / "verification.json", verification)
    (candidate_run_dir / "verification_summary.txt").write_text(
        _build_summary(verification, logs_dir),
        encoding="utf-8",
    )


def _finalize(
    candidate_run_dir: Path,
    candidate_run_id: str,
    workspace_path: Path | None,
    source_dir: Path | None,
    build_dir: Path | None,
    eigen_include_dir: Path | None,
    logs_dir: Path,
    step_statuses: list[dict[str, Any]],
    failed_step: str | None,
    error_message: str | None,
    benchmark: dict[str, Any],
) -> int:
    completed_steps = _complete_steps(step_statuses)
    adapter_validation = {
        "success": _step_success(
            completed_steps, "run_absolute_pose_lambdatwist_adapter_validator"
        ),
        "raw_output_available": (
            logs_dir / "run_absolute_pose_lambdatwist_adapter_validator.log"
        ).exists(),
    }
    overall_status = "failed" if failed_step else "success"
    verification = _build_verification(
        overall_status,
        failed_step,
        error_message,
        candidate_run_id,
        workspace_path,
        source_dir,
        build_dir,
        eigen_include_dir,
        completed_steps,
        adapter_validation,
        benchmark,
    )
    _save_artifacts(candidate_run_dir, verification, logs_dir)

    print(f"\nFinal status: {overall_status}")
    print(f"Artifacts saved to: {candidate_run_dir}")
    if failed_step:
        print(f"Failed step: {failed_step}")
        print(f"ERROR: {error_message}", file=sys.stderr)
        print(f"Logs saved to: {logs_dir}")
        return 1

    print("Candidate benchmark verification completed successfully.")
    return 0


def _fail_before_commands(
    candidate_run_dir: Path,
    candidate_run_id: str,
    workspace_path: Path | None,
    source_dir: Path | None,
    build_dir: Path | None,
    eigen_include_dir: Path | None,
    logs_dir: Path,
    failed_step: str,
    error_message: str,
) -> int:
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        return _finalize(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            source_dir,
            build_dir,
            eigen_include_dir,
            logs_dir,
            [],
            failed_step,
            error_message,
            _empty_benchmark(False),
        )
    except (OSError, ValueError) as exc:
        print("Final status: failed")
        print("Failed step: save_artifacts")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _build_command(
    cmake_exe: str,
    build_dir: Path,
    target: str,
) -> list[str]:
    return [
        cmake_exe,
        "--build",
        str(build_dir),
        "--target",
        target,
        "--config",
        "Debug",
    ]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    candidate_run_dir = _resolve_repo_path(args.candidate_run)
    candidate_run_id = candidate_run_dir.name
    materialization_path = candidate_run_dir / "materialization.json"
    logs_dir = candidate_run_dir / "verification_logs"

    workspace_path: Path | None = None
    source_dir: Path | None = None
    build_dir: Path | None = None
    eigen_include_dir: Path | None = None

    print(f"Candidate run id: {candidate_run_id}")

    try:
        if not candidate_run_dir.exists() or not candidate_run_dir.is_dir():
            raise FileNotFoundError(f"Candidate run directory not found: {candidate_run_dir}")
        if not materialization_path.exists():
            raise FileNotFoundError(f"materialization.json not found: {materialization_path}")

        materialization = json.loads(materialization_path.read_text(encoding="utf-8-sig"))
        if not isinstance(materialization, dict):
            raise ValueError("materialization.json must contain a JSON object.")
        if materialization.get("overall_status") != "success":
            raise ValueError(
                "Candidate materialization must be successful before verification; "
                f"got overall_status={materialization.get('overall_status')!r}."
            )

        workspace_path_text = materialization.get("workspace_path")
        if not isinstance(workspace_path_text, str) or not workspace_path_text.strip():
            raise ValueError("materialization.json is missing a valid workspace_path.")

        workspace_path = _resolve_repo_path(workspace_path_text)
        source_dir = workspace_path / "cpp"
        build_dir = source_dir / args.build_dir_name
        if not source_dir.exists() or not source_dir.is_dir():
            raise FileNotFoundError(f"Candidate source directory not found: {source_dir}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _fail_before_commands(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            source_dir,
            build_dir,
            eigen_include_dir,
            logs_dir,
            "read_materialization",
            str(exc),
        )

    try:
        if not args.eigen_include_dir:
            raise ValueError(
                "EIGEN3_INCLUDE_DIR is not set. Provide --eigen-include-dir or set "
                "the EIGEN3_INCLUDE_DIR environment variable."
            )
        eigen_include_dir = _resolve_repo_path(args.eigen_include_dir)
        eigen_core = eigen_include_dir / "Eigen" / "Core"
        if not eigen_core.exists():
            raise FileNotFoundError(
                f"Eigen include dir is invalid. Expected Eigen/Core at: {eigen_core}"
            )
        if not args.build_dir_name or any(
            separator in args.build_dir_name for separator in ("/", "\\")
        ):
            raise ValueError("--build-dir-name must be a simple directory name.")
    except (OSError, ValueError) as exc:
        return _fail_before_commands(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            source_dir,
            build_dir,
            eigen_include_dir,
            logs_dir,
            "environment",
            str(exc),
        )

    assert workspace_path is not None
    assert source_dir is not None
    assert build_dir is not None
    assert eigen_include_dir is not None

    print(f"Workspace path: {workspace_path}")
    print(f"Source dir: {source_dir}")
    print(f"Build dir: {build_dir}")

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        if build_dir.exists():
            if build_dir.parent != source_dir:
                raise ValueError(f"Refusing to remove unexpected build directory: {build_dir}")
            shutil.rmtree(build_dir)
    except OSError as exc:
        return _fail_before_commands(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            source_dir,
            build_dir,
            eigen_include_dir,
            logs_dir,
            "save_artifacts",
            str(exc),
        )

    configure_command = [
        args.cmake_exe,
        "-S",
        str(source_dir),
        "-B",
        str(build_dir),
        f"-DEIGEN3_INCLUDE_DIR={eigen_include_dir}",
    ]
    if args.cmake_generator:
        configure_command.extend(["-G", args.cmake_generator])
    if args.cmake_cxx_compiler:
        configure_command.append(f"-DCMAKE_CXX_COMPILER={args.cmake_cxx_compiler}")
    if args.cmake_make_program:
        configure_command.append(f"-DCMAKE_MAKE_PROGRAM={args.cmake_make_program}")

    step_statuses: list[dict[str, Any]] = []
    failed_step: str | None = None
    error_message: str | None = None
    benchmark = _empty_benchmark(False)

    command_steps: list[tuple[str, str, Sequence[str], Path, Path]] = [
        (
            "configure_cmake",
            "Configure candidate CMake project",
            configure_command,
            workspace_path,
            logs_dir / "configure_cmake.log",
        ),
        (
            "build_baseline_smoke_test",
            "Build baseline_smoke_test target",
            _build_command(args.cmake_exe, build_dir, "baseline_smoke_test"),
            workspace_path,
            logs_dir / "build_baseline_smoke_test.log",
        ),
        (
            "build_absolute_pose_lambdatwist_adapter_validator",
            f"Build {ADAPTER_VALIDATOR_TARGET} target",
            _build_command(args.cmake_exe, build_dir, ADAPTER_VALIDATOR_TARGET),
            workspace_path,
            logs_dir / "build_absolute_pose_lambdatwist_adapter_validator.log",
        ),
        (
            "build_absolute_pose_lambdatwist_benchmark",
            f"Build {FAMILY_BENCHMARK_TARGET} target",
            _build_command(args.cmake_exe, build_dir, FAMILY_BENCHMARK_TARGET),
            workspace_path,
            logs_dir / "build_absolute_pose_lambdatwist_benchmark.log",
        ),
    ]

    for step_name, title, command, cwd, log_path in command_steps:
        step_status, step_error, _stdout = _run_command(
            step_name, title, command, cwd, log_path
        )
        step_statuses.append(step_status)
        if step_error:
            failed_step = step_name
            error_message = step_error
            break

    run_targets = [
        (
            "run_baseline_smoke_test",
            "Run baseline_smoke_test executable",
            "baseline_smoke_test",
            logs_dir / "run_baseline_smoke_test.log",
        ),
        (
            "run_absolute_pose_lambdatwist_adapter_validator",
            f"Run {ADAPTER_VALIDATOR_TARGET} executable",
            ADAPTER_VALIDATOR_TARGET,
            logs_dir / "run_absolute_pose_lambdatwist_adapter_validator.log",
        ),
        (
            "run_absolute_pose_lambdatwist_benchmark",
            f"Run {FAMILY_BENCHMARK_TARGET} executable",
            FAMILY_BENCHMARK_TARGET,
            logs_dir / "run_absolute_pose_lambdatwist_benchmark.log",
        ),
    ]

    benchmark_stdout = ""
    if failed_step is None:
        for step_name, title, executable_name, log_path in run_targets:
            try:
                executable = _find_executable(build_dir, executable_name)
            except OSError as exc:
                failed_step = step_name
                error_message = str(exc)
                step_statuses.append(_step_status(step_name, "failed", None, None))
                _write_step_log(
                    log_path,
                    step_name,
                    f"find executable {executable_name}",
                    workspace_path,
                    None,
                    "",
                    error_message,
                )
                print(f"\n[STEP] {title}")
                print(f"ERROR: {error_message}", file=sys.stderr)
                break

            step_status, step_error, stdout = _run_command(
                step_name,
                title,
                [str(executable)],
                workspace_path,
                log_path,
            )
            step_statuses.append(step_status)
            if step_name == "run_absolute_pose_lambdatwist_benchmark":
                benchmark_stdout = stdout
                benchmark = _empty_benchmark(True)
            if step_error:
                failed_step = step_name
                error_message = step_error
                break

    if failed_step is None:
        parse_started = time.perf_counter()
        parse_result = parse_absolute_pose_benchmark_output(benchmark_stdout)
        parse_duration = round(time.perf_counter() - parse_started, 3)
        benchmark = _benchmark_from_parse(benchmark_stdout, parse_result)
        if parse_result["parse_success"]:
            step_statuses.append(
                _step_status(
                    "parse_absolute_pose_lambdatwist_benchmark",
                    "success",
                    None,
                    parse_duration,
                )
            )
        else:
            failed_step = "parse_absolute_pose_lambdatwist_benchmark"
            error_message = (
                "Could not parse family benchmark output. "
                f"Missing fields: {parse_result['missing_fields']}; "
                f"parse errors: {parse_result['parse_errors']}"
            )
            step_statuses.append(
                _step_status(
                    "parse_absolute_pose_lambdatwist_benchmark",
                    "failed",
                    None,
                    parse_duration,
                )
            )

    try:
        return _finalize(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            source_dir,
            build_dir,
            eigen_include_dir,
            logs_dir,
            step_statuses,
            failed_step,
            error_message,
            benchmark,
        )
    except OSError as exc:
        print("Final status: failed")
        print("Failed step: save_artifacts")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
