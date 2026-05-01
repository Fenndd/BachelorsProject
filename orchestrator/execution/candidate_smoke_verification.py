"""Narrow Step 9 verifier for one materialized candidate smoke test.

This module is intentionally scoped to the first concrete Step 9 case:
configure the workspace C++ copy, build baseline_smoke_test, and run only that
smoke test. It is not the future general candidate execution pipeline.

The public CLI wrapper is orchestrator.execution.verify_candidate. Keeping this
implementation in a specifically named module makes the temporary narrow scope
visible when the broader verifier/executor is added later.

This verifier never modifies the main project source tree. It operates only on
the C++ project copied under workspace/candidates/<candidate_run_id>/cpp.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUILD_DIR_NAME = "build"

# Current narrow Step 9 scope. Future general verification should define its own
# step set instead of silently expanding this smoke-only command.
EXPECTED_STEPS = [
    "configure_cmake",
    "build_baseline_smoke_test",
    "run_baseline_smoke_test",
]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Narrow Step 9 verifier: configure, build, and run only "
            "baseline_smoke_test for one materialized candidate."
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


def _complete_steps(
    step_statuses: list[dict[str, Any]], failed_step: str | None
) -> list[dict[str, Any]]:
    completed = list(step_statuses)
    recorded_names = {step["name"] for step in completed}
    for step_name in EXPECTED_STEPS:
        if step_name not in recorded_names:
            completed.append(_skipped_step(step_name))
    if failed_step == "find_executable" and failed_step not in recorded_names:
        completed.append(_step_status("find_executable", "failed", None, None))
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
    if isinstance(command, str):
        command_text = command
    else:
        command_text = _format_command(command)

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
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except OSError as exc:
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
    )


def _find_smoke_test_executable(build_dir: Path) -> Path:
    executable_name = "baseline_smoke_test.exe" if platform.system() == "Windows" else "baseline_smoke_test"
    candidates = sorted(build_dir.rglob(executable_name))
    if not candidates and executable_name.endswith(".exe"):
        candidates = sorted(build_dir.rglob("baseline_smoke_test"))
    if not candidates:
        raise FileNotFoundError(
            "Could not find baseline_smoke_test executable under build directory: "
            f"{build_dir}"
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


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
    }


def _format_duration(duration_seconds: float | None) -> str:
    if duration_seconds is None:
        return "n/a"
    return f"{duration_seconds:.3f}s"


def _build_summary(
    verification: dict[str, Any],
    logs_dir: Path,
) -> str:
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
    for step in verification["steps"]:
        lines.append(
            f"- {step['name']}: {step['status']} "
            f"({_format_duration(step['duration_seconds'])})"
        )
    lines.extend(
        [
            "",
            f"Logs directory: {logs_dir}",
            "Benchmark and performance comparison are not implemented for candidates yet.",
            "",
        ]
    )
    return "\n".join(lines)


def _save_artifacts(
    candidate_run_dir: Path,
    verification: dict[str, Any],
    logs_dir: Path,
) -> None:
    _write_json(candidate_run_dir / "verification.json", verification)
    summary = _build_summary(verification, logs_dir)
    (candidate_run_dir / "verification_summary.txt").write_text(
        summary, encoding="utf-8"
    )


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
    steps = _complete_steps([], failed_step)
    verification = _build_verification(
        "failed",
        failed_step,
        error_message,
        candidate_run_id,
        workspace_path,
        source_dir,
        build_dir,
        eigen_include_dir,
        steps,
    )
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        _save_artifacts(candidate_run_dir, verification, logs_dir)
    except OSError as exc:
        print("Final status: failed")
        print("Failed step: save_artifacts")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Final status: failed")
    print(f"Failed step: {failed_step}")
    print(f"ERROR: {error_message}", file=sys.stderr)
    print(f"Logs saved to: {logs_dir}")
    print(f"Artifacts saved to: {candidate_run_dir}")
    return 1


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

    build_command = [
        args.cmake_exe,
        "--build",
        str(build_dir),
        "--target",
        "baseline_smoke_test",
        "--config",
        "Debug",
    ]

    step_statuses: list[dict[str, Any]] = []
    failed_step: str | None = None
    error_message: str | None = None

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
            build_command,
            workspace_path,
            logs_dir / "build_baseline_smoke_test.log",
        ),
    ]

    for step_name, title, command, cwd, log_path in command_steps:
        step_status, step_error = _run_command(step_name, title, command, cwd, log_path)
        step_statuses.append(step_status)
        if step_error:
            failed_step = step_name
            error_message = step_error
            break

    if failed_step is None:
        try:
            smoke_test_executable = _find_smoke_test_executable(build_dir)
        except OSError as exc:
            failed_step = "find_executable"
            error_message = str(exc)
            step_statuses.append(_step_status("find_executable", "failed", None, None))
            _write_step_log(
                logs_dir / "run_baseline_smoke_test.log",
                "find_executable",
                "find baseline_smoke_test executable",
                workspace_path,
                None,
                "",
                error_message,
            )
            print("\n[STEP] Find baseline_smoke_test executable")
            print(f"ERROR: {error_message}", file=sys.stderr)
        else:
            step_status, step_error = _run_command(
                "run_baseline_smoke_test",
                "Run baseline_smoke_test executable",
                [str(smoke_test_executable)],
                workspace_path,
                logs_dir / "run_baseline_smoke_test.log",
            )
            step_statuses.append(step_status)
            if step_error:
                failed_step = "run_baseline_smoke_test"
                error_message = step_error

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
        _complete_steps(step_statuses, failed_step),
    )

    try:
        _save_artifacts(candidate_run_dir, verification, logs_dir)
    except OSError as exc:
        verification = _build_verification(
            "failed",
            "save_artifacts",
            str(exc),
            candidate_run_id,
            workspace_path,
            source_dir,
            build_dir,
            eigen_include_dir,
            _complete_steps(step_statuses, "save_artifacts"),
        )
        print("Final status: failed")
        print("Failed step: save_artifacts")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"\nFinal status: {overall_status}")
    print(f"Artifacts saved to: {candidate_run_dir}")
    if failed_step:
        print(f"Failed step: {failed_step}")
        print(f"ERROR: {error_message}", file=sys.stderr)
        print(f"Logs saved to: {logs_dir}")
        return 1

    print("Candidate verification completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
