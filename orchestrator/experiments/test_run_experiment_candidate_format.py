"""Tests for experiment-runner candidate format command wiring."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.experiments.experiment_config import load_experiment_config
from orchestrator.experiments.run_experiment import _build_generation_command


def _base_config_payload(candidate_format: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "experiment_name": "candidate format command test",
        "target_file": "cpp/external/lambdatwist/p3p.cc",
        "pipeline": {
            "generate_candidate": True,
            "materialize_candidate": True,
            "verify_candidate": True,
        },
        "candidate_generation": {"max_source_chars": 1000},
        "llm_config": "configs/llm_mock_candidate.json",
        "iterations": 1,
    }
    if candidate_format is not None:
        payload["candidate_format"] = candidate_format
    return payload


def _write_config(root: Path, candidate_format: dict[str, Any] | None = None) -> Path:
    config_path = root / "experiment_config.json"
    config_path.write_text(
        json.dumps(_base_config_payload(candidate_format), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return config_path


class RunExperimentCandidateFormatTests(unittest.TestCase):
    def test_default_generation_command_passes_unified_diff_plain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir)))

        command = _build_generation_command(config, "llm.json", None)

        self.assertEqual(command[command.index("--candidate-type") + 1], "unified_diff")
        self.assertEqual(command[command.index("--source-presentation") + 1], "plain")

    def test_line_range_generation_command_passes_configured_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(
                _write_config(
                    Path(tmpdir),
                    {
                        "type": "line_range_edits",
                        "source_presentation": "line_numbered",
                        "require_original_verification": True,
                        "allow_exact_search_fallback": True,
                    },
                )
            )

        command = _build_generation_command(config, "llm.json", None)

        self.assertEqual(command[command.index("--candidate-type") + 1], "line_range_edits")
        self.assertEqual(
            command[command.index("--source-presentation") + 1],
            "line_numbered",
        )

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


if __name__ == "__main__":
    unittest.main()