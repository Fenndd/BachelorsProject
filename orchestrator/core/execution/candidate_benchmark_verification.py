"""Benchmark-family verifier for one materialized candidate workspace.

This verifier never calls an LLM and never modifies the main project source
tree. It operates only on the isolated workspace recorded in a candidate run's
materialization.json.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from orchestrator.paths import paths

from orchestrator.core.benchmarking.benchmark_artifacts import (
    benchmark_artifact_from_parse,
    build_benchmark_correctness_error_message,
    empty_benchmark_artifact,
)
from orchestrator.core.benchmarking.benchmark_runner import (
    build_cmake_build_command,
    configure_cmake_command,
    find_executable,
    run_command,
    write_step_log,
)
from orchestrator.core.benchmarking.solver_registry import (
    SolverBenchmarkDescriptor,
    default_solver_descriptor,
)


DESCRIPTOR: SolverBenchmarkDescriptor = default_solver_descriptor()

DEFAULT_BUILD_DIR_NAME = "build"
PATH_LENGTH_WARNING_THRESHOLD = 240
SOURCE_FILE_SUFFIXES_FOR_PATH_DIAGNOSTICS = {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh"}

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
    parser.add_argument(
        "--cmake-build-type",
        default=os.environ.get(
            "BENCHMARK_CMAKE_BUILD_TYPE",
            os.environ.get("CMAKE_BUILD_TYPE", "Release"),
        ),
        help="CMake build type (Release, Debug, RelWithDebInfo, MinSizeRel).",
    )
    return parser.parse_args(argv)


def _resolve_repo_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = paths.repo_root / path
    return path.resolve()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(paths.repo_root).as_posix()
    except ValueError:
        return str(path)


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


def _build_verification(
    overall_status: str,
    failed_step: str | None,
    error_message: str | None,
    candidate_run_id: str,
    workspace_path: Path | None,
    source_dir: Path | None,
    build_dir: Path | None,
    eigen_include_dir: Path | None,
    cmake_build_type: str,
    steps: list[dict[str, Any]],
    adapter_validation: dict[str, Any],
    benchmark: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
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
        "cmake_build_type": cmake_build_type,
        "steps": steps,
        "adapter_validation": adapter_validation,
        "benchmark": benchmark,
        "diagnostics": diagnostics or {},
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
        f"Build type: {verification.get('cmake_build_type', 'Release')}",
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
    path_length = verification.get("diagnostics", {}).get("path_length")
    if isinstance(path_length, dict) and path_length.get("warning") is True:
        lines.extend([
            "",
            "Diagnostics:",
            f"- path length warning: {path_length.get('message') or 'warning'}",
        ])

    lines.extend(
        [
            "",
            f"Logs directory: {logs_dir}",
            "Adapter validator status: "
            f"{_status_for_step(steps, f'run_{DESCRIPTOR.adapter_validator_target}')}",
            "Family benchmark status: "
            f"{_status_for_step(steps, f'run_{DESCRIPTOR.benchmark_target}')}",
            f"Benchmark parse status: {_format_value(benchmark['parse_success'])}",
            "",
            "Family benchmark:",
            f"- solver: {_format_value(benchmark['parsed_solver_name'])}",
            f"- problems: {_format_value(benchmark['parsed_num_problems'])}",
            f"- solutions/problem: {_format_value(benchmark['parsed_solutions_per_problem'])}",
            f"- valid solutions: {_format_value(benchmark['parsed_valid_solutions_percent'])}%",
            f"- GT found: {_format_value(benchmark['parsed_gt_found_percent'])}%",
            f"- correctness passed: {_format_value(benchmark['parsed_correctness_passed'])}",
            "- median runtime total: "
            f"{_format_value(benchmark['parsed_runtime_ns_total_median'])} ns",
            "- median runtime per problem: "
            f"{_format_value(benchmark['parsed_runtime_ns_per_problem_median'])} ns",
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
    cmake_build_type: str,
    logs_dir: Path,
    step_statuses: list[dict[str, Any]],
    failed_step: str | None,
    error_message: str | None,
    benchmark: dict[str, Any],
    diagnostics: dict[str, Any] | None = None,
) -> int:
    completed_steps = _complete_steps(step_statuses)
    run_adapter_step = f"run_{DESCRIPTOR.adapter_validator_target}"
    adapter_validation = {
        "success": _step_success(completed_steps, run_adapter_step),
        "raw_output_available": (
            logs_dir / f"{run_adapter_step}.log"
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
        cmake_build_type,
        completed_steps,
        adapter_validation,
        benchmark,
        diagnostics,
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
    cmake_build_type: str,
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
            cmake_build_type,
            logs_dir,
            [],
            failed_step,
            error_message,
            empty_benchmark_artifact(DESCRIPTOR, build_type=cmake_build_type),
            None,
        )
    except (OSError, ValueError) as exc:
        print("Final status: failed")
        print("Failed step: save_artifacts")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _path_length_diagnostics(source_dir: Path | None, build_dir: Path | None) -> dict[str, Any]:
    if source_dir is None or build_dir is None:
        return {
            "path_length": {
                "max_observed_path_length": 0,
                "threshold": PATH_LENGTH_WARNING_THRESHOLD,
                "warning": False,
                "message": None,
            }
        }
    max_length = max((len(str(path)) for path in _critical_candidate_paths(source_dir, build_dir)), default=0)
    warning = max_length > PATH_LENGTH_WARNING_THRESHOLD
    return {
        "path_length": {
            "max_observed_path_length": max_length,
            "threshold": PATH_LENGTH_WARNING_THRESHOLD,
            "warning": warning,
            "message": (
                "Candidate verification paths may exceed Windows/MinGW/CMake path limits. "
                f"Maximum observed path length is {max_length}, threshold is {PATH_LENGTH_WARNING_THRESHOLD}."
                if warning
                else None
            ),
        }
    }


def _critical_candidate_paths(source_dir: Path, build_dir: Path) -> list[Path]:
    paths = [source_dir, build_dir]
    object_roots = [
        build_dir / "CMakeFiles" / f"{target}.dir"
        for target in (
            DESCRIPTOR.adapter_validator_target,
            DESCRIPTOR.benchmark_target,
        )
    ]
    if not source_dir.is_dir():
        return paths
    for source_file in sorted(source_dir.rglob("*")):
        if not source_file.is_file() or source_file.suffix.lower() not in SOURCE_FILE_SUFFIXES_FOR_PATH_DIAGNOSTICS:
            continue
        try:
            relative_source = source_file.relative_to(source_dir)
        except ValueError:
            continue
        paths.append(source_file)
        for object_root in object_roots:
            object_path = object_root / Path(str(relative_source) + ".obj")
            paths.extend([object_path, Path(str(object_path) + ".d")])
    return paths


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
            args.cmake_build_type,
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
            args.cmake_build_type,
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
            args.cmake_build_type,
            logs_dir,
            "save_artifacts",
            str(exc),
        )

    configure_command = configure_cmake_command(
        source_dir=source_dir,
        build_dir=build_dir,
        eigen_include_dir=str(eigen_include_dir),
        cmake_generator=args.cmake_generator,
        cmake_cxx_compiler=args.cmake_cxx_compiler,
        cmake_make_program=args.cmake_make_program,
        cmake_build_type=args.cmake_build_type,
        cmake_exe=args.cmake_exe,
    )

    step_statuses: list[dict[str, Any]] = []
    failed_step: str | None = None
    error_message: str | None = None
    benchmark = empty_benchmark_artifact(DESCRIPTOR, False, build_type=args.cmake_build_type)
    diagnostics = _path_length_diagnostics(source_dir, build_dir)

    assert DESCRIPTOR.adapter_validator_target is not None
    assert DESCRIPTOR.benchmark_target is not None

    command_steps: list[tuple[str, str, Sequence[str], Path, Path]] = [
        (
            "configure_cmake",
            "Configure candidate CMake project",
            configure_command,
            workspace_path,
            logs_dir / "configure_cmake.log",
        ),
        (
            f"build_{DESCRIPTOR.adapter_validator_target}",
            f"Build {DESCRIPTOR.adapter_validator_target} target",
            build_cmake_build_command(args.cmake_exe, build_dir, DESCRIPTOR.adapter_validator_target, args.cmake_build_type),
            workspace_path,
            logs_dir / f"build_{DESCRIPTOR.adapter_validator_target}.log",
        ),
        (
            f"build_{DESCRIPTOR.benchmark_target}",
            f"Build {DESCRIPTOR.benchmark_target} target",
            build_cmake_build_command(args.cmake_exe, build_dir, DESCRIPTOR.benchmark_target, args.cmake_build_type),
            workspace_path,
            logs_dir / f"build_{DESCRIPTOR.benchmark_target}.log",
        ),
    ]

    for step_name, title, command, cwd, log_path in command_steps:
        step_status, step_error, _stdout = run_command(
            step_name, title, command, cwd, log_path
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
            logs_dir / f"run_{DESCRIPTOR.adapter_validator_target}.log",
        ),
        (
            f"run_{DESCRIPTOR.benchmark_target}",
            f"Run {DESCRIPTOR.benchmark_target} executable",
            DESCRIPTOR.benchmark_target,
            logs_dir / f"run_{DESCRIPTOR.benchmark_target}.log",
        ),
    ]

    benchmark_stdout = ""
    if failed_step is None:
        for step_name, title, executable_name, log_path in run_targets:
            try:
                executable = find_executable(build_dir, executable_name)
            except OSError as exc:
                failed_step = step_name
                error_message = str(exc)
                step_statuses.append(_step_status(step_name, "failed", None, None))
                write_step_log(
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

            step_status, step_error, stdout = run_command(
                step_name,
                title,
                [str(executable)],
                workspace_path,
                log_path,
            )
            step_statuses.append(step_status)
            if step_name == f"run_{DESCRIPTOR.benchmark_target}":
                benchmark_stdout = stdout
                benchmark = empty_benchmark_artifact(DESCRIPTOR, True, build_type=args.cmake_build_type)
            if step_error:
                failed_step = step_name
                error_message = step_error
                break

    if failed_step is None:
        parse_started = time.perf_counter()
        parse_result = DESCRIPTOR.parser(benchmark_stdout)
        parse_duration = round(time.perf_counter() - parse_started, 3)
        benchmark = benchmark_artifact_from_parse(parse_result, DESCRIPTOR, args.cmake_build_type)
        if parse_result["parse_success"]:
            step_statuses.append(
                _step_status(
                    PARSE_FAMILY_BENCHMARK_STEP,
                    "success",
                    None,
                    parse_duration,
                )
            )
        else:
            failed_step = PARSE_FAMILY_BENCHMARK_STEP
            error_message = (
                "Could not parse family benchmark output. "
                f"Missing fields: {parse_result['missing_fields']}; "
                f"parse errors: {parse_result['parse_errors']}"
            )
            step_statuses.append(
                _step_status(
                    PARSE_FAMILY_BENCHMARK_STEP,
                    "failed",
                    None,
                    parse_duration,
                )
            )
        if parse_result["parse_success"]:
            correctness_started = time.perf_counter()
            correctness_passed = benchmark.get("parsed_correctness_passed") is True
            correctness_duration = round(time.perf_counter() - correctness_started, 3)
            if correctness_passed:
                step_statuses.append(
                    _step_status(
                        BENCHMARK_CORRECTNESS_CHECK_STEP,
                        "success",
                        None,
                        correctness_duration,
                    )
                )
            else:
                failed_step = BENCHMARK_CORRECTNESS_CHECK_STEP
                error_message = build_benchmark_correctness_error_message(benchmark)
                step_statuses.append(
                    _step_status(
                        BENCHMARK_CORRECTNESS_CHECK_STEP,
                        "failed",
                        None,
                        correctness_duration,
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
            args.cmake_build_type,
            logs_dir,
            step_statuses,
            failed_step,
            error_message,
            benchmark,
            diagnostics,
        )
    except OSError as exc:
        print("Final status: failed")
        print("Failed step: save_artifacts")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
