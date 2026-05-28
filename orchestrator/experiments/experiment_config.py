"""Experiment config loading and validation for closed-loop experiments."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.core.patching.scope_validation import (
    normalize_repo_path,
    validate_allowed_files_list,
)
from orchestrator.core.benchmarking.solver_registry import (
    default_solver_descriptor,
    get_solver_descriptor,
)
from orchestrator.shared.io.json_io import read_json
from orchestrator.paths import paths


class ExperimentConfigError(ValueError):
    """Raised when an experiment config file is missing or invalid."""


@dataclass(frozen=True)
class ReportingConfig:
    enabled: bool = False
    formats: list[str] = field(default_factory=lambda: ["html", "pdf"])
    renderer: str = "auto"


@dataclass(frozen=True)
class SelectionPolicyConfig:
    gt_found_max_drop_points: float | None = None


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
    optimization_scope: OptimizationScopeConfig
    llm_config: str
    llm_overrides: dict[str, Any] | None
    iterations: int
    additional_context: str | None
    reporting: ReportingConfig = field(default_factory=ReportingConfig)
    selection: SelectionPolicyConfig = field(default_factory=SelectionPolicyConfig)
    solver_id: str = "lambdatwist_p3p"


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

    return _build_experiment_config(payload, config_path)


def validate_experiment_config_dict(payload: dict[str, Any]) -> ExperimentConfig:
    """Validate a payload dict and return ExperimentConfig without a file on disk."""
    if not isinstance(payload, dict):
        raise ExperimentConfigError("Experiment config must contain a JSON object.")
    return _build_experiment_config(payload, paths.repo_root / "_virtual.json")


def _build_experiment_config(
    payload: dict[str, Any],
    config_path: Path,
) -> ExperimentConfig:
    """Parse and validate a payload dict into an ExperimentConfig."""
    solver_id = _optional_string(payload, "solver_id")
    try:
        solver_descriptor = (
            get_solver_descriptor(solver_id)
            if solver_id is not None
            else default_solver_descriptor()
        )
    except KeyError as exc:
        raise ExperimentConfigError(str(exc)) from exc
    target_file_raw = payload.get("target_file")
    if target_file_raw is None:
        if not solver_descriptor.default_target_file:
            raise ExperimentConfigError(
                "Field 'target_file' is required when the selected solver descriptor "
                "does not define default_target_file."
            )
        target_file = normalize_repo_path(solver_descriptor.default_target_file)
    else:
        if not isinstance(target_file_raw, str) or not target_file_raw.strip():
            raise ExperimentConfigError(
                "Field 'target_file' must be a non-empty string."
            )
        target_file = normalize_repo_path(target_file_raw)
    default_allowed_files = list(solver_descriptor.default_allowed_files) or [target_file]
    optimization_scope = _load_optimization_scope(
        payload,
        target_file,
        default_allowed_files,
    )
    reporting = _load_reporting(payload)
    selection = _load_selection(payload)
    llm_config, llm_overrides, iterations, additional_context = _load_experiment_llm_fields(payload)
    baseline_run_dir = _required_non_empty_string(payload, "baseline_run_dir")
    _validate_baseline_solver_match(
        baseline_run_dir,
        config_path,
        solver_descriptor.solver_id,
    )

    return ExperimentConfig(
        experiment_name=_required_non_empty_string(payload, "experiment_name"),
        description=_optional_string(payload, "description"),
        solver_id=solver_descriptor.solver_id,
        target_file=target_file,
        baseline_run_dir=baseline_run_dir,
        reporting=reporting,
        selection=selection,
        optimization_scope=optimization_scope,
        llm_config=llm_config,
        llm_overrides=llm_overrides,
        iterations=iterations,
        additional_context=additional_context,
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


def _load_reporting(payload: dict[str, Any]) -> ReportingConfig:
    reporting = payload.get("reporting")
    if reporting is None:
        return ReportingConfig()

    if not isinstance(reporting, dict):
        raise ExperimentConfigError("Field 'reporting' must be an object if present.")

    enabled = _required_bool(reporting, "enabled")

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
    )


def _load_selection(payload: dict[str, Any]) -> SelectionPolicyConfig:
    selection = payload.get("selection")
    if selection is None:
        return SelectionPolicyConfig()
    if not isinstance(selection, dict):
        raise ExperimentConfigError("Field 'selection' must be an object if present.")

    value = selection.get("gt_found_max_drop_points")
    if value is None:
        return SelectionPolicyConfig(gt_found_max_drop_points=None)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ExperimentConfigError(
            "Field 'selection.gt_found_max_drop_points' must be null or a "
            "finite non-negative number."
        )
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0.0:
        raise ExperimentConfigError(
            "Field 'selection.gt_found_max_drop_points' must be null or a "
            "finite non-negative number."
        )
    return SelectionPolicyConfig(gt_found_max_drop_points=numeric)


def _validate_baseline_solver_match(
    baseline_run_dir: str,
    config_path: Path,
    solver_id: str,
) -> None:
    baseline_dir = _resolve_existing_baseline_dir(baseline_run_dir, config_path)
    if baseline_dir is None:
        return
    baseline_solver_id = _baseline_solver_id_from_artifacts(baseline_dir)
    if baseline_solver_id is None:
        return
    if baseline_solver_id != solver_id:
        raise ExperimentConfigError(
            "Field 'baseline_run_dir' points to a baseline produced by a "
            "different solver_id: "
            f"baseline={baseline_solver_id!r}, config={solver_id!r}."
        )


def _resolve_existing_baseline_dir(
    baseline_run_dir: str,
    config_path: Path,
) -> Path | None:
    raw_path = Path(baseline_run_dir)
    candidates = [raw_path] if raw_path.is_absolute() else [
        paths.repo_root / raw_path,
        config_path.parent / raw_path,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _baseline_solver_id_from_artifacts(baseline_dir: Path) -> str | None:
    metadata = _safe_read_json_object(baseline_dir / "metadata.json")
    if metadata is not None:
        solver_id = _string_value(metadata.get("solver_id"))
        if solver_id is not None:
            return solver_id
        baseline = _string_value(metadata.get("baseline"))
        if baseline is not None:
            return baseline

    metrics = _safe_read_json_object(baseline_dir / "metrics.json")
    benchmark = metrics.get("benchmark") if isinstance(metrics, dict) else None
    if isinstance(benchmark, dict):
        return _string_value(benchmark.get("solver"))
    return None


def _safe_read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _load_experiment_llm_fields(
    payload: dict[str, Any],
) -> tuple[str, dict[str, Any] | None, int, str | None]:
    return (
        _required_non_empty_string(payload, "llm_config"),
        _load_llm_overrides(payload),
        _required_positive_int(payload, "iterations"),
        _optional_string(payload, "additional_context"),
    )


def _load_optimization_scope(
    payload: dict[str, Any],
    target_file: str,
    default_allowed_files: list[str],
) -> OptimizationScopeConfig:
    """Load and validate the optional optimization_scope block.

    If the key is absent, derive scope from solver default_allowed_files,
    falling back to target_file.
    """
    scope_raw = payload.get("optimization_scope")
    if scope_raw is None:
        allowed_files = validate_allowed_files_list(
            default_allowed_files,
            label="solver default_allowed_files",
        )
        if target_file not in allowed_files:
            allowed_files = [target_file, *allowed_files]
        return OptimizationScopeConfig(allowed_files=allowed_files)

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


def experiment_config_to_payload(config: ExperimentConfig) -> dict[str, Any]:
    """Convert an :class:`ExperimentConfig` to a JSON-serializable dict."""
    reporting = config.reporting

    payload: dict[str, Any] = {
        "experiment_name": config.experiment_name,
        "description": config.description,
        "solver_id": config.solver_id,
        "target_file": config.target_file,
        "baseline_run_dir": config.baseline_run_dir,
        "reporting": {
            "enabled": reporting.enabled,
            "formats": list(reporting.formats),
            "renderer": reporting.renderer,
        },
        "selection": {
            "gt_found_max_drop_points": config.selection.gt_found_max_drop_points,
        },
        "llm_config": config.llm_config,
        "llm_overrides": config.llm_overrides,
        "iterations": config.iterations,
        "additional_context": config.additional_context,
    }
    return payload


def dump_experiment_config(config: ExperimentConfig, path: Path | str) -> Path:
    """Serialize *config* to JSON, creating parent directories.

    The output can be read back with :func:`load_experiment_config`.
    Returns the written :class:`~pathlib.Path`.
    """
    from orchestrator.shared.io.json_io import write_json

    payload = experiment_config_to_payload(config)
    return write_json(path, payload)
