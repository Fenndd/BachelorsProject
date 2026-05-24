"""Tests for dump_experiment_config and experiment_config_to_payload."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

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
from orchestrator.control.experiment_configs import list_experiment_config_paths


def _make_full_config() -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="test_full",
        description="A full test experiment",
        solver_id="lambdatwist_p3p",
        target_file="cpp/external/lambdatwist/p3p.cc",
        baseline_run_dir="results/runs/test_baseline",
        candidate_generation=CandidateGenerationConfig(max_source_chars=50000),
        optimization_scope=OptimizationScopeConfig(
            allowed_files=["cpp/external/lambdatwist/p3p.cc"],
        ),
        reporting=ReportingConfig(
            enabled=True,
            formats=["html", "pdf"],
            renderer="auto",
            fail_on_error=False,
        ),
        selection=SelectionPolicyConfig(gt_found_max_drop_points=2.5),
        variants=[
            ExperimentVariantConfig(
                variant_id="main",
                description="Main variant",
                llm_config="configs/llm_deepseek.json",
                llm_overrides={
                    "provider": "deepseek",
                    "model": "deepseek-v4",
                    "max_tokens": 4096,
                    "thinking": {
                        "enabled": True,
                        "effort": "medium",
                    },
                },
                iterations=5,
                additional_context="Some additional context",
            )
        ],
    )


def _make_minimal_config() -> ExperimentConfig:
    return ExperimentConfig(
        experiment_name="test_min",
        solver_id="lambdatwist_p3p",
        target_file="cpp/external/lambdatwist/p3p.cc",
        baseline_run_dir="results/runs/test_baseline",
        candidate_generation=CandidateGenerationConfig(max_source_chars=10000),
        optimization_scope=OptimizationScopeConfig(
            allowed_files=["cpp/external/lambdatwist/p3p.cc"],
        ),
        reporting=ReportingConfig(),
        variants=[
            ExperimentVariantConfig(
                variant_id="default",
                llm_config="configs/llm_mock.json",
                llm_overrides=None,
                iterations=1,
                description=None,
                additional_context=None,
            )
        ],
        description=None,
    )


class TestDumpLoadRoundtrip:
    def test_full_config_roundtrip(self, tmp_path: Path) -> None:
        config = _make_full_config()
        out_path = tmp_path / "test_full.json"
        dump_experiment_config(config, out_path)
        loaded = load_experiment_config(out_path)

        assert loaded.experiment_name == "test_full"
        assert loaded.description == "A full test experiment"
        assert loaded.target_file == "cpp/external/lambdatwist/p3p.cc"
        assert loaded.baseline_run_dir == "results/runs/test_baseline"
        assert loaded.candidate_generation.max_source_chars == 50000
        assert loaded.optimization_scope.allowed_files == ["cpp/external/lambdatwist/p3p.cc"]
        assert loaded.reporting.enabled is True
        assert loaded.reporting.formats == ["html", "pdf"]
        assert loaded.reporting.renderer == "auto"
        assert loaded.reporting.fail_on_error is False
        assert loaded.selection.gt_found_max_drop_points == 2.5

        assert len(loaded.variants) == 1
        v = loaded.variants[0]
        assert v.variant_id == "main"
        assert v.description == "Main variant"
        assert v.llm_config == "configs/llm_deepseek.json"
        assert v.iterations == 5
        assert v.additional_context == "Some additional context"

        assert v.llm_overrides is not None
        assert v.llm_overrides["provider"] == "deepseek"
        assert v.llm_overrides["model"] == "deepseek-v4"
        assert v.llm_overrides["max_tokens"] == 4096
        assert v.llm_overrides["thinking"]["enabled"] is True
        assert v.llm_overrides["thinking"]["effort"] == "medium"

    def test_minimal_config_roundtrip(self, tmp_path: Path) -> None:
        config = _make_minimal_config()
        out_path = tmp_path / "test_min.json"
        dump_experiment_config(config, out_path)
        loaded = load_experiment_config(out_path)

        assert loaded.experiment_name == "test_min"
        assert loaded.description is None
        assert loaded.selection.gt_found_max_drop_points is None
        assert len(loaded.variants) == 1
        v = loaded.variants[0]
        assert v.llm_overrides is None
        assert v.description is None
        assert v.additional_context is None

    def test_null_overrides_roundtrip(self, tmp_path: Path) -> None:
        config = _make_minimal_config()
        out_path = tmp_path / "test_null_ov.json"
        dump_experiment_config(config, out_path)

        raw = json.loads(out_path.read_text(encoding="utf-8"))
        assert raw["variants"][0]["llm_overrides"] is None

        loaded = load_experiment_config(out_path)
        assert loaded.variants[0].llm_overrides is None

    def test_payload_shape_has_required_keys(self) -> None:
        config = _make_full_config()
        payload = experiment_config_to_payload(config)

        assert "experiment_name" in payload
        assert "target_file" in payload
        assert "baseline_run_dir" in payload
        assert "candidate_generation" in payload
        assert "optimization_scope" in payload
        assert "reporting" in payload
        assert "selection" in payload
        assert "variants" in payload
        assert len(payload["variants"]) == 1

        v = payload["variants"][0]
        assert "variant_id" in v
        assert "llm_config" in v
        assert "iterations" in v

    def test_payload_omits_none_description(self) -> None:
        config = _make_minimal_config()
        payload = experiment_config_to_payload(config)
        assert payload["description"] is None
        assert payload["variants"][0]["description"] is None
        assert payload["variants"][0]["additional_context"] is None
        assert payload["selection"]["gt_found_max_drop_points"] is None

    def test_descriptions_null_in_json(self, tmp_path: Path) -> None:
        config = _make_minimal_config()
        out_path = tmp_path / "test_null_desc.json"
        dump_experiment_config(config, out_path)
        raw = json.loads(out_path.read_text(encoding="utf-8"))
        assert raw["description"] is None
        assert raw["variants"][0]["description"] is None


class TestConfigDiscovery:
    def test_list_includes_root_configs(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True, exist_ok=True)
        exp_dir = root / "configs" / "experiments"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "test_a.json").write_text("{}", encoding="utf-8")

        paths = list_experiment_config_paths(root)
        names = {p.name for p in paths}
        assert "test_a.json" in names

    def test_list_includes_templates(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True, exist_ok=True)
        exp_dir = root / "configs" / "experiments"
        tmpl_dir = exp_dir / "templates"
        tmpl_dir.mkdir(parents=True, exist_ok=True)
        (tmpl_dir / "sample.template.json").write_text("{}", encoding="utf-8")

        paths = list_experiment_config_paths(root)
        names = {p.name for p in paths}
        assert "sample.template.json" in names

    def test_list_includes_local(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True, exist_ok=True)
        exp_dir = root / "configs" / "experiments"
        local_dir = exp_dir / "local"
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "my_exp.json").write_text("{}", encoding="utf-8")

        paths = list_experiment_config_paths(root)
        names = {p.name for p in paths}
        assert "my_exp.json" in names

    def test_list_returns_all_together(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        (root / ".git").mkdir(parents=True, exist_ok=True)
        exp_dir = root / "configs" / "experiments"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "root_config.json").write_text("{}", encoding="utf-8")
        (exp_dir / "templates").mkdir(parents=True, exist_ok=True)
        (exp_dir / "templates" / "tmpl.template.json").write_text("{}", encoding="utf-8")
        (exp_dir / "local").mkdir(parents=True, exist_ok=True)
        (exp_dir / "local" / "local_config.json").write_text("{}", encoding="utf-8")

        paths = list_experiment_config_paths(root)
        names = {p.name for p in paths}
        assert "root_config.json" in names
        assert "tmpl.template.json" in names
        assert "local_config.json" in names
