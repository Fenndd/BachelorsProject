"""Shared test helpers and fixtures for the orchestration test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.control.environment import get_env_specs

TARGET_FILE = "cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a dict as UTF-8 JSON with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write a list of dicts as JSON Lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def repo_root(tmp_path: Path) -> Path:
    """Create a minimal fake git repo root with standard subdirectories."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / "results" / "runs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def clear_managed_env(monkeypatch) -> None:
    """Clear all environment variables managed by the project."""
    for spec in get_env_specs():
        monkeypatch.delenv(spec.name, raising=False)


def make_benchmark_payload(runtime: float | None = None, **overrides: Any) -> dict[str, Any]:
    """Build a standard poselib_native benchmark metrics payload.

    Accepts an optional ``runtime`` positional for convenience; when given,
    *parsed_runtime_ns_per_problem_median* and *parsed_runtime_ns_total_median*
    are set from it before applying any keyword overrides.
    """
    benchmark: dict[str, Any] = {
        "family": "poselib_native",
        "solver": "poselib_p3p_lambdatwist",
        "runtime_unit": "ns",
        "build_type": "Release",
        "benchmark_options": {
            "num_problems": 1000,
            "tolerance": 1e-6,
            "camera_fov": 75.0,
            "n_point_point": 3,
            "n_point_line": 0,
            "timed_iterations": 10,
            "runtime_unit": "ns",
            "build_type": "Release",
        },
        "parse_success": True,
        "parsed_num_problems": 1000,
        "parsed_total_solutions": 3000,
        "parsed_solutions_per_problem": 3.0,
        "parsed_valid_solutions": 3000,
        "parsed_valid_solutions_percent": 100.0,
        "parsed_gt_found": 1000,
        "parsed_gt_found_percent": 100.0,
        "parsed_runtime_ns_total_median": 1_000_000.0,
        "parsed_runtime_ns_per_problem_median": 1000.0,
        "parsed_correctness_passed": True,
    }
    if runtime is not None:
        benchmark["parsed_runtime_ns_per_problem_median"] = runtime
        benchmark["parsed_runtime_ns_total_median"] = runtime * 10
    runtime_value = benchmark["parsed_runtime_ns_per_problem_median"]
    benchmark["benchmark_run_count"] = 100
    benchmark["decision_metric"] = "median_runtime_ns_per_problem_median"
    benchmark["repeated_benchmark_samples"] = [
        {
            "run_index": index,
            "runtime_ns_per_problem_median": runtime_value,
            "gt_found_percent": benchmark["parsed_gt_found_percent"],
            "valid_solutions_percent": benchmark["parsed_valid_solutions_percent"],
            "wall_seconds": 0.001,
        }
        for index in range(1, 101)
    ]
    benchmark["repeated_benchmark_aggregate"] = {
        "benchmark_run_count": 100,
        "decision_metric": "median_runtime_ns_per_problem_median",
        "median_runtime_ns_per_problem_median": runtime_value,
        "min_runtime_ns_per_problem_median": runtime_value,
        "total_benchmark_wall_seconds": 0.1,
    }
    benchmark.update(overrides)
    return {"benchmark": benchmark}


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo_root(tmp_path: Path) -> Path:
    """Create a minimal fake repository root under tmp_path."""
    root = tmp_path
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "results" / "runs").mkdir(parents=True, exist_ok=True)
    (root / "results" / "experiments").mkdir(parents=True, exist_ok=True)
    (root / "workspace").mkdir(parents=True, exist_ok=True)
    (root / "configs").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace structure under tmp_path."""
    ws = tmp_path / "workspace"
    (ws / "candidates").mkdir(parents=True, exist_ok=True)
    (ws / "experiments").mkdir(parents=True, exist_ok=True)
    (ws / "build").mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def benchmark_payload_factory():
    """Return a callable that builds benchmark payloads via make_benchmark_payload."""
    return make_benchmark_payload


@pytest.fixture
def sample_baseline_run(tmp_path: Path) -> Path:
    """Create a minimal baseline run directory with metrics/metadata/status."""
    results_root = tmp_path / "results"
    run_dir = results_root / "runs" / "2026-01-01_00-00-00_baseline"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "metrics.json", make_benchmark_payload(runtime=1000.0))
    write_json(run_dir / "metadata.json", {"scenario": "baseline"})
    write_json(run_dir / "status.json", {"status": "success"})
    return run_dir


@pytest.fixture
def sample_candidate_run(tmp_path: Path) -> Path:
    """Create a minimal candidate run directory with verification/candidate/status."""
    results_root = tmp_path / "results"
    run_dir = results_root / "runs" / "2026-01-01_00-00-01_candidate"
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "verification.json", make_benchmark_payload(runtime=950.0))
    write_json(
        run_dir / "candidate.json",
        {
            "summary": "Reshape arithmetic in p3p pose estimation to reduce multiplications.",
            "rationale": "Eliminate redundant scalar multiplications in the pose construction block.",
            "correctness_notes": "Algebraically equivalent; no numerical precision change expected.",
            "edits": [
                {
                    "start_line": 100,
                    "end_line": 110,
                    "original": "// placeholder original snippet",
                    "replace": "// placeholder modified snippet",
                }
            ],
        },
    )
    write_json(run_dir / "status.json", {"status": "success"})
    return run_dir
