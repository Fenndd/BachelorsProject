"""Experiment config loading and validation for future multi-run experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.patching.scope_validation import (
    normalize_repo_path,
    validate_allowed_files_list,
)


class ExperimentConfigError(ValueError):
    """Raised when an experiment config file is missing or invalid."""


@dataclass(frozen=True)
class ExperimentPipelineConfig:
    generate_candidate: bool
    materialize_candidate: bool
    verify_candidate: bool


@dataclass(frozen=True)
class CandidateGenerationConfig:
    max_source_chars: int


@dataclass(frozen=True)
class CandidateFormatConfig:
    type: str
    source_presentation: str
    require_original_verification: bool
    allow_exact_search_fallback: bool


@dataclass(frozen=True)
class HistoryPolicyConfig:
    enabled: bool
    scope: str
    max_previous_iterations: int
    include_failed_iterations: bool
    include_materialization_results: bool
    include_verification_results: bool


@dataclass(frozen=True)
class SelectionConfig:
    enabled: bool
    baseline_run_dir: str | None
    write_candidate_decisions: bool


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
    pipeline: ExperimentPipelineConfig
    candidate_generation: CandidateGenerationConfig
    candidate_format: CandidateFormatConfig
    history_policy: HistoryPolicyConfig
    selection: SelectionConfig
    optimization_scope: OptimizationScopeConfig
    variants: list[ExperimentVariantConfig]
    llm_config: str | None = None
    iterations: int | None = None
    additional_context: str | None = None


def load_experiment_config(path: Path | str) -> ExperimentConfig:
    """Load and validate an experiment config JSON file."""

    config_path = Path(path)
    if not config_path.exists():
        raise ExperimentConfigError(f"Experiment config file not found: {config_path}")
    if not config_path.is_file():
        raise ExperimentConfigError(f"Experiment config path is not a file: {config_path}")

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
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

    return ExperimentConfig(
        experiment_name=_required_non_empty_string(payload, "experiment_name"),
        description=_optional_string(payload, "description"),
        target_file=target_file,
        pipeline=_load_pipeline(payload),
        candidate_generation=_load_candidate_generation(payload),
        candidate_format=_load_candidate_format(payload),
        history_policy=_load_history_policy(payload),
        selection=_load_selection(payload),
        optimization_scope=optimization_scope,
        variants=_load_variants(payload),
        llm_config=(
            payload.get("llm_config") if isinstance(payload.get("llm_config"), str) else None
        ),
        iterations=payload.get("iterations") if isinstance(payload.get("iterations"), int) else None,
        additional_context=_optional_string(payload, "additional_context"),
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


def _load_pipeline(payload: dict[str, Any]) -> ExperimentPipelineConfig:
    pipeline = payload.get("pipeline")
    if not isinstance(pipeline, dict):
        raise ExperimentConfigError("Field 'pipeline' must be an object.")

    return ExperimentPipelineConfig(
        generate_candidate=_required_bool(pipeline, "generate_candidate"),
        materialize_candidate=_required_bool(pipeline, "materialize_candidate"),
        verify_candidate=_required_bool(pipeline, "verify_candidate"),
    )


def _load_candidate_generation(payload: dict[str, Any]) -> CandidateGenerationConfig:
    candidate_generation = payload.get("candidate_generation")
    if not isinstance(candidate_generation, dict):
        raise ExperimentConfigError("Field 'candidate_generation' must be an object.")

    return CandidateGenerationConfig(
        max_source_chars=_required_positive_int(
            candidate_generation, "max_source_chars"
        )
    )


def _load_candidate_format(payload: dict[str, Any]) -> CandidateFormatConfig:
    candidate_format = payload.get("candidate_format")
    if candidate_format is None:
        return CandidateFormatConfig(
            type="unified_diff",
            source_presentation="plain",
            require_original_verification=True,
            allow_exact_search_fallback=True,
        )

    if not isinstance(candidate_format, dict):
        raise ExperimentConfigError("Field 'candidate_format' must be an object.")

    format_type = _required_non_empty_string(candidate_format, "type")
    if format_type not in {"unified_diff", "line_range_edits"}:
        raise ExperimentConfigError(
            "Field 'candidate_format.type' must be one of: "
            "unified_diff, line_range_edits."
        )

    source_presentation = _required_non_empty_string(
        candidate_format,
        "source_presentation",
    )
    if source_presentation not in {"plain", "line_numbered"}:
        raise ExperimentConfigError(
            "Field 'candidate_format.source_presentation' must be one of: "
            "plain, line_numbered."
        )

    if format_type == "unified_diff" and source_presentation != "plain":
        raise ExperimentConfigError(
            "candidate_format.type='unified_diff' requires "
            "candidate_format.source_presentation='plain'."
        )
    if format_type == "line_range_edits" and source_presentation != "line_numbered":
        raise ExperimentConfigError(
            "candidate_format.type='line_range_edits' requires "
            "candidate_format.source_presentation='line_numbered'."
        )

    return CandidateFormatConfig(
        type=format_type,
        source_presentation=source_presentation,
        require_original_verification=_required_bool(
            candidate_format,
            "require_original_verification",
        ),
        allow_exact_search_fallback=_required_bool(
            candidate_format,
            "allow_exact_search_fallback",
        ),
    )


def _load_history_policy(payload: dict[str, Any]) -> HistoryPolicyConfig:
    history_policy = payload.get("history_policy")
    if history_policy is None:
        return HistoryPolicyConfig(
            enabled=False,
            scope="variant",
            max_previous_iterations=0,
            include_failed_iterations=False,
            include_materialization_results=True,
            include_verification_results=True,
        )

    if not isinstance(history_policy, dict):
        raise ExperimentConfigError("Field 'history_policy' must be an object.")

    enabled = _required_bool(history_policy, "enabled")
    scope = _required_non_empty_string(history_policy, "scope")
    if scope != "variant":
        raise ExperimentConfigError(
            "Field 'history_policy.scope' must be 'variant'."
        )

    max_previous_iterations = _required_non_negative_int(
        history_policy, "max_previous_iterations"
    )
    if enabled and max_previous_iterations <= 0:
        raise ExperimentConfigError(
            "Field 'history_policy.max_previous_iterations' must be positive "
            "when history_policy.enabled is true."
        )

    return HistoryPolicyConfig(
        enabled=enabled,
        scope=scope,
        max_previous_iterations=max_previous_iterations,
        include_failed_iterations=_required_bool(
            history_policy, "include_failed_iterations"
        ),
        include_materialization_results=_required_bool(
            history_policy, "include_materialization_results"
        ),
        include_verification_results=_required_bool(
            history_policy, "include_verification_results"
        ),
    )


def _load_selection(payload: dict[str, Any]) -> SelectionConfig:
    selection = payload.get("selection")
    if selection is None:
        return SelectionConfig(
            enabled=False,
            baseline_run_dir=None,
            write_candidate_decisions=True,
        )

    if not isinstance(selection, dict):
        raise ExperimentConfigError("Field 'selection' must be an object.")

    enabled = _required_bool(selection, "enabled")
    baseline_run_dir = _optional_string(selection, "baseline_run_dir")
    if enabled and baseline_run_dir is None:
        raise ExperimentConfigError(
            "Field 'selection.baseline_run_dir' is required when selection.enabled is true."
        )

    if "write_candidate_decisions" in selection:
        write_candidate_decisions = _required_bool(selection, "write_candidate_decisions")
    else:
        write_candidate_decisions = True

    return SelectionConfig(
        enabled=enabled,
        baseline_run_dir=baseline_run_dir,
        write_candidate_decisions=write_candidate_decisions,
    )


def _load_variants(payload: dict[str, Any]) -> list[ExperimentVariantConfig]:
    variants = payload.get("variants")
    if variants is None:
        return [
            ExperimentVariantConfig(
                variant_id="default",
                description=_optional_string(payload, "description"),
                llm_config=_required_non_empty_string(payload, "llm_config"),
                llm_overrides=_load_llm_overrides(payload),
                iterations=_required_positive_int(payload, "iterations"),
                additional_context=_optional_string(payload, "additional_context"),
            )
        ]

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
