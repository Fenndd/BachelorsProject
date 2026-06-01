"""Tests for dump_experiment_config and experiment_config_to_payload."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

from orchestrator.control.experiment_configs import list_experiment_config_paths
from orchestrator.experiments.experiment_config import (
    ExperimentConfig,
    OptimizationScopeConfig,
    ReportingConfig,
    SelectionPolicyConfig,
    dump_experiment_config,
    experiment_config_to_payload,
    load_experiment_config,
)


def _make_full_config() -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="test_full",
        description="A full test experiment",
        solver_id="poselib_p3p_lambdatwist",
        target_file="cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc",
        baseline_run_dir="results/runs/test_baseline",
        optimization_scope=OptimizationScopeConfig(allowed_files=["cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"]),
        reporting=ReportingConfig(enabled=True, formats=["html", "pdf"], renderer="auto"),
        selection=SelectionPolicyConfig(gt_found_max_drop_points=2.5),
        llm_config="configs/llm_deepseek.json",
        llm_overrides={
            "provider": "deepseek",
            "model": "deepseek-v4",
            "max_tokens": 4096,
            "thinking": {"enabled": True, "effort": "medium"},
        },
        iterations=5,
        additional_context="Some additional context",
    )


def _make_minimal_config() -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="test_min",
        solver_id="poselib_p3p_lambdatwist",
        target_file="cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc",
        baseline_run_dir="results/runs/test_baseline",
        optimization_scope=OptimizationScopeConfig(allowed_files=["cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"]),
        reporting=ReportingConfig(),
        llm_config="configs/llm_mock.json",
        llm_overrides=None,
        iterations=1,
        additional_context=None,
        description=None,
    )


class TestDumpLoadRoundtrip:
    def test_full_config_roundtrip(self, tmp_path: Path) -> None:
        out_path = tmp_path / "test_full.json"
        dump_experiment_config(_make_full_config(), out_path)
        loaded = load_experiment_config(out_path)

        assert loaded.experiment_name == "test_full"
        assert loaded.description == "A full test experiment"
        assert loaded.target_file == "cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"
        assert loaded.baseline_run_dir == "results/runs/test_baseline"
        assert loaded.optimization_scope.allowed_files == ["cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"]
        assert loaded.reporting.formats == ["html", "pdf"]
        assert loaded.selection.gt_found_max_drop_points == 2.5
        assert loaded.llm_config == "configs/llm_deepseek.json"
        assert loaded.iterations == 5
        assert loaded.additional_context == "Some additional context"
        assert loaded.llm_overrides is not None
        assert loaded.llm_overrides["provider"] == "deepseek"
        assert loaded.llm_overrides["thinking"]["effort"] == "medium"

    def test_minimal_config_roundtrip(self, tmp_path: Path) -> None:
        out_path = tmp_path / "test_min.json"
        dump_experiment_config(_make_minimal_config(), out_path)
        loaded = load_experiment_config(out_path)

        assert loaded.experiment_name == "test_min"
        assert loaded.description is None
        assert loaded.selection.gt_found_max_drop_points is None
        assert loaded.llm_overrides is None
        assert loaded.additional_context is None

    def test_null_overrides_roundtrip(self, tmp_path: Path) -> None:
        out_path = tmp_path / "test_null_ov.json"
        dump_experiment_config(_make_minimal_config(), out_path)

        raw = json.loads(out_path.read_text(encoding="utf-8"))
        assert raw["llm_overrides"] is None
        assert "variants" not in raw
        assert "variant_id" not in json.dumps(raw)

        loaded = load_experiment_config(out_path)
        assert loaded.llm_overrides is None

    def test_payload_shape_has_required_keys(self) -> None:
        payload = experiment_config_to_payload(_make_full_config())

        for key in (
            "experiment_name",
            "target_file",
            "baseline_run_dir",
            "reporting",
            "selection",
            "llm_config",
            "llm_overrides",
            "iterations",
            "additional_context",
        ):
            assert key in payload
        assert "optimization_scope" not in payload
        assert "variants" not in payload
        assert "variant_id" not in json.dumps(payload)

    def test_planner_has_no_variant_config_imports(self) -> None:
        source = Path("orchestrator/experiments/experiment_planner.py").read_text(encoding="utf-8")
        assert "ExperimentVariantConfig" not in source
        assert "variant_id" not in source
        assert "config.variants" not in source

    def test_payload_preserves_nulls(self) -> None:
        payload = experiment_config_to_payload(_make_minimal_config())
        assert payload["description"] is None
        assert payload["additional_context"] is None
        assert payload["selection"]["gt_found_max_drop_points"] is None

class TestConfigDiscovery:
    def test_list_includes_root_configs(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True, exist_ok=True)
        exp_dir = root / "configs" / "experiments"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "test_a.json").write_text("{}", encoding="utf-8")

        names = {p.name for p in list_experiment_config_paths(root)}
        assert "test_a.json" in names

    def test_list_includes_local(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True, exist_ok=True)
        local_dir = root / "configs" / "experiments" / "local"
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "my_exp.json").write_text("{}", encoding="utf-8")

        names = {p.name for p in list_experiment_config_paths(root)}
        assert "my_exp.json" in names
