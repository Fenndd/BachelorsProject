"""Minimal solver descriptor registry for project-owned benchmark targets.

Each solver family registers one descriptor that maps a human-readable solver
identifier to the CMake target names, family label, runtime metadata, and
stdout parser needed for benchmark verification and final-selection reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from orchestrator.benchmarking.family_benchmark_parser import parse_absolute_pose_benchmark_output


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


_DESCRIPTORS: dict[str, SolverBenchmarkDescriptor] = {
    "lambdatwist_p3p": SolverBenchmarkDescriptor(
        solver_id="lambdatwist_p3p",
        family="absolute_pose_solvers",
        benchmark_target="absolute_pose_lambdatwist_benchmark",
        adapter_validator_target="absolute_pose_lambdatwist_adapter_validator",
        benchmark_step_name="absolute_pose_lambdatwist_benchmark",
        adapter_validator_step_name="absolute_pose_lambdatwist_adapter_validator",
        parser=parse_absolute_pose_benchmark_output,
        runtime_metric_key="parsed_runtime_ns_per_problem_median",
        runtime_unit="ns",
    ),
}

_DEFAULT_SOLVER_ID = "lambdatwist_p3p"


def get_solver_descriptor(solver_id: str) -> SolverBenchmarkDescriptor:
    """Return the descriptor for *solver_id*.

    Raises :class:`KeyError` when the solver is not registered.
    """
    if solver_id not in _DESCRIPTORS:
        raise KeyError(
            f"Unknown solver id {solver_id!r}. Registered solvers: "
            f"{sorted(_DESCRIPTORS.keys())}"
        )
    return _DESCRIPTORS[solver_id]


def default_solver_descriptor() -> SolverBenchmarkDescriptor:
    """Return the default solver descriptor used by the current pipeline."""
    return _DESCRIPTORS[_DEFAULT_SOLVER_ID]


def list_solver_descriptors() -> list[SolverBenchmarkDescriptor]:
    """Return every registered solver descriptor."""
    return list(_DESCRIPTORS.values())
