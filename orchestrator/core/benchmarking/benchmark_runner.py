"""Public CMake/build/run helpers for benchmark execution.

This module provides reusable functions for CMake configuration, target
building, executable discovery, and subprocess execution with log capture.
It is the single source of truth for these operations in both candidate
verification and final-selection reporting.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Any, Sequence

from orchestrator.shared.process.step_runner import format_command, StepRunner

_runner = StepRunner()


def write_step_log(
    log_path: Path,
    step: str,
    command: Sequence[str] | str,
    cwd: Path,
    exit_code: int | None,
    stdout: str,
    stderr: str,
) -> None:
    """Write a step execution log to *log_path*."""
    command_text = command if isinstance(command, str) else format_command(command)
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
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines), encoding="utf-8")


def run_command(
    step_name: str,
    title: str,
    command: Sequence[str],
    cwd: Path,
    log_path: Path,
) -> tuple[dict[str, Any], str | None, str]:
    """Run *command* in *cwd*, write a step log, and return (step_status, error, stdout).

    Returns:
        A tuple ``(step_status, error_message, stdout)`` where *error_message* is
        ``None`` when the command exits with code 0.
    """
    result = _runner.run_step(
        label=step_name,
        cmd=command,
        cwd=cwd,
        title=title,
        log_path=log_path,
    )

    return (
        {
            "name": step_name,
            "status": result.status,
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
        },
        result.error_message,
        result.stdout,
    )


def find_executable(build_dir: Path, executable_name: str) -> Path:
    """Locate the most recently modified executable matching *executable_name* under *build_dir*.

    On Windows, ``.exe`` is appended automatically for the primary search.
    """
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


def build_cmake_build_command(
    cmake_exe: str,
    build_dir: Path,
    target: str,
    cmake_build_type: str,
) -> list[str]:
    """Return the CMake ``--build`` command for a single target."""
    return [
        cmake_exe,
        "--build",
        str(build_dir),
        "--target",
        target,
        "--config",
        cmake_build_type,
    ]


def configure_cmake_command(
    source_dir: Path,
    build_dir: Path,
    eigen_include_dir: str,
    *,
    cmake_generator: str | None = None,
    cmake_cxx_compiler: str | None = None,
    cmake_make_program: str | None = None,
    cmake_build_type: str = "Release",
    cmake_exe: str = "cmake",
) -> list[str]:
    """Return the CMake configure command for a benchmarkable C++ source tree."""
    command: list[str] = [
        cmake_exe,
        "-S",
        str(source_dir),
        "-B",
        str(build_dir),
        f"-DEIGEN3_INCLUDE_DIR={eigen_include_dir}",
    ]
    if cmake_generator:
        command.extend(["-G", cmake_generator])
    if cmake_cxx_compiler:
        command.append(f"-DCMAKE_CXX_COMPILER={cmake_cxx_compiler}")
    if cmake_make_program:
        command.append(f"-DCMAKE_MAKE_PROGRAM={cmake_make_program}")
    command.append(f"-DCMAKE_BUILD_TYPE={cmake_build_type}")
    return command
