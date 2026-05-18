from __future__ import annotations

from pathlib import Path

from orchestrator.storage.experiment_registry import allocate_next_experiment_run


def test_allocate_next_experiment_run_creates_one_when_empty(tmp_path: Path) -> None:
    root = tmp_path / "results" / "experiments"

    allocation = allocate_next_experiment_run(root)

    assert allocation.experiment_id == "1"
    assert allocation.experiment_dir == root / "1"
    assert allocation.experiment_dir.is_dir()
    assert (allocation.experiment_dir / "logs").is_dir()


def test_allocate_next_experiment_run_creates_four_after_existing_ids(tmp_path: Path) -> None:
    root = tmp_path / "results" / "experiments"
    for experiment_id in ("1", "2", "3"):
        (root / experiment_id).mkdir(parents=True)

    allocation = allocate_next_experiment_run(root)

    assert allocation.experiment_id == "4"
    assert (root / "4" / "logs").is_dir()


def test_allocate_next_experiment_run_ignores_timestamp_directories(tmp_path: Path) -> None:
    root = tmp_path / "results" / "experiments"
    (root / "2026-05-16_15-16_basic_deepseek_flash").mkdir(parents=True)
    (root / "2").mkdir()

    allocation = allocate_next_experiment_run(root)

    assert allocation.experiment_id == "3"
    assert (root / "3" / "logs").is_dir()


def test_allocate_next_experiment_run_skips_race_collision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "results" / "experiments"
    (root / "1").mkdir(parents=True)
    original_mkdir = Path.mkdir

    def racing_mkdir(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self == root / "2":
            original_mkdir(self, parents=False, exist_ok=False)
            raise FileExistsError(str(self))
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", racing_mkdir)

    allocation = allocate_next_experiment_run(root)

    assert allocation.experiment_id == "3"
    assert (root / "2").is_dir()
    assert (root / "3" / "logs").is_dir()
