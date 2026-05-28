"""Tests for experiment config loading with fixed candidate schema."""

from __future__ import annotations

import json
import pytest

pytestmark = pytest.mark.integration
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


class ExperimentConfigFixedCandidateSchemaTests(unittest.TestCase):
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

    def test_legacy_multiple_variants_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = _base_config_payload()
            payload.pop("llm_config")
            payload.pop("iterations")
            payload["variants"] = [
                {"variant_id": "a", "llm_config": "configs/llm_mock_candidate.json", "iterations": 1},
                {"variant_id": "b", "llm_config": "configs/llm_mock_candidate.json", "iterations": 1},
            ]

            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(_write_config(Path(tmpdir), payload))

        self.assertIn("exactly one variant", str(ctx.exception))

    def test_missing_selection_defaults_gt_found_gate_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir)))

        self.assertIsNone(config.selection.gt_found_max_drop_points)

    def test_selection_null_disables_gt_found_gate(self) -> None:
        payload = _base_config_payload()
        payload["selection"] = {"gt_found_max_drop_points": None}
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir), payload))

        self.assertIsNone(config.selection.gt_found_max_drop_points)

    def test_selection_accepts_zero_and_positive_drop_points(self) -> None:
        for value in (0.0, 2.5):
            payload = _base_config_payload()
            payload["selection"] = {"gt_found_max_drop_points": value}
            with tempfile.TemporaryDirectory() as tmpdir:
                config = load_experiment_config(_write_config(Path(tmpdir), payload))

            self.assertEqual(config.selection.gt_found_max_drop_points, value)

    def test_selection_rejects_invalid_drop_points(self) -> None:
        for value in (-0.1, "2.5", True):
            payload = _base_config_payload()
            payload["selection"] = {"gt_found_max_drop_points": value}
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaises(ExperimentConfigError) as ctx:
                    load_experiment_config(_write_config(Path(tmpdir), payload))

            self.assertIn("selection.gt_found_max_drop_points", str(ctx.exception))

    def test_baseline_solver_mismatch_fails_when_metadata_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline_dir = root / "baseline"
            baseline_dir.mkdir()
            (baseline_dir / "metadata.json").write_text(
                json.dumps({"solver_id": "poselib_p3p"}) + "\n",
                encoding="utf-8",
            )
            payload = _base_config_payload()
            payload["baseline_run_dir"] = str(baseline_dir)
            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(_write_config(root, payload))

        self.assertIn("different solver_id", str(ctx.exception))

    def test_missing_baseline_metadata_does_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            baseline_dir = root / "baseline"
            baseline_dir.mkdir()
            payload = _base_config_payload()
            payload["baseline_run_dir"] = str(baseline_dir)
            config = load_experiment_config(_write_config(root, payload))

        self.assertEqual(config.baseline_run_dir, str(baseline_dir))


if __name__ == "__main__":
    unittest.main()
