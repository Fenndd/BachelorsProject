"""Tests for experiment config loading after candidate format removal."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from orchestrator.experiments.experiment_config import (
    ExperimentConfigError,
    load_experiment_config,
)


def _base_config_payload() -> dict[str, Any]:
    return {
        "experiment_name": "candidate config test",
        "target_file": "cpp/external/lambdatwist/p3p.cc",
        "baseline_run_dir": "results/runs/baseline",
        "candidate_generation": {"max_source_chars": 1000},
        "variants": [
            {
                "variant_id": "default",
                "llm_config": "configs/llm_mock_candidate.json",
                "iterations": 1,
            }
        ],
    }


def _write_config(root: Path, payload: dict[str, Any] | None = None) -> Path:
    config_path = root / "experiment_config.json"
    config_path.write_text(
        json.dumps(payload or _base_config_payload(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return config_path


class ExperimentConfigCandidateFormatTests(unittest.TestCase):
    def test_config_loads_without_removed_format_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir)))

        removed_field = "candidate" + "_format"
        self.assertFalse(hasattr(config, removed_field))
        self.assertEqual(config.baseline_run_dir, "results/runs/baseline")

    def test_removed_format_field_is_ignored_as_user_config(self) -> None:
        payload = _base_config_payload()
        removed_field = "candidate" + "_format"
        payload[removed_field] = {
            "type": "legacy_value",
            "source" + "_presentation": "legacy_value",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir), payload))

        self.assertFalse(hasattr(config, removed_field))

    def test_baseline_run_dir_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _base_config_payload()
            payload.pop("baseline_run_dir")
            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(_write_config(Path(tmpdir), payload))

        self.assertIn("baseline_run_dir", str(ctx.exception))

    def test_closed_loop_with_multiple_variants_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _base_config_payload()
            payload["variants"] = [
                {"variant_id": "a", "llm_config": "configs/llm_mock_candidate.json", "iterations": 1},
                {"variant_id": "b", "llm_config": "configs/llm_mock_candidate.json", "iterations": 1},
            ]

            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(_write_config(Path(tmpdir), payload))

        self.assertIn("exactly one variant", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
