"""Tests for experiment candidate_format config loading and validation."""

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
        "experiment_name": "candidate format config test",
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


def _write_config(root: Path, candidate_format: dict[str, Any] | None = None) -> Path:
    payload = _base_config_payload()
    if candidate_format is not None:
        payload["candidate_format"] = candidate_format

    config_path = root / "experiment_config.json"
    config_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return config_path


def _candidate_format_payload(**overrides: Any) -> dict[str, Any]:
    candidate_format = {
        "type": "unified_diff",
        "source_presentation": "plain",
        "require_original_verification": True,
        "allow_exact_search_fallback": True,
    }
    candidate_format.update(overrides)
    return candidate_format


class ExperimentConfigCandidateFormatTests(unittest.TestCase):
    def test_missing_candidate_format_defaults_to_unified_diff_plain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(_write_config(Path(tmpdir)))

        self.assertEqual(config.candidate_format.type, "unified_diff")
        self.assertEqual(config.candidate_format.source_presentation, "plain")
        self.assertTrue(config.candidate_format.require_original_verification)
        self.assertTrue(config.candidate_format.allow_exact_search_fallback)
        self.assertEqual(config.baseline_run_dir, "results/runs/baseline")

    def test_baseline_run_dir_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = _base_config_payload()
            payload.pop("baseline_run_dir")
            config_path = root / "experiment_config.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(config_path)

        self.assertIn("baseline_run_dir", str(ctx.exception))

    def test_closed_loop_with_multiple_variants_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = _base_config_payload()
            payload["variants"] = [
                {"variant_id": "a", "llm_config": "configs/llm_mock_candidate.json", "iterations": 1},
                {"variant_id": "b", "llm_config": "configs/llm_mock_candidate.json", "iterations": 1},
            ]
            config_path = root / "experiment_config.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(config_path)

        self.assertIn("exactly one variant", str(ctx.exception))

    def test_removed_closed_loop_switch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = _base_config_payload()
            payload["closed_loop"] = {"enabled": False}
            config_path = root / "experiment_config.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(config_path)

        self.assertIn("closed_loop", str(ctx.exception))

    def test_removed_pipeline_flags_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = _base_config_payload()
            payload["pipeline"] = {"generate_candidate": True}
            config_path = root / "experiment_config.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(ExperimentConfigError) as ctx:
                load_experiment_config(config_path)

        self.assertIn("pipeline", str(ctx.exception))

    def test_explicit_unified_diff_plain_loads_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(
                _write_config(Path(tmpdir), _candidate_format_payload())
            )

        self.assertEqual(config.candidate_format.type, "unified_diff")
        self.assertEqual(config.candidate_format.source_presentation, "plain")

    def test_explicit_line_range_edits_line_numbered_loads_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(
                _write_config(
                    Path(tmpdir),
                    _candidate_format_payload(
                        type="line_range_edits",
                        source_presentation="line_numbered",
                    ),
                )
            )

        self.assertEqual(config.candidate_format.type, "line_range_edits")
        self.assertEqual(config.candidate_format.source_presentation, "line_numbered")

    def test_unknown_candidate_format_type_is_rejected(self) -> None:
        self._assert_candidate_format_rejected(type="json_patch")

    def test_unknown_candidate_format_source_presentation_is_rejected(self) -> None:
        self._assert_candidate_format_rejected(source_presentation="annotated")

    def test_unified_diff_with_line_numbered_is_rejected(self) -> None:
        self._assert_candidate_format_rejected(
            type="unified_diff",
            source_presentation="line_numbered",
        )

    def test_line_range_edits_with_plain_is_rejected(self) -> None:
        self._assert_candidate_format_rejected(
            type="line_range_edits",
            source_presentation="plain",
        )

    def test_non_boolean_require_original_verification_is_rejected(self) -> None:
        self._assert_candidate_format_rejected(require_original_verification="true")

    def test_non_boolean_allow_exact_search_fallback_is_rejected(self) -> None:
        self._assert_candidate_format_rejected(allow_exact_search_fallback="true")

    def _assert_candidate_format_rejected(self, **overrides: Any) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = _write_config(
                Path(tmpdir),
                _candidate_format_payload(**overrides),
            )

            with self.assertRaises(ExperimentConfigError):
                load_experiment_config(config_path)


if __name__ == "__main__":
    unittest.main()
