"""Experiment planning and LLM configuration helpers."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .experiment_config import ExperimentConfig
from . import experiment_environment as env


def _total_iterations(config: ExperimentConfig) -> int:
    return config.iterations


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


def _resolve_llm_config(config: ExperimentConfig) -> dict[str, Any]:
    base_config_path = env._resolve_path(config.llm_config)
    base_config = env._read_json_file_object(base_config_path, "LLM config")
    return _apply_llm_overrides(base_config, config.llm_overrides)


def _llm_metadata(
    config: ExperimentConfig,
    resolved_config: dict[str, Any],
    resolved_config_path: Path | None,
) -> dict[str, Any]:
    thinking = resolved_config.get("thinking")
    thinking = thinking if isinstance(thinking, dict) else {}
    return {
        "base_config": config.llm_config,
        "resolved_config": (
            env._display_path(resolved_config_path) if resolved_config_path is not None else None
        ),
        "provider": resolved_config.get("provider"),
        "model": resolved_config.get("model"),
        "thinking_enabled": thinking.get("enabled"),
        "reasoning_effort": thinking.get("effort"),
        "max_tokens": resolved_config.get("max_tokens"),
    }


def _resolved_llm_config_path(experiment_dir: Path) -> Path:
    return experiment_dir / "resolved_llm_config.json"


def _write_resolved_llm_config(
    experiment_dir: Path,
    config: ExperimentConfig,
) -> dict[str, Any]:
    resolved_config = _resolve_llm_config(config)
    resolved_config_path = _resolved_llm_config_path(experiment_dir)
    env._write_json(resolved_config_path, resolved_config)
    return _llm_metadata(config, resolved_config, resolved_config_path)


def _print_plan(config: ExperimentConfig, dry_run: bool) -> None:
    print("Experiment dry run" if dry_run else "Experiment plan")
    print(f"Experiment name: {config.experiment_name}")
    print(f"Description: {config.description or 'none'}")
    print(f"Target file: {config.target_file}")
    print("Mode: closed-loop optimization")
    print(f"Baseline run dir: {config.baseline_run_dir}")
    print(
        f"Optimization scope allowed files: "
        f"{config.optimization_scope.allowed_files}"
    )
    resolved_llm_config = _resolve_llm_config(config)
    llm_metadata = _llm_metadata(config, resolved_llm_config, None)
    print("")
    print(f"LLM config: {config.llm_config}")
    print(
        "LLM overrides: "
        + (
            json.dumps(config.llm_overrides, ensure_ascii=False, sort_keys=True)
            if config.llm_overrides is not None
            else "none"
        )
    )
    print(f"Effective provider: {llm_metadata['provider']}")
    print(f"Effective model: {llm_metadata['model']}")
    print(f"Effective thinking.enabled: {llm_metadata['thinking_enabled']}")
    print(f"Effective thinking.effort: {llm_metadata['reasoning_effort']}")
    print(f"Effective max_tokens: {llm_metadata['max_tokens']}")
    print(f"Iterations: {config.iterations}")
    print(f"Additional context: {config.additional_context or 'none'}")
    print("")
    print(f"Total planned iterations: {_total_iterations(config)}")
    if dry_run:
        print("")
        print("Dry run only: no LLM requests, candidates, materialization, or verification were run.")


def _write_effective_experiment_config(experiment_dir: Path, config: ExperimentConfig) -> Path:
    path = experiment_dir / "experiment_config_effective.json"
    env._write_json(path, env._portable_plain_dict(asdict(config)))
    return path
