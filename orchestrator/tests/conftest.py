"""Shared test helpers and fixtures for the orchestration test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.control.environment import get_env_specs

TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


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
    """Build a standard absolute-pose-solvers benchmark metrics payload.

    Accepts an optional ``runtime`` positional for convenience; when given,
    *parsed_runtime_ns_per_problem_median* and *parsed_runtime_ns_total_median*
    are set from it before applying any keyword overrides.
    """
    benchmark: dict[str, Any] = {
        "family": "absolute_pose_solvers",
        "solver": "lambdatwist_p3p",
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
    benchmark.update(overrides)
    return {"benchmark": benchmark}
