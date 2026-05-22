from __future__ import annotations

import pytest
from pathlib import Path

pytestmark = pytest.mark.unit

from orchestrator.storage.experiment_registry import allocate_next_experiment_run


def test_creates_experiments_root_if_missing(tmp_path: Path) -> None:
    root = tmp_path / "experiments"

    allocation = allocate_next_experiment_run(root)

    assert root.exists()
    assert root.is_dir()
    assert allocation.experiment_id == "1"


def test_allocates_id_1_when_empty(tmp_path: Path) -> None:
    root = tmp_path / "experiments"
    root.mkdir()

    allocation = allocate_next_experiment_run(root)

    assert allocation.experiment_id == "1"
    assert allocation.experiment_dir == root / "1"


def test_creates_experiment_dir_and_logs(tmp_path: Path) -> None:
    root = tmp_path / "experiments"

    allocation = allocate_next_experiment_run(root)

    assert allocation.experiment_dir.exists()
    assert (allocation.experiment_dir / "logs").exists()


def test_skips_existing_numeric_dirs(tmp_path: Path) -> None:
    root = tmp_path / "experiments"
    (root / "1").mkdir(parents=True)
    (root / "2").mkdir(parents=True)

    allocation = allocate_next_experiment_run(root)

    assert allocation.experiment_id == "3"


def test_ignores_non_numeric_dirs(tmp_path: Path) -> None:
    root = tmp_path / "experiments"
    (root / "1").mkdir(parents=True)
    (root / "not_a_number").mkdir(parents=True)
    (root / "logs").mkdir(parents=True)

    allocation = allocate_next_experiment_run(root)

    assert allocation.experiment_id == "2"
