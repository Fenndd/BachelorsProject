"""Solver descriptor registry loaded from per-solver JSON manifests.

Each solver family registers one descriptor that maps a human-readable solver
identifier to the CMake target names, family label, runtime metadata, and
stdout parser needed for benchmark verification and final-selection reporting.

Manifests are discovered under ``cpp/bench/poselib_native/solvers/*.json``
relative to the repository root.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from orchestrator.core.benchmarking.family_benchmark_parser import parse_poselib_native_benchmark_output
from orchestrator.paths import get_project_paths


@dataclass(frozen=True)
class SolverBenchmarkDescriptor:
    """Immutable descriptor for one solver-family benchmark suite."""

    solver_id: str
    family: str
    benchmark_target: str
    adapter_validator_target: str | None
    benchmark_step_name: str
    adapter_validator_step_name: str | None
    parser: Callable[[str], dict[str, Any]]
    runtime_metric_key: str = "parsed_runtime_ns_per_problem_median"
    runtime_unit: str = "ns"
    benchmark_backend: str = "poselib_native"
    benchmark_solver_key: str | None = None
    benchmark_kind: str | None = None
    default_target_file: str | None = None
    default_allowed_files: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

_DEFAULT_SOLVER_ID = "poselib_p3p_lambdatwist"

_descriptors_cache: dict[str, SolverBenchmarkDescriptor] | None = None


def _family_parser(family: str) -> Callable[[str], dict[str, Any]]:
    """Return the stdout parser for a solver family."""
    if family == "poselib_native":
        return parse_poselib_native_benchmark_output
    raise ValueError(f"Unsupported solver family {family!r}. Supported family: poselib_native")


def _family_descriptor_label(family: str) -> str:
    """Map manifest family to descriptor family label."""
    if family == "poselib_native":
        return "poselib_native"
    raise ValueError(f"Unsupported solver family {family!r}. Supported family: poselib_native")


def _require_string(obj: dict[str, Any], key: str, source: Path) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"Manifest {source}: field {key!r} must be a non-empty string"
        )
    return value


def _require_dict(obj: dict[str, Any], key: str, source: Path) -> dict[str, Any]:
    value = obj.get(key)
    if not isinstance(value, dict):
        raise ValueError(
            f"Manifest {source}: field {key!r} must be a JSON object"
        )
    return value


def _require_string_list(obj: dict[str, Any], key: str, source: Path) -> tuple[str, ...]:
    value = obj.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(
            f"Manifest {source}: field {key!r} must be a non-empty list"
        )
    parsed: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise ValueError(
                f"Manifest {source}: field {key!r}[{index}] must be a non-empty string"
            )
        parsed.append(item)
    return tuple(parsed)


def _load_manifests() -> dict[str, SolverBenchmarkDescriptor]:
    """Discover and parse solver manifest files."""
    paths = get_project_paths()
    manifest_dir = paths.cpp / "bench" / "poselib_native" / "solvers"
    descriptors: dict[str, SolverBenchmarkDescriptor] = {}

    for manifest_path in sorted(manifest_dir.glob("*.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))

        solver_id = _require_string(data, "solver_id", manifest_path)
        family = _require_string(data, "family", manifest_path)
        targets = _require_dict(data, "targets", manifest_path)
        benchmark_backend = data.get("benchmark_backend", family)
        if not isinstance(benchmark_backend, str) or not benchmark_backend:
            raise ValueError(
                f"Manifest {manifest_path}: field 'benchmark_backend' must be a non-empty string"
            )

        _require_string(targets, "benchmark", manifest_path)

        if solver_id in descriptors:
            raise ValueError(
                f"Duplicate solver_id {solver_id!r} in {manifest_path}. "
                f"Already registered from another manifest."
            )

        if family != "poselib_native":
            raise ValueError(
                f"Unsupported family {family!r} in {manifest_path}. "
                "Supported family: poselib_native"
            )

        if benchmark_backend != "poselib_native":
            raise ValueError(
                f"Manifest {manifest_path}: poselib_native manifests must use "
                "benchmark_backend='poselib_native'"
            )
        benchmark_target = _require_string(data, "benchmark_target", manifest_path)
        benchmark_solver_key = _require_string(data, "benchmark_solver_key", manifest_path)
        benchmark_kind = _require_string(data, "benchmark_kind", manifest_path)
        default_target_file = _require_string(data, "default_target_file", manifest_path)
        default_allowed_files = _require_string_list(data, "default_allowed_files", manifest_path)
        if targets.get("benchmark") != benchmark_target:
            raise ValueError(
                f"Manifest {manifest_path}: targets.benchmark must match benchmark_target"
            )
        parser = _family_parser(family)

        descriptors[solver_id] = SolverBenchmarkDescriptor(
            solver_id=solver_id,
            family=_family_descriptor_label(family),
            benchmark_target=benchmark_target,
            adapter_validator_target=targets.get("adapter_validator"),
            benchmark_step_name=benchmark_target,
            adapter_validator_step_name=targets.get("adapter_validator"),
            parser=parser,
            runtime_metric_key="parsed_runtime_ns_per_problem_median",
            runtime_unit="ns",
            benchmark_backend=benchmark_backend,
            benchmark_solver_key=benchmark_solver_key,
            benchmark_kind=benchmark_kind,
            default_target_file=default_target_file,
            default_allowed_files=default_allowed_files,
        )

    return descriptors


def _descriptors() -> dict[str, SolverBenchmarkDescriptor]:
    """Lazy-initialized cache of solver descriptors."""
    global _descriptors_cache
    if _descriptors_cache is None:
        _descriptors_cache = _load_manifests()
    return _descriptors_cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_solver_descriptor(solver_id: str) -> SolverBenchmarkDescriptor:
    """Return the descriptor for *solver_id*.

    Raises :class:`KeyError` when the solver is not registered.
    """
    descriptors = _descriptors()
    if solver_id not in descriptors:
        raise KeyError(
            f"Unknown solver id {solver_id!r}. Registered solvers: "
            f"{sorted(descriptors.keys())}"
        )
    return descriptors[solver_id]


def default_solver_descriptor() -> SolverBenchmarkDescriptor:
    """Return the default solver descriptor used by the current pipeline."""
    descriptors = _descriptors()
    if _DEFAULT_SOLVER_ID in descriptors:
        return descriptors[_DEFAULT_SOLVER_ID]
    raise RuntimeError(
        f"Default solver {_DEFAULT_SOLVER_ID!r} is not registered. "
        f"Ensure a manifest exists with solver_id={_DEFAULT_SOLVER_ID!r} "
        "under cpp/bench/poselib_native/solvers/"
    )


def list_solver_descriptors() -> list[SolverBenchmarkDescriptor]:
    """Return every registered solver descriptor."""
    return list(_descriptors().values())
