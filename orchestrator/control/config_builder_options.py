"""Option discovery helpers for the TUI config builder."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.shared.io.json_io import read_json

from .project_paths import get_project_paths
from .results_browser import list_run_items
from .solver_manifests import list_solver_manifest_options


@dataclass(frozen=True)
class ConfigBuilderSolverOption:
    display_label: str
    solver_id: str
    default_target_file: str | None
    default_allowed_files: tuple[str, ...]


def list_config_builder_solver_options() -> list[ConfigBuilderSolverOption]:
    """Return solver options backed by solver manifests."""

    paths = get_project_paths()
    return [
        ConfigBuilderSolverOption(
            display_label=option.display_label,
            solver_id=option.solver_id,
            default_target_file=option.default_target_file,
            default_allowed_files=option.default_allowed_files,
        )
        for option in list_solver_manifest_options(paths.repo_root)
    ]


def discover_llm_configs() -> list[tuple[str, str]]:
    """Discover LLM config files under ``configs/llm_*.json``."""

    paths = get_project_paths()
    options: list[tuple[str, str]] = []
    for llm_path in sorted(paths.configs.glob("llm_*.json")):
        rel = str(llm_path.relative_to(paths.repo_root)).replace("\\", "/")
        options.append((rel, rel))
    return options


def discover_template_configs() -> list[Path]:
    paths = get_project_paths()
    template_dir = paths.experiments_config / "templates"
    if not template_dir.is_dir():
        return []
    return sorted(template_dir.glob("*.template.json"))


def discover_local_configs() -> list[Path]:
    paths = get_project_paths()
    local_dir = paths.experiments_config / "local"
    if not local_dir.is_dir():
        return []
    return sorted(local_dir.glob("*.json"))


def safe_config_stem(name: str) -> str:
    """Normalize *name* to a lowercase filesystem-safe config stem."""

    if not name or not name.strip():
        return "experiment_config"
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip())
    safe = re.sub(r"_+", "_", safe)
    return safe.strip("_").lower() or "experiment_config"


def _json_object_or_empty(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _status_from_run(item: Any) -> str | None:
    status_payload = _json_object_or_empty(getattr(item.artifacts, "status_json", None))
    for key in ("overall_status", "status"):
        value = status_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    status = getattr(item, "status", None)
    return status if isinstance(status, str) and status.strip() else None


def _solver_from_run(item: Any) -> str | None:
    metadata = _json_object_or_empty(getattr(item.artifacts, "metadata_json", None))
    metrics = _json_object_or_empty(getattr(item.artifacts, "metrics_json", None))
    benchmark = metrics.get("benchmark") if isinstance(metrics.get("benchmark"), dict) else {}
    for value in (
        benchmark.get("solver") if isinstance(benchmark, dict) else None,
        metadata.get("solver_id"),
        metadata.get("baseline"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_success_status(status: str | None) -> bool:
    return status is not None and status.lower() in {"success", "succeeded", "completed"}


def _looks_like_candidate_item(item: Any) -> bool:
    if "/" in getattr(item, "name", "").replace("\\", "/"):
        return True
    path = getattr(item, "path", None)
    if not isinstance(path, Path):
        return False
    if (path / "candidate.json").exists() or (path / "llm_request.json").exists():
        return True
    status_payload = _json_object_or_empty(getattr(item.artifacts, "status_json", None))
    scenario = status_payload.get("scenario")
    return isinstance(scenario, str) and scenario != "baseline"


def discover_baseline_runs(solver_id: str | None = None) -> list[tuple[str, str]]:
    """Discover successful baseline runs, filtered by solver when supplied."""

    paths = get_project_paths()
    try:
        run_items = list_run_items(paths.repo_root)
    except Exception:
        run_items = []
    matching: list[tuple[str, str]] = []
    unknown_solver: list[tuple[str, str]] = []
    fallback: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in run_items:
        if _looks_like_candidate_item(item):
            continue
        status = _status_from_run(item)
        if not _is_success_status(status):
            continue
        run_solver = _solver_from_run(item)
        if solver_id and run_solver is not None and run_solver != solver_id:
            continue
        try:
            rel = str(item.path.relative_to(paths.repo_root)).replace("\\", "/")
        except ValueError:
            continue
        if rel in seen:
            continue
        seen.add(rel)
        solver_label = run_solver if run_solver is not None else "unknown solver"
        option = (f"{rel} [{status or '?'}] [{solver_label}]", rel)
        if solver_id and run_solver == solver_id:
            matching.append(option)
        elif run_solver is None:
            unknown_solver.append(option)
        else:
            fallback.append(option)
    options = (matching or unknown_solver) if solver_id else [*matching, *unknown_solver, *fallback]
    if not options:
        options.append(("No matching baseline found. Run Baseline first or enter custom path", ""))
    return options
