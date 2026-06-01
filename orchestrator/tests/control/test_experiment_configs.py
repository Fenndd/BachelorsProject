from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

from pathlib import Path

from orchestrator.control.experiment_configs import (
    list_experiment_config_summaries,
    read_experiment_config_summary,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_valid_experiment(root: Path, provider: str = "deepseek", model: str = "model-x") -> Path:
    (root / ".git").mkdir(exist_ok=True)
    (root / "configs" / "experiments").mkdir(parents=True, exist_ok=True)
    llm_config = root / "configs" / "llm_test.json"
    llm_config.write_text(
        f'{{"provider": "{provider}", "model": "{model}"}}\n',
        encoding="utf-8",
    )
    experiment = root / "configs" / "experiments" / "test_exp.json"
    experiment.write_text(
        """{
  "experiment_name": "test_exp",
  "description": "Test experiment",
  "target_file": "cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc",
  "baseline_run_dir": "results/runs/baseline",
  "optimization_scope": {
    "allowed_files": ["cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"]
  },
  "llm_config": "configs/llm_test.json",
  "iterations": 2
}
""",
        encoding="utf-8",
    )
    return experiment


def test_listing_existing_configs_does_not_crash() -> None:
    summaries = list_experiment_config_summaries(REPO_ROOT)

    assert isinstance(summaries, list)


def test_valid_config_summary_can_be_read_from_path(tmp_path: Path) -> None:
    config = _write_valid_experiment(tmp_path, provider="mock", model="mock-model")

    summary = read_experiment_config_summary(config)

    assert summary.status == "ok"
    assert summary.name == "test_exp"
    assert summary.total_iterations == 2


def test_invalid_json_config_is_reported_without_crashing(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    config_dir = tmp_path / "configs" / "experiments"
    config_dir.mkdir(parents=True)
    (config_dir / "bad.json").write_text("{not valid json", encoding="utf-8")

    summaries = list_experiment_config_summaries(tmp_path)

    assert len(summaries) == 1
    assert summaries[0].status == "invalid"
    assert summaries[0].message


def test_provider_and_model_are_extracted_from_llm_config(tmp_path: Path) -> None:
    config = _write_valid_experiment(tmp_path, provider="deepseek", model="deepseek-test")

    summary = read_experiment_config_summary(config)

    assert summary.status == "ok"
    assert summary.providers == ["deepseek"]
    assert summary.models == ["deepseek-test"]


def test_flat_config_without_baseline_is_reported_invalid_but_summarized(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    config_dir = tmp_path / "configs" / "experiments"
    config_dir.mkdir(parents=True)
    llm_config = tmp_path / "configs" / "llm_old.json"
    llm_config.write_text('{"provider": "old", "model": "old-model"}\n', encoding="utf-8")
    old_config = config_dir / "old_top_level.json"
    old_config.write_text(
        """{
  "experiment_name": "old_style",
  "llm_config": "configs/llm_old.json",
  "iterations": 5
}
""",
        encoding="utf-8",
    )

    summary = read_experiment_config_summary(old_config)

    assert summary.status == "invalid"
    assert summary.total_iterations == 5
    assert summary.providers == ["old"]
    assert summary.models == ["old-model"]
