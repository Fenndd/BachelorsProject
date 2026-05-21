"""Experiment planning and LLM configuration helpers."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .experiment_config import ExperimentConfig, ExperimentVariantConfig
from . import experiment_environment as env


def _safe_artifact_name(value: str) -> str:
    lowered = value.lower()
    separated = re.sub(r"[\s/\\]+", "_", lowered)
    safe = re.sub(r"[^a-z0-9_-]+", "_", separated)
    compacted = re.sub(r"_+", "_", safe).strip("_-")
    return compacted or "experiment"


def _total_iterations(config: ExperimentConfig) -> int:
    return sum(variant.iterations for variant in config.variants)


def _apply_llm_overrides(
    base_config: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    resolved = copy.deepcopy(base_config)
    if overrides is None:
        return resolved

    for key, value in overrides.items():
        if key == "thinking":
            current = resolved.get("thinking")
            resolved_thinking = copy.deepcopy(current) if isinstance(current, dict) else {}
            resolved_thinking.update(copy.deepcopy(value))
            resolved["thinking"] = resolved_thinking
        elif value is None:
            resolved.pop(key, None)
        else:
            resolved[key] = copy.deepcopy(value)
    return resolved


def _resolve_variant_llm_config(variant: ExperimentVariantConfig) -> dict[str, Any]:
    base_config_path = env._resolve_path(variant.llm_config)
    base_config = env._read_json_file_object(base_config_path, "LLM config")
    return _apply_llm_overrides(base_config, variant.llm_overrides)


def _llm_metadata(
    variant: ExperimentVariantConfig,
    resolved_config: dict[str, Any],
    resolved_config_path: Path | None,
) -> dict[str, Any]:
    thinking = resolved_config.get("thinking")
    thinking = thinking if isinstance(thinking, dict) else {}
    return {
        "base_config": variant.llm_config,
        "resolved_config": (
            env._display_path(resolved_config_path) if resolved_config_path is not None else None
        ),
        "provider": resolved_config.get("provider"),
        "model": resolved_config.get("model"),
        "thinking_enabled": thinking.get("enabled"),
        "reasoning_effort": thinking.get("effort"),
        "max_tokens": resolved_config.get("max_tokens"),
    }


def _variant_llm_config_path(experiment_dir: Path, variant_id: str) -> Path:
    return (
        experiment_dir
        / "variant_configs"
        / f"{_safe_artifact_name(variant_id)}_llm_config.json"
    )


def _write_resolved_variant_llm_configs(
    experiment_dir: Path,
    config: ExperimentConfig,
) -> dict[str, dict[str, Any]]:
    variant_configs_dir = experiment_dir / "variant_configs"
    variant_configs_dir.mkdir(parents=True, exist_ok=True)
    metadata_by_variant: dict[str, dict[str, Any]] = {}
    for variant in config.variants:
        resolved_config = _resolve_variant_llm_config(variant)
        resolved_config_path = _variant_llm_config_path(experiment_dir, variant.variant_id)
        env._write_json(resolved_config_path, resolved_config)
        metadata_by_variant[variant.variant_id] = _llm_metadata(
            variant,
            resolved_config,
            resolved_config_path,
        )
    return metadata_by_variant


def _print_plan(config: ExperimentConfig, dry_run: bool) -> None:
    candidate_generation = config.candidate_generation

    print("Experiment dry run" if dry_run else "Experiment plan")
    print(f"Experiment name: {config.experiment_name}")
    print(f"Description: {config.description or 'none'}")
    print(f"Target file: {config.target_file}")
    print("Mode: closed-loop optimization")
    print(f"Baseline run dir: {config.baseline_run_dir}")
    print(f"Max source chars: {candidate_generation.max_source_chars}")
    print(
        f"Optimization scope allowed files: "
        f"{config.optimization_scope.allowed_files}"
    )
    print(f"Variants: {len(config.variants)}")
    for variant in config.variants:
        resolved_llm_config = _resolve_variant_llm_config(variant)
        llm_metadata = _llm_metadata(variant, resolved_llm_config, None)
        print("")
        print(f"Variant: {variant.variant_id}")
        print(f"- description: {variant.description or 'none'}")
        print(f"- base llm_config: {variant.llm_config}")
        print(
            "- llm_overrides: "
            + (
                json.dumps(variant.llm_overrides, ensure_ascii=False, sort_keys=True)
                if variant.llm_overrides is not None
                else "none"
            )
        )
        print(f"- effective provider: {llm_metadata['provider']}")
        print(f"- effective model: {llm_metadata['model']}")
        print(f"- effective thinking.enabled: {llm_metadata['thinking_enabled']}")
        print(f"- effective thinking.effort: {llm_metadata['reasoning_effort']}")
        print(f"- effective max_tokens: {llm_metadata['max_tokens']}")
        print(f"- iterations: {variant.iterations}")
        print(f"- additional_context: {variant.additional_context or 'none'}")
    print("")
    print(f"Total planned iterations: {_total_iterations(config)}")
    if dry_run:
        print("")
        print("Dry run only: no LLM requests, candidates, materialization, or verification were run.")


def _write_effective_experiment_config(experiment_dir: Path, config: ExperimentConfig) -> Path:
    path = experiment_dir / "experiment_config_effective.json"
    env._write_json(path, env._portable_plain_dict(asdict(config)))
    return path
