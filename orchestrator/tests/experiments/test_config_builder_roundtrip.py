"""Tests for config builder payload roundtrip (serialize → dump → load).

Focuses on the serializer path used by the Config Builder
(experiment_config_to_payload / dump_experiment_config) and verifies
that load_experiment_config restores equivalent configs.

This file targets cases not covered by test_experiment_config_dump.py:
poselib solver, strict null/numeric gt_found_max_drop_points roundtrip,
and full overrides payload equality.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from orchestrator.experiments.experiment_config import (
    CandidateGenerationConfig,
    ExperimentConfig,
    ExperimentConfigError,
    ExperimentVariantConfig,
    OptimizationScopeConfig,
    ReportingConfig,
    SelectionPolicyConfig,
    dump_experiment_config,
    experiment_config_to_payload,
    load_experiment_config,
)


def _make_poselib_config(
    gt_found_max_drop_points: float | None = None,
    llm_overrides: dict | None = None,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="roundtrip-poselib",
        description="Builder roundtrip test — poselib solver",
        solver_id="poselib_p3p",
        target_file="cpp/external/poselib/PoseLib/solvers/p3p.cc",
        baseline_run_dir="results/runs/test_baseline",
        candidate_generation=CandidateGenerationConfig(max_source_chars=120000),
        optimization_scope=OptimizationScopeConfig(
            allowed_files=["cpp/external/poselib/PoseLib/solvers/p3p.cc"],
        ),
        reporting=ReportingConfig(
            enabled=True,
            formats=["html"],
            renderer="auto",
            fail_on_error=False,
        ),
        selection=SelectionPolicyConfig(gt_found_max_drop_points=gt_found_max_drop_points),
        variants=[
            ExperimentVariantConfig(
                variant_id="default",
                description=None,
                llm_config="configs/llm_deepseek_flash.json",
                llm_overrides=llm_overrides,
                iterations=3,
                additional_context=None,
            )
        ],
    )


class TestPayloadRoundtripNullGtFound:
    def test_roundtrip_null_gt_found_drop_points(self, tmp_path: Path) -> None:
        config = _make_poselib_config(gt_found_max_drop_points=None)
        out_path = tmp_path / "null_gt.json"
        dump_experiment_config(config, out_path)
        loaded = load_experiment_config(out_path)
        assert loaded.selection.gt_found_max_drop_points is None

    def test_json_null_preserved(self, tmp_path: Path) -> None:
        config = _make_poselib_config(gt_found_max_drop_points=None)
        out_path = tmp_path / "null_gt2.json"
        dump_experiment_config(config, out_path)
        raw = json.loads(out_path.read_text(encoding="utf-8"))
        assert raw["selection"]["gt_found_max_drop_points"] is None

    def test_payload_null_preserved(self) -> None:
        config = _make_poselib_config(gt_found_max_drop_points=None)
        payload = experiment_config_to_payload(config)
        assert payload["selection"]["gt_found_max_drop_points"] is None


class TestPayloadRoundtripNumericGtFound:
    def test_roundtrip_numeric_gt_found_drop_points(self, tmp_path: Path) -> None:
        config = _make_poselib_config(gt_found_max_drop_points=2.5)
        out_path = tmp_path / "num_gt.json"
        dump_experiment_config(config, out_path)
        loaded = load_experiment_config(out_path)
        assert loaded.selection.gt_found_max_drop_points == 2.5

    def test_roundtrip_zero_gt_found_drop_points(self, tmp_path: Path) -> None:
        config = _make_poselib_config(gt_found_max_drop_points=0.0)
        out_path = tmp_path / "zero_gt.json"
        dump_experiment_config(config, out_path)
        loaded = load_experiment_config(out_path)
        assert loaded.selection.gt_found_max_drop_points == 0.0


class TestPayloadRoundtripOverrides:
    def test_roundtrip_null_overrides(self, tmp_path: Path) -> None:
        config = _make_poselib_config(llm_overrides=None)
        out_path = tmp_path / "null_ov.json"
        dump_experiment_config(config, out_path)
        loaded = load_experiment_config(out_path)
        assert loaded.variants[0].llm_overrides is None

    def test_roundtrip_populated_overrides(self, tmp_path: Path) -> None:
        overrides = {
            "provider": "deepseek",
            "model": "deepseek-v4",
            "max_tokens": 4096,
            "thinking": {
                "enabled": True,
                "effort": "medium",
            },
        }
        config = _make_poselib_config(llm_overrides=overrides)
        out_path = tmp_path / "pop_ov.json"
        dump_experiment_config(config, out_path)
        loaded = load_experiment_config(out_path)

        v = loaded.variants[0]
        assert v.llm_overrides is not None
        assert v.llm_overrides["provider"] == "deepseek"
        assert v.llm_overrides["model"] == "deepseek-v4"
        assert v.llm_overrides["max_tokens"] == 4096
        assert v.llm_overrides["thinking"]["enabled"] is True
        assert v.llm_overrides["thinking"]["effort"] == "medium"


class TestPayloadTopLevelKeys:
    def test_payload_contains_all_expected_keys(self) -> None:
        config = _make_poselib_config()
        payload = experiment_config_to_payload(config)

        for key in (
            "experiment_name",
            "solver_id",
            "target_file",
            "baseline_run_dir",
            "candidate_generation",
            "optimization_scope",
            "reporting",
            "selection",
            "variants",
        ):
            assert key in payload, f"missing key: {key}"

        assert len(payload["variants"]) == 1
        v = payload["variants"][0]
        assert "variant_id" in v
        assert "llm_config" in v
        assert "iterations" in v


class TestFullRoundtripStrictEquivalence:
    def test_full_config_dump_load_field_equivalence(self, tmp_path: Path) -> None:
        overrides = {
            "provider": "deepseek",
            "model": "deepseek-v4",
            "max_tokens": 4096,
            "thinking": {
                "enabled": True,
                "effort": "high",
            },
        }
        config = _make_poselib_config(
            gt_found_max_drop_points=1.0,
            llm_overrides=overrides,
        )
        out_path = tmp_path / "full_poselib.json"
        dump_experiment_config(config, out_path)
        loaded = load_experiment_config(out_path)

        assert loaded.experiment_name == "roundtrip-poselib"
        assert loaded.description == "Builder roundtrip test — poselib solver"
        assert loaded.solver_id == "poselib_p3p"
        assert loaded.target_file == "cpp/external/poselib/PoseLib/solvers/p3p.cc"
        assert loaded.baseline_run_dir == "results/runs/test_baseline"
        assert loaded.candidate_generation.max_source_chars == 120000
        assert loaded.optimization_scope.allowed_files == ["cpp/external/poselib/PoseLib/solvers/p3p.cc"]
        assert loaded.reporting.enabled is True
        assert loaded.reporting.formats == ["html"]
        assert loaded.reporting.renderer == "auto"
        assert loaded.reporting.fail_on_error is False
        assert loaded.selection.gt_found_max_drop_points == 1.0

        assert len(loaded.variants) == 1
        v = loaded.variants[0]
        assert v.variant_id == "default"
        assert v.description is None
        assert v.llm_config == "configs/llm_deepseek_flash.json"
        assert v.iterations == 3
        assert v.additional_context is None

        assert v.llm_overrides is not None
        assert v.llm_overrides["provider"] == "deepseek"
        assert v.llm_overrides["model"] == "deepseek-v4"
        assert v.llm_overrides["max_tokens"] == 4096
        assert v.llm_overrides["thinking"]["enabled"] is True
        assert v.llm_overrides["thinking"]["effort"] == "high"
