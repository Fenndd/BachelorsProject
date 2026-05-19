"""Read-only experiment config summaries for the control layer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from orchestrator.experiments.experiment_config import (
    ExperimentConfigError,
    load_experiment_config,
)

from .project_paths import get_project_paths, resolve_project_path


ConfigStatus = Literal["ok", "invalid"]


@dataclass(frozen=True)
class ExperimentConfigSummary:
    path: Path
    name: str
    description: str | None
    target_file: str | None
    variants_count: int | None
    total_iterations: int | None
    candidate_format: str | None
    source_presentation: str | None
    baseline_run_dir: str | None
    reporting_enabled: bool | None
    providers: list[str]
    models: list[str]
    status: ConfigStatus
    message: str | None


def list_experiment_config_paths(repo_root: Path | None = None) -> list[Path]:
    paths = get_project_paths(repo_root)
    if not paths.experiments_config.is_dir():
        return []
    return sorted(paths.experiments_config.glob("*.json"))


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Experiment config must contain a JSON object.")
    return payload


def _resolve_config_path(path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return resolve_project_path(path)


def _read_llm_config(path_text: str | None, config_path: Path) -> dict[str, Any]:
    if not path_text:
        return {}
    llm_path = Path(path_text)
    if not llm_path.is_absolute():
        llm_path = get_project_paths(config_path).repo_root / llm_path
    try:
        return _read_json_object(llm_path)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _append_unique(values: list[str], value: object) -> None:
    if isinstance(value, str) and value.strip() and value not in values:
        values.append(value)


def _provider_models_from_payload(payload: dict[str, Any], config_path: Path) -> tuple[list[str], list[str]]:
    providers: list[str] = []
    models: list[str] = []
    variants = payload.get("variants")
    if isinstance(variants, list) and variants:
        variant_payloads = [variant for variant in variants if isinstance(variant, dict)]
    else:
        variant_payloads = [payload]

    for variant in variant_payloads:
        llm_config = _read_llm_config(
            variant.get("llm_config") if isinstance(variant.get("llm_config"), str) else payload.get("llm_config"),
            config_path,
        )
        overrides = variant.get("llm_overrides")
        provider = llm_config.get("provider")
        model = llm_config.get("model")
        if isinstance(overrides, dict):
            provider = overrides.get("provider", provider)
            model = overrides.get("model", model)
        _append_unique(providers, provider)
        _append_unique(models, model)
    return providers, models


def _summary_from_payload(
    path: Path,
    payload: dict[str, Any],
    status: ConfigStatus,
    message: str | None,
) -> ExperimentConfigSummary:
    variants = payload.get("variants")
    variant_payloads = variants if isinstance(variants, list) else None
    variants_count = len(variant_payloads) if variant_payloads is not None else 1
    if variant_payloads is not None:
        iterations = [
            variant.get("iterations")
            for variant in variant_payloads
            if isinstance(variant, dict) and isinstance(variant.get("iterations"), int)
        ]
        total_iterations = sum(iterations) if len(iterations) == len(variant_payloads) else None
    else:
        total_iterations = payload.get("iterations") if isinstance(payload.get("iterations"), int) else None

    candidate_format = payload.get("candidate_format")
    if isinstance(candidate_format, dict):
        format_type = candidate_format.get("type") if isinstance(candidate_format.get("type"), str) else None
        source_presentation = (
            candidate_format.get("source_presentation")
            if isinstance(candidate_format.get("source_presentation"), str)
            else None
        )
    else:
        format_type = "unified_diff"
        source_presentation = "plain"

    reporting = payload.get("reporting")
    providers, models = _provider_models_from_payload(payload, path)
    return ExperimentConfigSummary(
        path=path,
        name=payload.get("experiment_name") if isinstance(payload.get("experiment_name"), str) else path.stem,
        description=payload.get("description") if isinstance(payload.get("description"), str) else None,
        target_file=payload.get("target_file") if isinstance(payload.get("target_file"), str) else None,
        variants_count=variants_count,
        total_iterations=total_iterations,
        candidate_format=format_type,
        source_presentation=source_presentation,
        baseline_run_dir=payload.get("baseline_run_dir") if isinstance(payload.get("baseline_run_dir"), str) else None,
        reporting_enabled=reporting.get("enabled") if isinstance(reporting, dict) and isinstance(reporting.get("enabled"), bool) else False,
        providers=providers,
        models=models,
        status=status,
        message=message,
    )


def read_experiment_config_summary(path: Path) -> ExperimentConfigSummary:
    config_path = _resolve_config_path(path)
    try:
        config = load_experiment_config(config_path)
        payload = _read_json_object(config_path)
        providers, models = _provider_models_from_payload(payload, config_path)
        return ExperimentConfigSummary(
            path=config_path,
            name=config.experiment_name,
            description=config.description,
            target_file=config.target_file,
            variants_count=len(config.variants),
            total_iterations=sum(variant.iterations for variant in config.variants),
            candidate_format=config.candidate_format.type,
            source_presentation=config.candidate_format.source_presentation,
            baseline_run_dir=config.baseline_run_dir,
            reporting_enabled=config.reporting.enabled,
            providers=providers,
            models=models,
            status="ok",
            message=None,
        )
    except (ExperimentConfigError, OSError, json.JSONDecodeError, ValueError) as exc:
        try:
            payload = _read_json_object(config_path)
        except (OSError, json.JSONDecodeError, ValueError):
            return ExperimentConfigSummary(
                path=config_path,
                name=config_path.stem,
                description=None,
                target_file=None,
                variants_count=None,
                total_iterations=None,
                candidate_format=None,
                source_presentation=None,
                baseline_run_dir=None,
                reporting_enabled=None,
                providers=[],
                models=[],
                status="invalid",
                message=str(exc),
            )
        return _summary_from_payload(config_path, payload, "invalid", str(exc))


def list_experiment_config_summaries(repo_root: Path | None = None) -> list[ExperimentConfigSummary]:
    return [
        read_experiment_config_summary(path)
        for path in list_experiment_config_paths(repo_root)
    ]
