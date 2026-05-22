"""Canonical project path discovery for both core and control code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXPECTED_PROJECT_DIRS = ("configs", "cpp", "orchestrator")


@dataclass(frozen=True)
class ProjectPaths:
    repo_root: Path
    configs: Path
    results: Path
    workspace: Path
    cpp: Path
    orchestrator: Path
    experiments_config: Path
    result_runs: Path
    result_experiments: Path


def _looks_like_repo_root(path: Path) -> bool:
    return all((path / name).is_dir() for name in EXPECTED_PROJECT_DIRS)


def _module_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def find_repo_root(start: Path | None = None) -> Path:
    """Find the repository root from a start path, with a module-based fallback."""
    current = Path.cwd() if start is None else Path(start)
    current = current.resolve()
    if current.is_file():
        current = current.parent

    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() or _looks_like_repo_root(candidate):
            return candidate

    return _module_repo_root()


def get_project_paths(repo_root: Path | None = None) -> ProjectPaths:
    root = find_repo_root(repo_root)
    results = root / "results"
    configs = root / "configs"
    return ProjectPaths(
        repo_root=root,
        configs=configs,
        results=results,
        workspace=root / "workspace",
        cpp=root / "cpp",
        orchestrator=root / "orchestrator",
        experiments_config=configs / "experiments",
        result_runs=results / "runs",
        result_experiments=results / "experiments",
    )


def resolve_project_path(path: str | Path, repo_root: Path | None = None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (find_repo_root(repo_root) / candidate).resolve()


paths = get_project_paths()
