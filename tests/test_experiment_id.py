from __future__ import annotations

from datetime import datetime
from pathlib import Path

from orchestrator.experiments import run_experiment
from orchestrator.experiments.experiment_config import load_experiment_config


def _config(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        """
{
  "experiment_name": "closed loop deepseek flash p3p 10iter report html",
  "target_file": "cpp/external/lambdatwist/p3p.cc",
  "pipeline": {"generate_candidate": true, "materialize_candidate": true, "verify_candidate": true},
  "candidate_generation": {"max_source_chars": 1000},
  "candidate_format": {"type": "line_range_edits", "source_presentation": "line_numbered", "require_original_verification": true, "allow_exact_search_fallback": true},
  "closed_loop": {"enabled": true},
  "selection": {"enabled": false, "baseline_run_dir": "results/runs/baseline"},
  "llm_config": "configs/llm_mock_candidate.json",
  "iterations": 1
}
""".strip(),
        encoding="utf-8",
    )
    return load_experiment_config(path)


def test_experiment_id_omits_seconds(tmp_path: Path) -> None:
    config = _config(tmp_path)

    experiment_id = run_experiment._build_experiment_id(
        config,
        datetime(2026, 5, 15, 20, 34, 59),
    )

    assert experiment_id == "2026-05-15_20-34_closed_loop_deepseek_flash_p3p_10iter_report_html"


def test_create_experiment_dir_appends_two_digit_suffix_on_collision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "results" / "experiments"
    monkeypatch.setattr(run_experiment, "EXPERIMENTS_ROOT", root)
    base = "2026-05-15_20-34_example"
    (root / base / "logs").mkdir(parents=True)

    created = run_experiment._create_experiment_dir(base)

    assert created.name == "2026-05-15_20-34_example_01"
    assert (created / "logs").is_dir()
