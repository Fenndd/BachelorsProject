"""Baseline launch wrapper for the interactive control layer."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .environment import EnvVarStatus, get_env_specs, load_environment
from .process_runner import ProcessLaunchError, ProcessResult, run_streaming_command
from .project_paths import get_project_paths


BaselineStatus = Literal["success", "failed", "preflight_failed"]


@dataclass(frozen=True)
class BaselineRunResult:
    status: BaselineStatus
    exit_code: int | None
    command: list[str]
    message: str
    process_result: ProcessResult | None
    latest_run_dir: Path | None
    environment_statuses: list[EnvVarStatus]


def build_baseline_command(solver_id: str | None = None) -> list[str]:
    command = [sys.executable, "-u", "-m", "orchestrator.cli.main"]
    if solver_id:
        command.extend(["--solver", solver_id])
    return command


def build_baseline_environment(repo_root: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    statuses = load_environment(repo_root)
    known_names = {spec.name for spec in get_env_specs()}
    for status in statuses:
        if status.name in known_names and status.value is not None and status.name not in os.environ:
            env[status.name] = status.value
    return env


def _status_by_name(statuses: list[EnvVarStatus]) -> dict[str, EnvVarStatus]:
    return {status.name: status for status in statuses}


def _snapshot_run_dirs(runs_root: Path) -> set[Path]:
    if not runs_root.is_dir():
        return set()
    return {path.resolve() for path in runs_root.iterdir() if path.is_dir()}


def _latest_run_dir(runs_root: Path, before: set[Path]) -> Path | None:
    if not runs_root.is_dir():
        return None
    dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    if not dirs:
        return None
    new_dirs = [path for path in dirs if path.resolve() not in before]
    candidates = new_dirs or dirs
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _preflight_failure(
    command: list[str],
    statuses: list[EnvVarStatus],
    message: str,
) -> BaselineRunResult:
    return BaselineRunResult(
        status="preflight_failed",
        exit_code=None,
        command=command,
        message=message,
        process_result=None,
        latest_run_dir=None,
        environment_statuses=statuses,
    )


def run_baseline(
    repo_root: Path | None = None,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
    solver_id: str | None = None,
) -> BaselineRunResult:
    paths = get_project_paths(repo_root)
    command = build_baseline_command(solver_id)
    statuses = load_environment(paths.repo_root)
    eigen_status = _status_by_name(statuses).get("EIGEN3_INCLUDE_DIR")

    if eigen_status is None or eigen_status.status == "missing":
        return _preflight_failure(
            command,
            statuses,
            "EIGEN3_INCLUDE_DIR is required before running the baseline.",
        )
    if eigen_status.status == "invalid":
        return _preflight_failure(command, statuses, eigen_status.message)

    before = _snapshot_run_dirs(paths.result_runs)
    env = build_baseline_environment(paths.repo_root)
    try:
        process_result = run_streaming_command(
            command,
            paths.repo_root,
            env=env,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
        )
    except ProcessLaunchError as exc:
        return BaselineRunResult(
            status="failed",
            exit_code=None,
            command=command,
            message=str(exc),
            process_result=None,
            latest_run_dir=_latest_run_dir(paths.result_runs, before),
            environment_statuses=statuses,
        )

    latest_run_dir = _latest_run_dir(paths.result_runs, before)
    status: BaselineStatus = "success" if process_result.exit_code == 0 else "failed"
    message = (
        "Baseline completed successfully."
        if status == "success"
        else f"Baseline failed with exit code {process_result.exit_code}."
    )
    return BaselineRunResult(
        status=status,
        exit_code=process_result.exit_code,
        command=command,
        message=message,
        process_result=process_result,
        latest_run_dir=latest_run_dir,
        environment_statuses=statuses,
    )
