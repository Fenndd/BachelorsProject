"""Slow integration smoke test: baseline run for a PoseLib solver.

Verifies that the baseline CLI can build and run a second PoseLib solver
(not the default poselib_p3p_lambdatwist). The test is marked as slow and
integration; it skips cleanly when the required build environment is
not available.

Preference: poselib_relpose_5pt (comprehensive relative pose solver).
Fallback: poselib_homography_4pt (simple homography, may build faster).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _has_cmake() -> bool:
    return shutil.which("cmake") is not None


def _eigen_ok() -> bool:
    """Check EIGEN3_INCLUDE_DIR is set and the directory exists."""
    try:
        from orchestrator.control.environment import load_environment

        statuses = {s.name: s for s in load_environment()}
        eigen = statuses.get("EIGEN3_INCLUDE_DIR")
        if eigen is None:
            return False
        return eigen.status == "ok"
    except Exception:
        return False


def _find_latest_metrics(runs_root: Path) -> Path | None:
    """Find the most recent metrics.json inside results/runs/."""
    if not runs_root.is_dir():
        return None
    candidates: list[Path] = []
    for path in runs_root.iterdir():
        if not path.is_dir():
            continue
        metrics = path / "metrics.json"
        if metrics.is_file():
            candidates.append(metrics)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _run_baseline(solver_id: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run the baseline CLI for *solver_id*."""
    from orchestrator.control.baseline_launcher import build_baseline_environment

    command = [sys.executable, "-u", "-m", "orchestrator.cli.app", "baseline", "run", "--solver", solver_id]
    repo_root = None
    try:
        from orchestrator.paths import get_project_paths
        repo_root = get_project_paths().repo_root
    except Exception:
        pass

    env = build_baseline_environment(repo_root)
    return subprocess.run(
        command,
        cwd=str(repo_root) if repo_root else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _skip_if_no_build_env() -> None:
    """Skip the test if Eigen or CMake are unavailable."""
    if not _has_cmake():
        pytest.skip("cmake not found on PATH")
    if not _eigen_ok():
        pytest.skip("EIGEN3_INCLUDE_DIR is missing or invalid")


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.integration
class TestPoselibBaselineSmoke:
    def test_poselib_relpose_5pt_baseline(self, tmp_path: Path) -> None:
        _skip_if_no_build_env()

        result = _run_baseline("poselib_relpose_5pt", timeout=300)

        stdout_text = result.stdout
        stderr_text = result.stderr

        failure_msg = (
            f"relpose_5pt baseline exit={result.returncode}\n"
            f"STDOUT:\n{stdout_text[-2000:]}\n"
            f"STDERR:\n{stderr_text[-2000:]}"
        )
        assert result.returncode == 0, failure_msg

        # Verify solver_id appears in stdout or generated metrics
        from orchestrator.paths import get_project_paths

        repo_root = get_project_paths().repo_root
        runs_root = repo_root / "results" / "runs"
        metrics_path = _find_latest_metrics(runs_root)

        if metrics_path is not None:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            benchmark = metrics.get("benchmark", {}) if isinstance(metrics, dict) else {}
            solver_in_metrics = benchmark.get("solver")
            assert solver_in_metrics == "poselib_relpose_5pt", (
                f"Expected solver='poselib_relpose_5pt' in metrics, got {solver_in_metrics!r}\n"
                f"Metrics path: {metrics_path}"
            )
        else:
            # If no metrics.json found, check stdout
            assert (
                "poselib_relpose_5pt" in stdout_text
                or "poselib_relpose_5pt" in stderr_text
            ), (
                "poselib_relpose_5pt not found in stdout/stderr and no metrics.json found"
            )

    def test_poselib_homography_4pt_baseline(self, tmp_path: Path) -> None:
        _skip_if_no_build_env()

        result = _run_baseline("poselib_homography_4pt", timeout=300)

        stdout_text = result.stdout
        stderr_text = result.stderr

        failure_msg = (
            f"homography_4pt baseline exit={result.returncode}\n"
            f"STDOUT:\n{stdout_text[-2000:]}\n"
            f"STDERR:\n{stderr_text[-2000:]}"
        )
        assert result.returncode == 0, failure_msg

        from orchestrator.paths import get_project_paths

        repo_root = get_project_paths().repo_root
        runs_root = repo_root / "results" / "runs"
        metrics_path = _find_latest_metrics(runs_root)

        if metrics_path is not None:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            benchmark = metrics.get("benchmark", {}) if isinstance(metrics, dict) else {}
            solver_in_metrics = benchmark.get("solver")
            assert solver_in_metrics == "poselib_homography_4pt", (
                f"Expected solver='poselib_homography_4pt' in metrics, got {solver_in_metrics!r}"
            )
        else:
            assert (
                "poselib_homography_4pt" in stdout_text
                or "poselib_homography_4pt" in stderr_text
            )
