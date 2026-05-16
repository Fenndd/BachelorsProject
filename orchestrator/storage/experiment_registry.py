"""Experiment result directory allocation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentRunAllocation:
    """Allocated experiment run identifier and result directory."""

    experiment_id: str
    experiment_dir: Path


def allocate_next_experiment_run(experiments_root: Path) -> ExperimentRunAllocation:
    """Allocate the next numeric experiment directory under ``experiments_root``."""

    experiments_root.mkdir(parents=True, exist_ok=True)
    existing_ids = [
        int(path.name)
        for path in experiments_root.iterdir()
        if path.is_dir() and path.name.isdigit()
    ]
    next_id = max(existing_ids, default=0) + 1

    while True:
        experiment_id = str(next_id)
        experiment_dir = experiments_root / experiment_id
        try:
            experiment_dir.mkdir(exist_ok=False)
            (experiment_dir / "logs").mkdir()
        except FileExistsError:
            next_id += 1
            continue
        return ExperimentRunAllocation(
            experiment_id=experiment_id,
            experiment_dir=experiment_dir,
        )


__all__ = ["ExperimentRunAllocation", "allocate_next_experiment_run"]
