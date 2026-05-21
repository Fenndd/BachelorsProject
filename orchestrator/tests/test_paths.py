"""Tests for the canonical :mod:`orchestrator.paths` module."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.paths import (
    ProjectPaths,
    find_repo_root,
    get_project_paths,
    paths,
    resolve_project_path,
)


def test_find_repo_root_returns_existing_directory() -> None:
    root = find_repo_root()

    assert root.exists()
    assert (root / "orchestrator").is_dir()


def test_find_repo_root_with_explicit_start() -> None:
    root = find_repo_root(start=Path.cwd())

    assert root.exists()
    assert (root / "orchestrator").is_dir()


def test_get_project_paths_returns_all_fields() -> None:
    p = get_project_paths()

    assert isinstance(p, ProjectPaths)
    assert p.repo_root.exists()
    assert p.configs == p.repo_root / "configs"
    assert p.results == p.repo_root / "results"
    assert p.workspace == p.repo_root / "workspace"
    assert p.cpp == p.repo_root / "cpp"
    assert p.orchestrator == p.repo_root / "orchestrator"
    assert p.experiments_config == p.configs / "experiments"
    assert p.result_runs == p.results / "runs"
    assert p.result_experiments == p.results / "experiments"


def test_module_level_paths_default() -> None:
    assert isinstance(paths, ProjectPaths)
    assert paths.repo_root.exists()


def test_resolve_project_path_relative() -> None:
    resolved = resolve_project_path("orchestrator")

    assert resolved.is_absolute()
    assert resolved.name == "orchestrator"


def test_resolve_project_path_absolute() -> None:
    resolved = resolve_project_path(Path.cwd())

    assert resolved.is_absolute()
    assert resolved == Path.cwd().resolve()


def test_resolve_project_path_with_explicit_root(tmp_path: Path) -> None:
    (tmp_path / "orchestrator").mkdir()
    (tmp_path / "configs").mkdir()
    (tmp_path / "cpp").mkdir()
    (tmp_path / ".git").mkdir()

    resolved = resolve_project_path("cpp", repo_root=tmp_path)
    assert resolved == (tmp_path / "cpp").resolve()


def test_project_paths_is_frozen() -> None:
    p = get_project_paths()

    with pytest.raises(Exception):
        p.repo_root = Path("/tmp")  # type: ignore[misc]


def test_paths_default_has_workspace() -> None:
    assert paths.workspace.name == "workspace"


def test_find_repo_root_falls_back_to_module_location() -> None:
    root = find_repo_root(Path("/nonexistent/directory/that/does/not/exist"))

    assert root.exists()
    assert (root / "orchestrator").is_dir()
