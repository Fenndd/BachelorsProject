from __future__ import annotations

import os
from pathlib import Path

import pytest

from orchestrator.control.open_artifact import OpenArtifactError, open_path
from orchestrator.control.results_browser import (
    get_latest_result,
    list_result_items,
    resolve_result_selector,
)


def _repo_root(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def _write_run(root: Path, name: str, status: str = "success") -> Path:
    run_dir = root / "results" / "runs" / name
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(
        f'{{"overall_status": "{status}"}}\n',
        encoding="utf-8",
    )
    (run_dir / "metadata.json").write_text(
        '{"started_at": "2026-05-12T01:00:00+02:00", "finished_at": "2026-05-12T01:01:00+02:00"}\n',
        encoding="utf-8",
    )
    (run_dir / "summary.txt").write_text("Run summary\n", encoding="utf-8")
    return run_dir


def _write_experiment(root: Path, name: str) -> Path:
    exp_dir = root / "results" / "experiments" / name
    exp_dir.mkdir(parents=True)
    (exp_dir / "experiment_status.json").write_text(
        '{"overall_status": "completed", "started_at": "2026-05-12T02:00:00+02:00", "finished_at": "2026-05-12T02:10:00+02:00"}\n',
        encoding="utf-8",
    )
    (exp_dir / "closed_loop_summary.json").write_text(
        '{"final_validation_median_speedup": 1.2, "final_validation_median_runtime_reduction_percent": 16.7, "final_best_iteration": 3, "status_counts": {"accepted_improvement": 2}}\n',
        encoding="utf-8",
    )
    (exp_dir / "summary.txt").write_text("Experiment summary\n", encoding="utf-8")
    (exp_dir / "experiment_config_snapshot.json").write_text("{}\n", encoding="utf-8")
    (exp_dir / "experiment_config_effective.json").write_text("{}\n", encoding="utf-8")
    (exp_dir / "final_optimized_source").mkdir()
    (exp_dir / "final_optimized_source.diff").write_text("diff\n", encoding="utf-8")
    return exp_dir


def test_empty_results_directory_returns_empty_list(tmp_path: Path) -> None:
    root = _repo_root(tmp_path)
    (root / "results").mkdir()

    assert list_result_items(root) == []


def test_synthetic_run_is_listed(tmp_path: Path) -> None:
    root = _repo_root(tmp_path)
    _write_run(root, "run_001")

    items = list_result_items(root)

    assert len(items) == 1
    assert items[0].kind == "run"
    assert items[0].status == "success"
    assert items[0].summary_text == "Run summary\n"


def test_synthetic_experiment_is_listed(tmp_path: Path) -> None:
    root = _repo_root(tmp_path)
    _write_experiment(root, "exp_001")

    item = list_result_items(root)[0]

    assert item.kind == "experiment"
    assert item.status == "completed"
    assert item.final_speedup_vs_baseline == 1.2
    assert item.final_runtime_reduction_percent == 16.7
    assert item.final_best_iteration == 3
    assert item.accepted_improvements == 2
    assert item.artifacts.final_optimized_source_dir is not None
    assert item.artifacts.final_optimized_source_diff is not None
    assert item.artifacts.experiment_config_snapshot_json is not None
    assert item.artifacts.experiment_config_effective_json is not None


def test_experiment_does_not_fallback_to_single_run_closed_loop_metrics(tmp_path: Path) -> None:
    root = _repo_root(tmp_path)
    exp_dir = _write_experiment(root, "exp_old")
    (exp_dir / "closed_loop_summary.json").write_text(
        '{"final_speedup_vs_original_baseline": 9.9, "final_runtime_reduction_percent": 89.9, "final_best_iteration": 3}\n',
        encoding="utf-8",
    )

    item = list_result_items(root)[0]

    assert item.final_speedup_vs_baseline is None
    assert item.final_runtime_reduction_percent is None


def test_invalid_json_is_captured_in_read_errors(tmp_path: Path) -> None:
    root = _repo_root(tmp_path)
    run_dir = root / "results" / "runs" / "bad_run"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text("{bad json", encoding="utf-8")

    item = list_result_items(root)[0]

    assert item.kind == "run"
    assert item.read_errors


def test_latest_result_uses_newest_modified_directory(tmp_path: Path) -> None:
    root = _repo_root(tmp_path)
    old_run = _write_run(root, "old_run")
    new_exp = _write_experiment(root, "new_exp")
    os.utime(old_run, (1000, 1000))
    os.utime(new_exp, (2000, 2000))

    latest = get_latest_result(root)

    assert latest is not None
    assert latest.name == "new_exp"


def test_selector_latest_works(tmp_path: Path) -> None:
    root = _repo_root(tmp_path)
    _write_run(root, "run_001")

    item = resolve_result_selector("latest", root)

    assert item is not None
    assert item.name == "run_001"


def test_selector_by_unique_directory_name_works(tmp_path: Path) -> None:
    root = _repo_root(tmp_path)
    _write_run(root, "run_001")

    item = resolve_result_selector("run_001", root)

    assert item is not None
    assert item.kind == "run"


def test_open_path_raises_clear_error_for_missing_path(tmp_path: Path) -> None:
    with pytest.raises(OpenArtifactError, match="Path does not exist"):
        open_path(tmp_path / "missing")
