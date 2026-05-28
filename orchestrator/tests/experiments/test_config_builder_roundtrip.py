"""Tests for config builder payload roundtrip (serialize -> dump -> load)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from orchestrator.experiments.experiment_config import (
    ExperimentConfig,
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
        description="Builder roundtrip test - poselib solver",
        solver_id="poselib_p3p",
        target_file="cpp/external/poselib/PoseLib/solvers/p3p.cc",
        baseline_run_dir="results/runs/test_baseline",
        optimization_scope=OptimizationScopeConfig(allowed_files=["cpp/external/poselib/PoseLib/solvers/p3p.cc"]),
        reporting=ReportingConfig(enabled=True, formats=["html"], renderer="auto"),
        selection=SelectionPolicyConfig(gt_found_max_drop_points=gt_found_max_drop_points),
        llm_config="configs/llm_deepseek_flash.json",
        llm_overrides=llm_overrides,
        iterations=3,
        additional_context=None,
    )


class TestPayloadRoundtripNullGtFound:
    def test_roundtrip_null_gt_found_drop_points(self, tmp_path: Path) -> None:
        out_path = tmp_path / "null_gt.json"
        dump_experiment_config(_make_poselib_config(gt_found_max_drop_points=None), out_path)
        loaded = load_experiment_config(out_path)
        assert loaded.selection.gt_found_max_drop_points is None

    def test_json_null_preserved(self, tmp_path: Path) -> None:
        out_path = tmp_path / "null_gt2.json"
        dump_experiment_config(_make_poselib_config(gt_found_max_drop_points=None), out_path)
        raw = json.loads(out_path.read_text(encoding="utf-8"))
        assert raw["selection"]["gt_found_max_drop_points"] is None

    def test_payload_null_preserved(self) -> None:
        payload = experiment_config_to_payload(_make_poselib_config(gt_found_max_drop_points=None))
        assert payload["selection"]["gt_found_max_drop_points"] is None


class TestPayloadRoundtripNumericGtFound:
    def test_roundtrip_numeric_gt_found_drop_points(self, tmp_path: Path) -> None:
        out_path = tmp_path / "num_gt.json"
        dump_experiment_config(_make_poselib_config(gt_found_max_drop_points=2.5), out_path)
        loaded = load_experiment_config(out_path)
        assert loaded.selection.gt_found_max_drop_points == 2.5

    def test_roundtrip_zero_gt_found_drop_points(self, tmp_path: Path) -> None:
        out_path = tmp_path / "zero_gt.json"
        dump_experiment_config(_make_poselib_config(gt_found_max_drop_points=0.0), out_path)
        loaded = load_experiment_config(out_path)
        assert loaded.selection.gt_found_max_drop_points == 0.0


class TestPayloadRoundtripOverrides:
    def test_roundtrip_null_overrides(self, tmp_path: Path) -> None:
        out_path = tmp_path / "null_ov.json"
        dump_experiment_config(_make_poselib_config(llm_overrides=None), out_path)
        loaded = load_experiment_config(out_path)
        assert loaded.llm_overrides is None

    def test_roundtrip_populated_overrides(self, tmp_path: Path) -> None:
        overrides = {
            "provider": "deepseek",
            "model": "deepseek-v4",
            "max_tokens": 4096,
            "thinking": {"enabled": True, "effort": "medium"},
        }
        out_path = tmp_path / "pop_ov.json"
        dump_experiment_config(_make_poselib_config(llm_overrides=overrides), out_path)
        loaded = load_experiment_config(out_path)

        assert loaded.llm_overrides is not None
        assert loaded.llm_overrides["provider"] == "deepseek"
        assert loaded.llm_overrides["model"] == "deepseek-v4"
        assert loaded.llm_overrides["max_tokens"] == 4096
        assert loaded.llm_overrides["thinking"]["enabled"] is True
        assert loaded.llm_overrides["thinking"]["effort"] == "medium"


class TestPayloadTopLevelKeys:
    def test_payload_contains_all_expected_keys(self) -> None:
        payload = experiment_config_to_payload(_make_poselib_config())

        for key in (
            "experiment_name",
            "solver_id",
            "target_file",
            "baseline_run_dir",
            "reporting",
            "selection",
            "llm_config",
            "llm_overrides",
            "iterations",
            "additional_context",
        ):
            assert key in payload, f"missing key: {key}"
        assert "optimization_scope" not in payload
        assert "variants" not in payload
        assert "variant_id" not in json.dumps(payload)


class TestFullRoundtripStrictEquivalence:
    def test_full_config_dump_load_field_equivalence(self, tmp_path: Path) -> None:
        overrides = {
            "provider": "deepseek",
            "model": "deepseek-v4",
            "max_tokens": 4096,
            "thinking": {"enabled": True, "effort": "high"},
        }
        out_path = tmp_path / "full_poselib.json"
        dump_experiment_config(_make_poselib_config(gt_found_max_drop_points=1.0, llm_overrides=overrides), out_path)
        loaded = load_experiment_config(out_path)

        assert loaded.experiment_name == "roundtrip-poselib"
        assert loaded.solver_id == "poselib_p3p"
        assert loaded.target_file == "cpp/external/poselib/PoseLib/solvers/p3p.cc"
        assert loaded.baseline_run_dir == "results/runs/test_baseline"
        assert loaded.optimization_scope.allowed_files == ["cpp/external/poselib/PoseLib/solvers/p3p.cc"]
        assert loaded.reporting.formats == ["html"]
        assert loaded.selection.gt_found_max_drop_points == 1.0
        assert loaded.llm_config == "configs/llm_deepseek_flash.json"
        assert loaded.iterations == 3
        assert loaded.additional_context is None
        assert loaded.llm_overrides is not None
        assert loaded.llm_overrides["thinking"]["effort"] == "high"
