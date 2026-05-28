"""Tests for experiment-runner command wiring with fixed schema."""

from __future__ import annotations

import json
import pytest

pytestmark = pytest.mark.integration
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.experiments.experiment_config import load_experiment_config
from orchestrator.experiments.iteration_runner import (
    _build_generation_command,
    _build_materialization_command,
)


def _base_config_payload() -> dict[str, Any]:
    return {
        "experiment_name": "candidate command test",
        "target_file": "cpp/external/lambdatwist/p3p.cc",
        "baseline_run_dir": "results/runs/baseline",
        "candidate_generation": {"max_source_chars": 1000},
        "llm_config": "configs/llm_mock_candidate.json",
        "iterations": 1,
    }


def _write_config(root: Path, payload: dict[str, Any] | None = None) -> Path:
    config_path = root / "experiment_config.json"
    config_path.write_text(
        json.dumps(payload or _base_config_payload(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return config_path


class RunExperimentFixedSchemaTests(unittest.TestCase):
    def test_generation_command_does_not_pass_format_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir)))

        command = _build_generation_command(config, "llm.json", None)

        self.assertNotIn("--candidate-type", command)
        self.assertNotIn("--source-presentation", command)

    def test_generation_command_can_pass_optional_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir)))

        command = _build_generation_command(
            config,
            "llm.json",
            None,
            source_root="workspace/experiments/exp_001/current_best_source",
        )

        self.assertEqual(
            command[command.index("--source-root") + 1],
            "workspace/experiments/exp_001/current_best_source",
        )

    def test_materialization_command_does_not_pass_format_fallback_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir)))

        command = _build_materialization_command(
            "results/runs/candidate_001",
            config,
            base_source_root="workspace/experiments/exp_001/current_best_source",
        )

        self.assertEqual(
            command[command.index("--base-source-root") + 1],
            "workspace/experiments/exp_001/current_best_source",
        )
        self.assertNotIn("--allow-exact-search" + "-fallback", command)
        self.assertNotIn("--no-allow-exact-search" + "-fallback", command)


if __name__ == "__main__":
    unittest.main()
