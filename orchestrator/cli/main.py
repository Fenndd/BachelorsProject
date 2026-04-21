"""Minimal baseline automation entry point.

This script automates the current baseline flow:
1. CMake configure
2. CMake build (baseline_runner target)
3. Run baseline_runner executable
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


def _find_runner_executable(build_dir: Path) -> Path:
    candidates = sorted(build_dir.rglob("baseline_runner.exe"))
    if not candidates:
        candidates = sorted(build_dir.rglob("baseline_runner"))

    if not candidates:
        raise RuntimeError(
            "Could not find baseline_runner executable after build. "
            f"Checked under: {build_dir}"
        )

    return max(candidates, key=lambda path: path.stat().st_mtime)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    source_dir = repo_root / "cpp"
    build_dir = source_dir / "build"

    eigen_include_dir = os.environ.get("EIGEN3_INCLUDE_DIR")
    if not eigen_include_dir:
        print("ERROR: EIGEN3_INCLUDE_DIR environment variable is not set.")
        print("Set it to the Eigen include root (directory containing Eigen/).")
        print("Example (Windows cmd): set EIGEN3_INCLUDE_DIR=C:\\path\\to\\eigen")
        return 1

    try:
        _run_step(
            "Configure CMake project",
            [
                "cmake",
                "-S",
                str(source_dir),
                "-B",
                str(build_dir),
                f"-DEIGEN3_INCLUDE_DIR={eigen_include_dir}",
            ],
            cwd=repo_root,
        )

        _run_step(
            "Build baseline_runner target",
            [
                "cmake",
                "--build",
                str(build_dir),
                "--target",
                "baseline_runner",
                "--config",
                "Debug",
            ],
            cwd=repo_root,
        )

        runner_executable = _find_runner_executable(build_dir)
        _run_step(
            "Run baseline_runner executable",
            [str(runner_executable)],
            cwd=repo_root,
        )
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        return 1

    print("\nBaseline flow completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
