"""Experiment config loading and validation for closed-loop experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.core.patching.scope_validation import (
    normalize_repo_path,
    validate_allowed_files_list,
)
from orchestrator.shared.io.json_io import read_json


class ExperimentConfigError(ValueError):
    """Raised when an experiment config file is missing or invalid."""


@dataclass(frozen=True)
class CandidateGenerationConfig:
    max_source_chars: int


@dataclass(frozen=True)
class ReportingConfig:
    enabled: bool = False
    formats: list[str] = field(default_factory=lambda: ["html", "pdf"])
    renderer: str = "auto"
    fail_on_error: bool = False


@dataclass(frozen=True)
class ExperimentVariantConfig:
    variant_id: str
    description: str | None
    llm_config: str
    llm_overrides: dict[str, Any] | None
    iterations: int
    additional_context: str | None


@dataclass(frozen=True)
class OptimizationScopeConfig:
    """Files that LLM candidates are allowed to modify in the optimization pipeline.

    The main pipeline enforces that candidate target_files and diff paths
    must be a subset of these allowed_files. Benchmark, adapter, validator,
    CMake, orchestrator, configs, docs, and tests are fixed infrastructure
    and must never appear in allowed_files.
    """

    allowed_files: list[str]


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_name: str
    description: str | None
    target_file: str
    baseline_run_dir: str
    candidate_generation: CandidateGenerationConfig
    optimization_scope: OptimizationScopeConfig
    variants: list[ExperimentVariantConfig]
    reporting: ReportingConfig = field(default_factory=ReportingConfig)


def load_experiment_config(path: Path | str) -> ExperimentConfig:
    """Load and validate an experiment config JSON file."""

    config_path = Path(path)
    if not config_path.exists():
        raise ExperimentConfigError(f"Experiment config file not found: {config_path}")
    if not config_path.is_file():
        raise ExperimentConfigError(f"Experiment config path is not a file: {config_path}")

    try:
        payload = read_json(config_path)
    except json.JSONDecodeError as exc:
        raise ExperimentConfigError(
            f"Experiment config is not valid JSON: {config_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise ExperimentConfigError(
            f"Could not read experiment config: {config_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise ExperimentConfigError("Experiment config must contain a JSON object.")

    target_file_raw = _required_non_empty_string(payload, "target_file")
    target_file = normalize_repo_path(target_file_raw)
    optimization_scope = _load_optimization_scope(payload, target_file)
    reporting = _load_reporting(payload)
    variants = _load_variants(payload)

    _validate_single_variant(variants)

    return ExperimentConfig(
        experiment_name=_required_non_empty_string(payload, "experiment_name"),
        description=_optional_string(payload, "description"),
        target_file=target_file,
        baseline_run_dir=_required_non_empty_string(payload, "baseline_run_dir"),
        candidate_generation=_load_candidate_generation(payload),
        reporting=reporting,
        optimization_scope=optimization_scope,
        variants=variants,
    )


def _required_non_empty_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ExperimentConfigError(
            f"Field '{field_name}' must be a non-empty string."
        )
    return value


def _optional_string(payload: dict[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExperimentConfigError(
            f"Field '{field_name}' must be null or a string."
        )
    return value


def _required_positive_int(payload: dict[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ExperimentConfigError(
            f"Field '{field_name}' must be a positive integer."
        )
    return value


def _required_bool(payload: dict[str, Any], field_name: str) -> bool:
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ExperimentConfigError(f"Field '{field_name}' must be a boolean.")
    return value


def _required_non_negative_int(payload: dict[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ExperimentConfigError(
            f"Field '{field_name}' must be a non-negative integer."
        )
    return value


def _load_llm_overrides(
    payload: dict[str, Any],
    field_name: str = "llm_overrides",
) -> dict[str, Any] | None:
    overrides = payload.get(field_name)
    if overrides is None:
        return None
    if not isinstance(overrides, dict):
        raise ExperimentConfigError(f"Field '{field_name}' must be an object.")

    allowed_keys = {
        "provider",
        "model",
        "base_url",
        "api_key_env",
        "thinking",
        "max_tokens",
    }
    unknown_keys = sorted(set(overrides) - allowed_keys)
    if unknown_keys:
        raise ExperimentConfigError(
            f"Field '{field_name}' contains unsupported key(s): "
            f"{', '.join(unknown_keys)}."
        )

    parsed: dict[str, Any] = {}
    for key in ["provider", "model", "base_url", "api_key_env"]:
        if key in overrides:
            value = overrides[key]
            if not isinstance(value, str) or not value.strip():
                raise ExperimentConfigError(
                    f"Field '{field_name}.{key}' must be a non-empty string."
                )
            parsed[key] = value

    if "max_tokens" in overrides:
        value = overrides["max_tokens"]
        if value is None:
            parsed["max_tokens"] = None
        elif not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ExperimentConfigError(
                f"Field '{field_name}.max_tokens' must be null or a positive integer."
            )
        else:
            parsed["max_tokens"] = value

    if "thinking" in overrides:
        thinking = overrides["thinking"]
        if not isinstance(thinking, dict):
            raise ExperimentConfigError(
                f"Field '{field_name}.thinking' must be an object."
            )
        unknown_thinking_keys = sorted(set(thinking) - {"enabled", "effort"})
        if unknown_thinking_keys:
            raise ExperimentConfigError(
                f"Field '{field_name}.thinking' contains unsupported key(s): "
                f"{', '.join(unknown_thinking_keys)}."
            )
        parsed_thinking: dict[str, Any] = {}
        if "enabled" in thinking:
            enabled = thinking["enabled"]
            if not isinstance(enabled, bool):
                raise ExperimentConfigError(
                    f"Field '{field_name}.thinking.enabled' must be a boolean."
                )
            parsed_thinking["enabled"] = enabled
        if "effort" in thinking:
            effort = thinking["effort"]
            if not isinstance(effort, str) or not effort.strip():
                raise ExperimentConfigError(
                    f"Field '{field_name}.thinking.effort' must be a non-empty string."
                )
            parsed_thinking["effort"] = effort
        parsed["thinking"] = parsed_thinking

    return parsed


def _load_candidate_generation(payload: dict[str, Any]) -> CandidateGenerationConfig:
    candidate_generation = payload.get("candidate_generation")
    if not isinstance(candidate_generation, dict):
        raise ExperimentConfigError("Field 'candidate_generation' must be an object.")

    return CandidateGenerationConfig(
        max_source_chars=_required_positive_int(
            candidate_generation, "max_source_chars"
        )
    )


def _load_reporting(payload: dict[str, Any]) -> ReportingConfig:
    reporting = payload.get("reporting")
    if reporting is None:
        return ReportingConfig()

    if not isinstance(reporting, dict):
        raise ExperimentConfigError("Field 'reporting' must be an object if present.")

    enabled = _required_bool(reporting, "enabled")
    fail_on_error = _required_bool(reporting, "fail_on_error")

    formats_raw = reporting.get("formats")
    if not isinstance(formats_raw, list) or not formats_raw:
        raise ExperimentConfigError(
            "Field 'reporting.formats' must be a non-empty list."
        )

    formats: list[str] = []
    for index, value in enumerate(formats_raw):
        if not isinstance(value, str):
            raise ExperimentConfigError(
                f"Field 'reporting.formats[{index}]' must be a string."
            )
        if value not in {"html", "pdf"}:
            raise ExperimentConfigError(
                "Field 'reporting.formats' may only contain: html, pdf."
            )
        if value not in formats:
            formats.append(value)

    renderer = _required_non_empty_string(reporting, "renderer")
    if renderer not in {"auto", "weasyprint", "playwright"}:
        raise ExperimentConfigError(
            "Field 'reporting.renderer' must be one of: "
            "auto, weasyprint, playwright."
        )

    return ReportingConfig(
        enabled=enabled,
        formats=formats,
        renderer=renderer,
        fail_on_error=fail_on_error,
    )


def _validate_single_variant(variants: list[ExperimentVariantConfig]) -> None:
    if len(variants) != 1:
        raise ExperimentConfigError(
            "Closed-loop experiments currently support exactly one variant."
        )


def _load_variants(payload: dict[str, Any]) -> list[ExperimentVariantConfig]:
    variants = payload.get("variants")
    if variants is None:
        raise ExperimentConfigError("Field 'variants' is required and must contain exactly one variant.")

    if not isinstance(variants, list) or not variants:
        raise ExperimentConfigError("Field 'variants' must be a non-empty list.")

    parsed_variants: list[ExperimentVariantConfig] = []
    seen_ids: set[str] = set()
    for index, variant in enumerate(variants):
        if not isinstance(variant, dict):
            raise ExperimentConfigError(
                f"Variant at index {index} must be an object."
            )

        variant_id = _required_non_empty_string(variant, "variant_id")
        if variant_id in seen_ids:
            raise ExperimentConfigError(
                f"Variant id must be unique; duplicate variant_id: {variant_id}"
            )
        seen_ids.add(variant_id)

        parsed_variants.append(
            ExperimentVariantConfig(
                variant_id=variant_id,
                description=_optional_string(variant, "description"),
                llm_config=_required_non_empty_string(variant, "llm_config"),
                llm_overrides=_load_llm_overrides(variant),
                iterations=_required_positive_int(variant, "iterations"),
                additional_context=_optional_string(variant, "additional_context"),
            )
        )

    return parsed_variants


def _load_optimization_scope(
    payload: dict[str, Any],
    target_file: str,
) -> OptimizationScopeConfig:
    """Load and validate the optional optimization_scope block.

    If the key is absent, create a default scope containing only target_file
    for backward compatibility.
    """
    scope_raw = payload.get("optimization_scope")
    if scope_raw is None:
        return OptimizationScopeConfig(allowed_files=[target_file])

    if not isinstance(scope_raw, dict):
        raise ExperimentConfigError("Field 'optimization_scope' must be an object if present.")

    allowed_files_raw = scope_raw.get("allowed_files")
    if allowed_files_raw is None:
        raise ExperimentConfigError(
            "Field 'optimization_scope.allowed_files' is required."
        )
    if not isinstance(allowed_files_raw, list) or not allowed_files_raw:
        raise ExperimentConfigError(
            "Field 'optimization_scope.allowed_files' must be a non-empty list."
        )

    try:
        allowed_files = validate_allowed_files_list(allowed_files_raw, "optimization_scope.allowed_files")
    except ValueError as exc:
        raise ExperimentConfigError(str(exc)) from exc

    if target_file not in allowed_files:
        raise ExperimentConfigError(
            f"Field 'target_file' ({target_file}) must be included in "
            f"optimization_scope.allowed_files. "
            f"Current allowed_files: {allowed_files}"
        )

    return OptimizationScopeConfig(allowed_files=allowed_files)
