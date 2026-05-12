from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from orchestrator.control.environment import get_env_specs
from orchestrator.control.process_runner import ProcessResult
import orchestrator.control.baseline_launcher as baseline_launcher


def _clear_managed_env(monkeypatch) -> None:
    for spec in get_env_specs():
        monkeypatch.delenv(spec.name, raising=False)


def _repo_root(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    (tmp_path / "results" / "runs").mkdir(parents=True)
    return tmp_path


def test_baseline_preflight_fails_when_eigen_missing(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)

    result = baseline_launcher.run_baseline(root)

    assert result.status == "preflight_failed"
    assert result.exit_code is None
    assert "EIGEN3_INCLUDE_DIR" in result.message


def test_baseline_preflight_fails_when_eigen_invalid(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)
    (root / ".env.local").write_text(
        f"EIGEN3_INCLUDE_DIR={tmp_path / 'missing'}\n",
        encoding="utf-8",
    )

    result = baseline_launcher.run_baseline(root)

    assert result.status == "preflight_failed"
    assert result.exit_code is None
    assert "Directory does not exist" in result.message


def test_build_baseline_environment_preserves_process_priority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)
    file_value = tmp_path / "file-eigen"
    process_value = tmp_path / "process-eigen"
    file_value.mkdir()
    process_value.mkdir()
    (root / ".env.local").write_text(
        f"EIGEN3_INCLUDE_DIR={file_value}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", str(process_value))

    env = baseline_launcher.build_baseline_environment(root)

    assert env["EIGEN3_INCLUDE_DIR"] == str(process_value)


def test_baseline_launcher_builds_expected_command_without_real_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)
    eigen_dir = tmp_path / "eigen"
    eigen_dir.mkdir()
    (root / ".env.local").write_text(
        f"EIGEN3_INCLUDE_DIR={eigen_dir}\n",
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    def fake_run_streaming_command(command, cwd, env=None, on_stdout=None, on_stderr=None):
        seen["command"] = command
        seen["cwd"] = cwd
        if on_stdout is not None:
            on_stdout("fake baseline output")
        run_dir = root / "results" / "runs" / "fake_baseline_run"
        run_dir.mkdir()
        now = datetime.now().astimezone()
        return ProcessResult(command, cwd, 0, now, now, 0.0)

    monkeypatch.setattr(
        baseline_launcher,
        "run_streaming_command",
        fake_run_streaming_command,
    )
    stdout_lines: list[str] = []

    result = baseline_launcher.run_baseline(root, on_stdout=stdout_lines.append)

    assert result.status == "success"
    assert seen["command"] == baseline_launcher.build_baseline_command()
    assert seen["cwd"] == root
    assert stdout_lines == ["fake baseline output"]
    assert result.latest_run_dir == root / "results" / "runs" / "fake_baseline_run"


def test_baseline_launcher_reports_failed_process_and_latest_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)
    eigen_dir = tmp_path / "eigen"
    eigen_dir.mkdir()
    (root / ".env.local").write_text(
        f"EIGEN3_INCLUDE_DIR={eigen_dir}\n",
        encoding="utf-8",
    )

    def fake_run_streaming_command(command, cwd, env=None, on_stdout=None, on_stderr=None):
        run_dir = root / "results" / "runs" / "failed_baseline_run"
        run_dir.mkdir()
        now = datetime.now().astimezone()
        return ProcessResult(command, cwd, 3, now, now, 0.0)

    monkeypatch.setattr(
        baseline_launcher,
        "run_streaming_command",
        fake_run_streaming_command,
    )

    result = baseline_launcher.run_baseline(root)

    assert result.status == "failed"
    assert result.exit_code == 3
    assert result.latest_run_dir == root / "results" / "runs" / "failed_baseline_run"
