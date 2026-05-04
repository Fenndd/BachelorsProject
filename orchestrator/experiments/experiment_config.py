"""Experiment config loading and validation for future multi-run experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
class ExperimentVariantConfig:
    variant_id: str
    description: str | None
    llm_config: str
    iterations: int
    additional_context: str | None


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_name: str
    description: str | None
    target_file: str
    pipeline: ExperimentPipelineConfig
    candidate_generation: CandidateGenerationConfig
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

    return ExperimentConfig(
        experiment_name=_required_non_empty_string(payload, "experiment_name"),
        description=_optional_string(payload, "description"),
        target_file=_required_non_empty_string(payload, "target_file"),
        pipeline=_load_pipeline(payload),
        candidate_generation=_load_candidate_generation(payload),
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


def _load_variants(payload: dict[str, Any]) -> list[ExperimentVariantConfig]:
    variants = payload.get("variants")
    if variants is None:
        return [
            ExperimentVariantConfig(
                variant_id="default",
                description=_optional_string(payload, "description"),
                llm_config=_required_non_empty_string(payload, "llm_config"),
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
                iterations=_required_positive_int(variant, "iterations"),
                additional_context=_optional_string(variant, "additional_context"),
            )
        )

    return parsed_variants
