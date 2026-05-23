"""Experiment launch wrapper for the interactive control layer."""

from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .baseline_launcher import build_baseline_environment
from .environment import load_environment
from .experiment_configs import read_experiment_config_summary
from .process_runner import ProcessLaunchError, ProcessResult, run_streaming_command
from .project_paths import get_project_paths, resolve_project_path


ExperimentRunStatus = Literal["success", "failed", "preflight_failed"]


@dataclass(frozen=True)
class ExperimentRunResult:
    status: ExperimentRunStatus
    exit_code: int | None
    command: list[str]
    message: str
    process_result: ProcessResult | None
    latest_experiment_dir: Path | None
    config_path: Path


PROVIDER_API_KEYS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def build_experiment_command(config_path: Path, dry_run: bool = False) -> list[str]:
    command = [
        sys.executable,
        "-u",
        "-m",
        "orchestrator.experiments.run_experiment",
        "--config",
        str(config_path),
    ]
    if dry_run:
        command.append("--dry-run")
    return command


def _snapshot_experiment_dirs(experiments_root: Path) -> set[Path]:
    if not experiments_root.is_dir():
        return set()
    return {path.resolve() for path in experiments_root.iterdir() if path.is_dir()}


def _latest_experiment_dir(experiments_root: Path, before: set[Path]) -> Path | None:
    if not experiments_root.is_dir():
        return None
    dirs = [path for path in experiments_root.iterdir() if path.is_dir()]
    if not dirs:
        return None
    new_dirs = [path for path in dirs if path.resolve() not in before]
    if not new_dirs:
        return None
    return max(new_dirs, key=lambda path: path.stat().st_mtime)


def _preflight_failure(config_path: Path, command: list[str], message: str) -> ExperimentRunResult:
    return ExperimentRunResult(
        status="preflight_failed",
        exit_code=None,
        command=command,
        message=message,
        process_result=None,
        latest_experiment_dir=None,
        config_path=config_path,
    )


def _missing_api_keys(providers: list[str], repo_root: Path) -> list[str]:
    env_statuses = {status.name: status for status in load_environment(repo_root)}
    missing: list[str] = []
    for provider in providers:
        api_key_name = PROVIDER_API_KEYS.get(provider.lower())
        if api_key_name is None:
            continue
        status = env_statuses.get(api_key_name)
        if status is None or status.status == "secret_missing":
            missing.append(api_key_name)
    return sorted(set(missing))


def run_experiment_control(
    config_path: Path,
    dry_run: bool = False,
    repo_root: Path | None = None,
    require_api_key: bool = True,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
    cancel_event: threading.Event | None = None,
    on_process_started: Callable[[subprocess.Popen], None] | None = None,
) -> ExperimentRunResult:
    paths = get_project_paths(repo_root)
    resolved_config = resolve_project_path(config_path, paths.repo_root)
    command = build_experiment_command(resolved_config, dry_run=dry_run)
    if not resolved_config.is_file():
        return _preflight_failure(
            resolved_config,
            command,
            f"Experiment config does not exist: {resolved_config}",
        )

    summary = read_experiment_config_summary(resolved_config)
    if summary.status == "invalid":
        return _preflight_failure(
            resolved_config,
            command,
            f"Experiment config is invalid: {summary.message}",
        )

    if require_api_key and not dry_run:
        missing_keys = _missing_api_keys(summary.providers, paths.repo_root)
        if missing_keys:
            return _preflight_failure(
                resolved_config,
                command,
                "Missing required API key(s): " + ", ".join(missing_keys),
            )

    before = _snapshot_experiment_dirs(paths.result_experiments)
    try:
        process_result = run_streaming_command(
            command,
            paths.repo_root,
            env=build_baseline_environment(paths.repo_root),
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            cancel_event=cancel_event,
            on_process_started=on_process_started,
        )
    except ProcessLaunchError as exc:
        return ExperimentRunResult(
            status="failed",
            exit_code=None,
            command=command,
            message=str(exc),
            process_result=None,
            latest_experiment_dir=_latest_experiment_dir(paths.result_experiments, before),
            config_path=resolved_config,
        )

    status: ExperimentRunStatus = "success" if process_result.exit_code == 0 else "failed"
    return ExperimentRunResult(
        status=status,
        exit_code=process_result.exit_code,
        command=command,
        message=(
            "Experiment completed successfully."
            if status == "success"
            else f"Experiment failed with exit code {process_result.exit_code}."
        ),
        process_result=process_result,
        latest_experiment_dir=_latest_experiment_dir(paths.result_experiments, before),
        config_path=resolved_config,
    )
