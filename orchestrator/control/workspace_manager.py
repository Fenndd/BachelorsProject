"""Workspace inspection and safe cleanup helpers for the control layer."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .project_paths import get_project_paths


@dataclass(frozen=True)
class WorkspaceStatus:
    path: Path
    exists: bool
    total_files: int
    total_dirs: int
    total_size_bytes: int
    candidate_workspaces: list[Path]
    experiment_workspaces: list[Path]
    other_entries: list[Path]


@dataclass(frozen=True)
class CleanupResult:
    kind: str
    deleted_paths_count: int
    deleted_files_count: int
    deleted_bytes_estimate: int
    deleted_paths: list[Path]
    errors: list[str]


def _safe_relative_to_workspace(path: Path, workspace: Path) -> bool:
    try:
        resolved = path.resolve()
        workspace_resolved = workspace.resolve()
        resolved.relative_to(workspace_resolved)
    except ValueError:
        return False
    return resolved != workspace_resolved


def _entry_size(path: Path) -> tuple[int, int]:
    if path.is_file():
        try:
            return 1, path.stat().st_size
        except OSError:
            return 1, 0
    files = 0
    size = 0
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_file():
                files += 1
                try:
                    size += child.stat().st_size
                except OSError:
                    pass
    return files, size


def _workspace_counts(workspace: Path) -> tuple[int, int, int]:
    files = 0
    dirs = 0
    size = 0
    if not workspace.is_dir():
        return 0, 0, 0
    for child in workspace.rglob("*"):
        if child.is_file():
            files += 1
            try:
                size += child.stat().st_size
            except OSError:
                pass
        elif child.is_dir():
            dirs += 1
    return files, dirs, size


def _children(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(path.iterdir())


def get_workspace_status(repo_root: Path | None = None) -> WorkspaceStatus:
    paths = get_project_paths(repo_root)
    workspace = paths.workspace
    total_files, total_dirs, total_size = _workspace_counts(workspace)
    candidate_root = workspace / "candidates"
    experiment_root = workspace / "experiments"
    candidate_workspaces = [path for path in _children(candidate_root) if path.is_dir()]
    experiment_workspaces = [path for path in _children(experiment_root) if path.is_dir()]
    known_entries = {candidate_root.resolve(), experiment_root.resolve()}
    other_entries: list[Path] = []
    for entry in _children(workspace):
        if entry.name == ".gitkeep":
            continue
        if entry.resolve() in known_entries:
            continue
        other_entries.append(entry)
    return WorkspaceStatus(
        path=workspace,
        exists=workspace.exists(),
        total_files=total_files,
        total_dirs=total_dirs,
        total_size_bytes=total_size,
        candidate_workspaces=candidate_workspaces,
        experiment_workspaces=experiment_workspaces,
        other_entries=other_entries,
    )


def _delete_entries(kind: str, workspace: Path, entries: list[Path]) -> CleanupResult:
    deleted_paths: list[Path] = []
    deleted_files = 0
    deleted_bytes = 0
    errors: list[str] = []
    for entry in entries:
        if entry.name == ".gitkeep":
            continue
        if not _safe_relative_to_workspace(entry, workspace):
            errors.append(f"Refusing to delete outside workspace: {entry}")
            continue
        files, size = _entry_size(entry)
        try:
            if entry.is_dir():
                shutil.rmtree(entry)
            elif entry.exists():
                entry.unlink()
        except OSError as exc:
            errors.append(f"{entry}: {exc}")
            continue
        deleted_paths.append(entry)
        deleted_files += files
        deleted_bytes += size
    return CleanupResult(
        kind=kind,
        deleted_paths_count=len(deleted_paths),
        deleted_files_count=deleted_files,
        deleted_bytes_estimate=deleted_bytes,
        deleted_paths=deleted_paths,
        errors=errors,
    )


def clean_workspace_candidates(repo_root: Path | None = None) -> CleanupResult:
    status = get_workspace_status(repo_root)
    return _delete_entries("candidates", status.path, status.candidate_workspaces)


def clean_workspace_experiments(repo_root: Path | None = None) -> CleanupResult:
    status = get_workspace_status(repo_root)
    return _delete_entries("experiments", status.path, status.experiment_workspaces)


def clean_workspace_all(repo_root: Path | None = None) -> CleanupResult:
    status = get_workspace_status(repo_root)
    entries = [
        *status.candidate_workspaces,
        *status.experiment_workspaces,
        *status.other_entries,
    ]
    return _delete_entries("all", status.path, entries)
