from __future__ import annotations

from orchestrator.control import get_project_paths, read_project_status
from orchestrator.control.project_paths import find_repo_root


def test_project_root_detection_returns_existing_path() -> None:
    root = find_repo_root()

    assert root.exists()
    assert (root / "orchestrator").is_dir()


def test_project_paths_resolve_expected_directories() -> None:
    paths = get_project_paths()

    assert paths.repo_root.exists()
    assert paths.configs == paths.repo_root / "configs"
    assert paths.results == paths.repo_root / "results"
    assert paths.workspace == paths.repo_root / "workspace"
    assert paths.cpp == paths.repo_root / "cpp"
    assert paths.orchestrator == paths.repo_root / "orchestrator"
    assert paths.experiments_config == paths.configs / "experiments"
    assert paths.result_runs == paths.results / "runs"
    assert paths.result_experiments == paths.results / "experiments"


def test_project_status_reads_without_requiring_git() -> None:
    status = read_project_status()

    assert status.repo_root.exists()
    assert set(status.directories) == {
        "configs",
        "results",
        "workspace",
        "cpp",
        "orchestrator",
    }
    assert isinstance(status.git_available, bool)
