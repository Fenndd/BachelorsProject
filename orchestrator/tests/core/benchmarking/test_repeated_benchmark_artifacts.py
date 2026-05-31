from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from orchestrator.core.benchmarking.benchmark_artifacts import (
    benchmark_artifact_from_repeated_samples,
)
from orchestrator.core.benchmarking.benchmark_artifact_audit import (
    audit_single_benchmark_artifact,
)
from orchestrator.core.benchmarking.solver_registry import default_solver_descriptor


def _sample(index: int, runtime: float) -> dict[str, object]:
    return {
        "run_index": index,
        "solver_name": "poselib_p3p_lambdatwist",
        "num_problems": 1000,
        "total_solutions": 3000,
        "solutions_per_problem": 3.0,
        "valid_solutions": 3000,
        "valid_solutions_percent": 100.0,
        "gt_found": 1000,
        "gt_found_percent": 100.0,
        "runtime_ns_total_median": runtime * 1000,
        "runtime_ns_per_problem_median": runtime,
        "correctness_passed": True,
        "wall_seconds": 0.01,
    }


def test_repeated_benchmark_aggregation_uses_median_not_mean() -> None:
    artifact = benchmark_artifact_from_repeated_samples(
        [_sample(1, 100.0), _sample(2, 200.0), _sample(3, 1000.0)],
        default_solver_descriptor(),
        "Release",
    )

    assert artifact["parsed_runtime_ns_per_problem_median"] == 200.0
    assert artifact["repeated_benchmark_aggregate"]["median_runtime_ns_per_problem_median"] == 200.0
    assert artifact["repeated_benchmark_aggregate"]["min_runtime_ns_per_problem_median"] == 100.0
    assert artifact["benchmark_run_count"] == 3
    assert artifact["decision_metric"] == "median_runtime_ns_per_problem_median"
    assert "mean_runtime_ns_per_problem_median" not in artifact
    assert "max_runtime_ns_per_problem_median" not in artifact["repeated_benchmark_aggregate"]


def test_repeated_candidate_artifact_passes_audit() -> None:
    artifact = benchmark_artifact_from_repeated_samples(
        [_sample(index, runtime) for index, runtime in enumerate([100.0, 90.0, 110.0], start=1)],
        default_solver_descriptor(),
        "Release",
    )

    audit = audit_single_benchmark_artifact(
        {
            "artifact_exists": True,
            "benchmark_section_exists": True,
            "load_error": None,
            "artifact_path": "verification.json",
            "benchmark": artifact,
        },
        "candidate",
    )

    assert audit["passed"] is True
