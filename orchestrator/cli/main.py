"""Minimal baseline automation entry point.

This script automates the current baseline flow:
1. CMake configure
2. CMake build (baseline_smoke_test, baseline_runner, and baseline_benchmark targets)
3. Run baseline_smoke_test executable
4. Run baseline_runner executable
5. Run baseline_benchmark executable

On Windows outside CLion, CMake may need explicit toolchain environment
variables such as CMAKE_EXE, CMAKE_GENERATOR, CMAKE_CXX_COMPILER, and
CMAKE_MAKE_PROGRAM.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def _format_command(command: List[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def _run_step(title: str, command: List[str], cwd: Optional[Path] = None) -> None:
    print(f"\n[STEP] {title}")
    print(f"[CMD ] {_format_command(command)}")
    if cwd is not None:
        print(f"[CWD ] {cwd}")

    try:
        result = subprocess.run(command, cwd=str(cwd) if cwd else None)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Required command not found: '{command[0]}'. "
            "Make sure it is installed and available in PATH."
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"Step failed with exit code {result.returncode}: {_format_command(command)}"
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


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    source_dir = repo_root / "cpp"
    build_dir = source_dir / "build"

    cmake_exe = os.environ.get("CMAKE_EXE", "cmake")
    cmake_generator = os.environ.get("CMAKE_GENERATOR")
    cmake_cxx_compiler = os.environ.get("CMAKE_CXX_COMPILER")
    cmake_make_program = os.environ.get("CMAKE_MAKE_PROGRAM")
    eigen_include_dir = os.environ.get("EIGEN3_INCLUDE_DIR")

    if not eigen_include_dir:
        print("ERROR: EIGEN3_INCLUDE_DIR environment variable is not set.")
        print("Set it to the Eigen include root (directory containing Eigen/).")
        print('Example (PowerShell): $env:EIGEN3_INCLUDE_DIR="C:\\path\\to\\eigen"')
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

    try:
        _run_step(
            "Configure CMake project",
            configure_command,
            cwd=repo_root,
        )

        _run_step(
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
            cwd=repo_root,
        )

        _run_step(
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
            cwd=repo_root,
        )

        _run_step(
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
            cwd=repo_root,
        )

        smoke_test_executable = _find_executable(build_dir, "baseline_smoke_test")
        _run_step(
            "Run baseline_smoke_test executable",
            [str(smoke_test_executable)],
            cwd=repo_root,
        )

        runner_executable = _find_executable(build_dir, "baseline_runner")
        _run_step(
            "Run baseline_runner executable",
            [str(runner_executable)],
            cwd=repo_root,
        )

        benchmark_executable = _find_executable(build_dir, "baseline_benchmark")
        _run_step(
            "Run baseline_benchmark executable",
            [str(benchmark_executable)],
            cwd=repo_root,
        )
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        return 1

    print("\nBaseline flow completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
