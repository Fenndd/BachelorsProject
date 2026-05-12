"""Basic project status helpers for the interactive control layer."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .project_paths import ProjectPaths, get_project_paths


@dataclass(frozen=True)
class ProjectStatus:
    repo_root: Path
    directories: dict[str, bool]
    git_available: bool
    git_branch: str | None
    dirty_worktree: bool | None


def _run_git(repo_root: Path, args: Sequence[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _directory_flags(paths: ProjectPaths) -> dict[str, bool]:
    return {
        "configs": paths.configs.is_dir(),
        "results": paths.results.is_dir(),
        "workspace": paths.workspace.is_dir(),
        "cpp": paths.cpp.is_dir(),
        "orchestrator": paths.orchestrator.is_dir(),
    }


def read_project_status(repo_root: Path | None = None) -> ProjectStatus:
    paths = get_project_paths(repo_root)
    branch = _run_git(paths.repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    status = _run_git(paths.repo_root, ["status", "--porcelain"])
    git_available = branch is not None or status is not None

    return ProjectStatus(
        repo_root=paths.repo_root,
        directories=_directory_flags(paths),
        git_available=git_available,
        git_branch=branch,
        dirty_worktree=None if status is None else bool(status),
    )
