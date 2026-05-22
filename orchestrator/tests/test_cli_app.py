from __future__ import annotations

import os
import pytest
import subprocess
import sys
from pathlib import Path

pytestmark = pytest.mark.integration

from orchestrator.control.environment import get_env_specs


REPO_ROOT = Path(__file__).resolve().parents[2]


def run_cli(
    *args: str,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "orchestrator.cli.app", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_help_exits_successfully() -> None:
    result = run_cli("--help")

    assert result.returncode == 0
    assert "Experimental control layer" in result.stdout


def test_cli_doctor_exits_successfully() -> None:
    result = run_cli("doctor")

    assert result.returncode == 0
    assert "Doctor" in result.stdout
    assert "Environment Status" in result.stdout


def test_cli_doctor_exits_successfully_without_env_local(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    for spec in get_env_specs():
        env.pop(spec.name, None)

    result = run_cli("doctor", cwd=tmp_path, env=env)

    assert result.returncode == 0
    assert ".env.local not found" in result.stdout


def test_cli_experiment_list_exits_successfully() -> None:
    result = run_cli("experiment", "list")

    assert result.returncode == 0
    assert "Experiment Configs" in result.stdout
    assert "Status" in result.stdout


def test_cli_workspace_status_exits_successfully() -> None:
    result = run_cli("workspace", "status")

    assert result.returncode == 0
    assert "Workspace Status" in result.stdout


def test_cli_placeholder_commands_do_not_crash() -> None:
    result = run_cli("workspace", "status")

    assert result.returncode == 0, result.stderr


def test_cli_results_list_exits_successfully() -> None:
    result = run_cli("results", "list")

    assert result.returncode == 0
    assert "Results" in result.stdout


def test_cli_results_show_missing_selector_fails_cleanly() -> None:
    result = run_cli("results", "show", "definitely_missing_result_selector")

    assert result.returncode == 1
    assert "Result not found or ambiguous" in result.stdout


def test_cli_workspace_clean_declined_does_not_delete(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    candidate = tmp_path / "workspace" / "candidates" / "candidate_001"
    candidate.mkdir(parents=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = subprocess.run(
        [sys.executable, "-m", "orchestrator.cli.app", "workspace", "clean-candidates"],
        cwd=tmp_path,
        env=env,
        input="n\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert candidate.exists()


def test_cli_workspace_clean_yes_deletes_temp_workspace_only(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    candidate = tmp_path / "workspace" / "candidates" / "candidate_001"
    candidate.mkdir(parents=True)
    results = tmp_path / "results" / "runs" / "run_001"
    results.mkdir(parents=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)

    result = run_cli("workspace", "clean-candidates", "--yes", cwd=tmp_path, env=env)

    assert result.returncode == 0
    assert not candidate.exists()
    assert results.exists()


def test_cli_baseline_run_fails_cleanly_on_preflight_failure(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    for spec in get_env_specs():
        env.pop(spec.name, None)

    result = run_cli("baseline", "run", cwd=tmp_path, env=env)

    assert result.returncode == 1
    assert "preflight_failed" in result.stdout
    assert "EIGEN3_INCLUDE_DIR" in result.stdout


def test_cli_experiment_run_reports_invalid_config(tmp_path: Path) -> None:
    config = tmp_path / "experiment.json"
    config.write_text("{}\n", encoding="utf-8")

    result = run_cli("experiment", "run", "--config", str(config), "--dry-run")

    assert result.returncode == 1
    assert "preflight_failed" in result.stdout
