from __future__ import annotations

from pathlib import Path

from orchestrator.control.workspace_manager import (
    clean_workspace_all,
    clean_workspace_candidates,
    clean_workspace_experiments,
    get_workspace_status,
)


from orchestrator.tests.conftest import repo_root


def test_workspace_status_when_workspace_missing(tmp_path: Path) -> None:
    root = repo_root(tmp_path)

    status = get_workspace_status(root)

    assert status.exists is False
    assert status.total_files == 0
    assert status.total_dirs == 0
    assert status.total_size_bytes == 0


def test_workspace_status_counts_synthetic_files_and_dirs(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    workspace = root / "workspace"
    nested = workspace / "candidates" / "candidate_001"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("hello", encoding="utf-8")

    status = get_workspace_status(root)

    assert status.exists is True
    assert status.total_files == 1
    assert status.total_dirs >= 2
    assert status.total_size_bytes == 5
    assert status.candidate_workspaces == [nested]


def test_cleanup_candidates_deletes_only_candidate_workspaces(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    candidate = root / "workspace" / "candidates" / "candidate_001"
    experiment = root / "workspace" / "experiments" / "experiment_001"
    candidate.mkdir(parents=True)
    experiment.mkdir(parents=True)

    result = clean_workspace_candidates(root)

    assert result.deleted_paths_count == 1
    assert not candidate.exists()
    assert experiment.exists()


def test_cleanup_experiments_deletes_only_experiment_workspaces(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    candidate = root / "workspace" / "candidates" / "candidate_001"
    experiment = root / "workspace" / "experiments" / "experiment_001"
    candidate.mkdir(parents=True)
    experiment.mkdir(parents=True)

    result = clean_workspace_experiments(root)

    assert result.deleted_paths_count == 1
    assert candidate.exists()
    assert not experiment.exists()


def test_clean_all_deletes_only_inside_workspace_and_preserves_gitkeep(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    workspace = root / "workspace"
    candidate = workspace / "candidates" / "candidate_001"
    experiment = workspace / "experiments" / "experiment_001"
    other = workspace / "scratch"
    candidate.mkdir(parents=True)
    experiment.mkdir(parents=True)
    other.mkdir(parents=True)
    gitkeep = workspace / ".gitkeep"
    gitkeep.write_text("", encoding="utf-8")
    results = root / "results"
    results.mkdir(exist_ok=True)

    result = clean_workspace_all(root)

    assert result.deleted_paths_count == 3
    assert workspace.exists()
    assert gitkeep.exists()
    assert results.exists()
    assert not candidate.exists()
    assert not experiment.exists()
    assert not other.exists()


def test_cleanup_never_deletes_synthetic_results_directory(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    (root / "workspace" / "candidates" / "candidate_001").mkdir(parents=True)
    (root / "results" / "runs" / "run_001").mkdir(parents=True)

    clean_workspace_all(root)

    assert (root / "results" / "runs" / "run_001").exists()


def test_path_safety_reports_outside_workspace_entry(tmp_path: Path) -> None:
    root = repo_root(tmp_path)
    workspace = root / "workspace"
    workspace.mkdir()
    outside = root / "outside"
    outside.mkdir()

    # Exercise the guard by passing a crafted outside path through the private
    # deletion helper; public helpers only construct in-workspace paths.
    from orchestrator.control.workspace_manager import _delete_entries

    result = _delete_entries("test", workspace, [outside])

    assert result.deleted_paths_count == 0
    assert outside.exists()
    assert result.errors
