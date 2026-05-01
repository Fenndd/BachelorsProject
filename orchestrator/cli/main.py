"""Minimal baseline automation entry point.

This script automates the current baseline flow:
1. CMake configure
2. CMake build (baseline_smoke_test, baseline_runner, and baseline_benchmark targets)
3. Run baseline_smoke_test executable
4. Run baseline_runner executable
5. Run baseline_benchmark executable

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

from orchestrator.storage import RunStorage


EXPECTED_STEPS = [
    "configure_cmake",
    "build_baseline_smoke_test",
    "build_baseline_runner",
    "build_baseline_benchmark",
    "run_baseline_smoke_test",
    "run_baseline_runner",
    "run_baseline_benchmark",
]


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
        },
    }


def _run_step(
    storage: RunStorage,
    run_dir: Path,
    step_name: str,
    title: str,
    command: Sequence[str],
    cwd: Path,
) -> tuple[dict[str, Any], str | None]:
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


def _step_executed(step_statuses: list[dict[str, Any]], step_name: str) -> bool:
    return any(
        step["name"] == step_name
        and step["status"] in {"success", "failed"}
        and step["exit_code"] is not None
        for step in step_statuses
    )


def _build_metrics(step_statuses: list[dict[str, Any]]) -> dict[str, Any]:
    build_success = all(
        _step_succeeded(step_statuses, step_name)
        for step_name in [
            "configure_cmake",
            "build_baseline_smoke_test",
            "build_baseline_runner",
            "build_baseline_benchmark",
        ]
    )
    smoke_test_success = _step_succeeded(step_statuses, "run_baseline_smoke_test")
    runner_success = _step_succeeded(step_statuses, "run_baseline_runner")
    benchmark_success = _step_succeeded(step_statuses, "run_baseline_benchmark")

    return {
        "build_success": build_success,
        "smoke_test_success": smoke_test_success,
        "runner_success": runner_success,
        "benchmark_success": benchmark_success,
        "benchmark": {
            "raw_output_available": _step_executed(
                step_statuses, "run_baseline_benchmark"
            ),
            "parsed_runtime_ms": None,
        },
        "correctness": {
            "basic_smoke_test_passed": smoke_test_success,
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
) -> str:
    lines = [
        f"Run: {metadata['run_id']}",
        "Scenario: baseline",
        "Case study: p3p_solver",
        "Baseline: lambda_twist",
        f"Overall status: {status['overall_status']}",
        f"Failed step: {status['failed_step'] or 'none'}",
        f"Error message: {status['error_message'] or 'none'}",
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

    lines.extend(
        [
            "",
            f"Logs directory: {run_dir / 'logs'}",
            "Benchmark parsed runtime is not available yet.",
            "",
        ]
    )
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
        "smoke_test_success": metrics["smoke_test_success"],
        "runner_success": metrics["runner_success"],
        "benchmark_success": metrics["benchmark_success"],
        "benchmark_raw_output_available": benchmark["raw_output_available"],
        "benchmark_runtime_ms": benchmark["parsed_runtime_ms"],
        "run_dir": _display_path(run_dir, repo_root),
    }


def _write_final_artifacts(
    storage: RunStorage,
    run_dir: Path,
    metadata: dict[str, Any],
    step_statuses: list[dict[str, Any]],
    failed_step: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    metadata["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    status = _build_status(step_statuses, failed_step, error_message)
    metrics = _build_metrics(step_statuses)
    summary = _build_summary(run_dir, metadata, status)

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
    )
    storage.save_metadata(run_dir, metadata)

    step_statuses: list[dict[str, Any]] = []

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

    command_steps: list[tuple[str, str, Sequence[str]]] = [
        ("configure_cmake", "Configure CMake project", configure_command),
        (
            "build_baseline_smoke_test",
            "Build baseline_smoke_test target",
            [
                cmake_exe,
                "--build",
                str(build_dir),
                "--target",
                "baseline_smoke_test",
                "--config",
                "Debug",
            ],
        ),
        (
            "build_baseline_runner",
            "Build baseline_runner target",
            [
                cmake_exe,
                "--build",
                str(build_dir),
                "--target",
                "baseline_runner",
                "--config",
                "Debug",
            ],
        ),
        (
            "build_baseline_benchmark",
            "Build baseline_benchmark target",
            [
                cmake_exe,
                "--build",
                str(build_dir),
                "--target",
                "baseline_benchmark",
                "--config",
                "Debug",
            ],
        ),
    ]

    failed_step: str | None = None
    error_message: str | None = None

    for step_name, title, command in command_steps:
        step_status, step_error = _run_step(
            storage, run_dir, step_name, title, command, REPO_ROOT
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
        ),
        ("run_baseline_runner", "Run baseline_runner executable", "baseline_runner"),
        (
            "run_baseline_benchmark",
            "Run baseline_benchmark executable",
            "baseline_benchmark",
        ),
    ]

    if failed_step is None:
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

            step_status, step_error = _run_step(
                storage, run_dir, step_name, title, [str(executable)], REPO_ROOT
            )
            step_statuses.append(step_status)
            if step_error:
                failed_step = step_name
                error_message = step_error
                break

    status = _write_final_artifacts(
        storage, run_dir, metadata, step_statuses, failed_step, error_message
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
