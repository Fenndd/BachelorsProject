from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path

from orchestrator.control.environment import get_env_specs


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_cli_workspace_status_exits_successfully() -> None:
    result = run_cli("workspace", "status")

    assert result.returncode == 0
    assert "Workspace Status" in result.stdout


def test_cli_placeholder_commands_do_not_crash() -> None:
    for args in (
        ("baseline", "run"),
        ("results", "latest"),
    ):
        result = run_cli(*args)

        assert result.returncode == 0, result.stderr


def test_cli_experiment_run_validates_existing_config(tmp_path: Path) -> None:
    config = tmp_path / "experiment.json"
    config.write_text("{}\n", encoding="utf-8")

    result = run_cli("experiment", "run", "--config", str(config))

    assert result.returncode == 0
    assert "Validated config" in result.stdout
