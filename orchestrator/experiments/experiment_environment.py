"""Experiment-local environment, path, JSON, and source-tree helpers."""

from __future__ import annotations

import fnmatch
import json
import os
import platform
import shutil
import subprocess
from dataclasses import fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .closed_loop_state import (
    ClosedLoopPaths,
    CurrentBestState,
    to_plain_dict,
    write_current_best_state,
)
from .experiment_config import ExperimentConfig, ExperimentConfigError


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "results"
EXPERIMENTS_ROOT = RESULTS_ROOT / "experiments"
WORKSPACE_ROOT = REPO_ROOT / "workspace"


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _display_path(path: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass
    try:
        return (Path("workspace") / path.resolve().relative_to(WORKSPACE_ROOT)).as_posix()
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in: {path}")
    return payload


def _read_json_file_object(path: Path, label: str) -> dict[str, Any]:
    try:
        return _read_json_object(path)
    except json.JSONDecodeError as exc:
        raise ExperimentConfigError(f"{label} is not valid JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise ExperimentConfigError(f"Could not read {label}: {path}: {exc}") from exc
    except ValueError as exc:
        raise ExperimentConfigError(str(exc)) from exc


def _run_git_command(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _experiment_repository_info() -> dict[str, Any]:
    git_commit = _run_git_command(["rev-parse", "HEAD"])
    git_branch = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    git_status = _run_git_command(["status", "--porcelain"])
    return {
        "git_commit": git_commit or "unknown",
        "git_branch": git_branch or "unknown",
        "dirty_worktree": None if git_status is None else bool(git_status),
    }


def _experiment_environment_info() -> dict[str, Any]:
    return {
        "os": os.name,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cmake_build_type": os.environ.get("BENCHMARK_CMAKE_BUILD_TYPE") or os.environ.get("CMAKE_BUILD_TYPE") or "Release",
        "cmake_exe": os.environ.get("CMAKE_EXE"),
        "cmake_generator": os.environ.get("CMAKE_GENERATOR"),
        "cxx_compiler": os.environ.get("CMAKE_CXX_COMPILER"),
    }


def _write_experiment_metadata(
    experiment_dir: Path,
    started_at: datetime,
    finished_at: str | None = None,
) -> Path:
    total_duration: float | None = None
    if finished_at is not None:
        try:
            finished_dt = datetime.fromisoformat(finished_at)
            total_duration = round((finished_dt - started_at).total_seconds(), 3)
        except ValueError:
            total_duration = None
    payload = {
        "schema_version": "experiment_metadata.v1",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at,
        "total_duration_seconds": total_duration,
        "repository": _experiment_repository_info(),
        "environment": _experiment_environment_info(),
    }
    path = experiment_dir / "experiment_metadata.json"
    _write_json(path, _portable_plain_dict(payload))
    return path


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


SOURCE_TREE_IGNORE_NAMES = {"build", "CMakeFiles", "Testing", "CMakeCache.txt", "build.ninja"}
SOURCE_TREE_IGNORE_PATTERNS = {
    "build-*",
    "cmake-build-*",
    ".ninja_*",
    "*.exe",
    "*.obj",
    "*.o",
    "*.pdb",
    "*.ilk",
    "*.dll",
    "*.lib",
    "*.a",
}


def _source_tree_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in SOURCE_TREE_IGNORE_NAMES:
            ignored.add(name)
        elif any(fnmatch.fnmatch(name, pattern) for pattern in SOURCE_TREE_IGNORE_PATTERNS):
            ignored.add(name)
    return ignored


def _copy_source_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=_source_tree_ignore)


def _portable_plain_dict(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _portable_plain_dict(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Path):
        return _display_path(value)
    if isinstance(value, str):
        return _portable_path_string(value)
    if isinstance(value, list):
        return [_portable_plain_dict(item) for item in value]
    if isinstance(value, tuple):
        return [_portable_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _portable_plain_dict(item) for key, item in value.items()}
    return to_plain_dict(value)


def _portable_path_string(value: str) -> str:
    if not value:
        return value
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return value
    if not path.is_absolute():
        return value.replace("\\", "/")
    return _display_path(path)


def _ensure_path_inside(path: Path, root: Path, label: str) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise ValueError(f"Refusing unsafe {label} path outside {resolved_root}: {resolved_path}")


def initialize_current_best_source(paths: ClosedLoopPaths, config: ExperimentConfig) -> None:
    """Create current_best_source from the clean repository cpp tree."""

    current_best_source_dir = paths.current_best_source_dir
    _ensure_path_inside(current_best_source_dir, WORKSPACE_ROOT / "experiments", "current best source")
    if current_best_source_dir.exists():
        shutil.rmtree(current_best_source_dir)
    current_best_source_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        REPO_ROOT / "cpp",
        current_best_source_dir / "cpp",
        ignore=_source_tree_ignore,
    )
    target_path = current_best_source_dir / config.target_file
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"Current best source missing target file: {target_path}")


def _initialize_current_best_state(
    paths: ClosedLoopPaths,
    experiment_id: str,
    config: ExperimentConfig,
    baseline_run_dir: Path,
) -> CurrentBestState:
    baseline_metrics_path = baseline_run_dir / "metrics.json"
    return CurrentBestState(
        experiment_id=experiment_id,
        target_file=config.target_file,
        original_baseline_run_dir=baseline_run_dir,
        original_baseline_metrics_path=baseline_metrics_path,
        current_best_iteration=0,
        current_best_is_baseline=True,
        current_best_source_dir=paths.current_best_source_dir,
        current_best_run_dir=baseline_run_dir,
        current_best_metrics_path=baseline_metrics_path,
        accepted_improvements=0,
        updated_at=_now_iso(),
    )


def _write_current_best_state(paths: ClosedLoopPaths, state: CurrentBestState) -> None:
    state.updated_at = _now_iso()
    write_current_best_state(paths.current_best_state_path, state)


def update_current_best_source_from_workspace(
    paths: ClosedLoopPaths,
    workspace_path: Path,
    config: ExperimentConfig,
) -> None:
    workspace = workspace_path.resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise FileNotFoundError(f"Materialized workspace not found: {workspace}")
    current_best_source_dir = paths.current_best_source_dir
    _ensure_path_inside(current_best_source_dir, WORKSPACE_ROOT / "experiments", "current best source")
    if current_best_source_dir.exists():
        shutil.rmtree(current_best_source_dir)
    _copy_source_tree(workspace, current_best_source_dir)
    target_path = current_best_source_dir / config.target_file
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"Promoted current best source missing target file: {target_path}")
