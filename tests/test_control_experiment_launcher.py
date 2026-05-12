from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import orchestrator.control.experiment_launcher as experiment_launcher
from orchestrator.control.environment import get_env_specs
from orchestrator.control.process_runner import ProcessResult


def _clear_managed_env(monkeypatch) -> None:
    for spec in get_env_specs():
        monkeypatch.delenv(spec.name, raising=False)


def _write_valid_experiment(root: Path, provider: str = "mock") -> Path:
    (root / ".git").mkdir(exist_ok=True)
    (root / "results" / "experiments").mkdir(parents=True, exist_ok=True)
    (root / "configs" / "experiments").mkdir(parents=True, exist_ok=True)
    llm_config = root / "configs" / "llm_test.json"
    llm_config.write_text(
        f'{{"provider": "{provider}", "model": "{provider}-model"}}\n',
        encoding="utf-8",
    )
    config = root / "configs" / "experiments" / "test_exp.json"
    config.write_text(
        """{
  "experiment_name": "test_exp",
  "description": "Test experiment",
  "llm_config": "configs/llm_test.json",
  "target_file": "cpp/external/lambdatwist/p3p.cc",
  "iterations": 1,
  "optimization_scope": {
    "allowed_files": ["cpp/external/lambdatwist/p3p.cc"]
  },
  "pipeline": {
    "generate_candidate": true,
    "materialize_candidate": false,
    "verify_candidate": false
  },
  "candidate_generation": {
    "max_source_chars": 120000
  }
}
""",
        encoding="utf-8",
    )
    return config


def test_build_experiment_command_includes_config() -> None:
    config = Path("configs/experiments/example.json")

    command = experiment_launcher.build_experiment_command(config)

    assert "--config" in command
    assert str(config) in command


def test_build_experiment_command_includes_dry_run_when_requested() -> None:
    command = experiment_launcher.build_experiment_command(Path("example.json"), dry_run=True)

    assert "--dry-run" in command


def test_dry_run_does_not_require_api_key(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    config = _write_valid_experiment(tmp_path, provider="deepseek")

    def fake_run_streaming_command(command, cwd, env=None, on_stdout=None, on_stderr=None):
        now = datetime.now().astimezone()
        return ProcessResult(command, cwd, 0, now, now, 0.0)

    monkeypatch.setattr(
        experiment_launcher,
        "run_streaming_command",
        fake_run_streaming_command,
    )

    result = experiment_launcher.run_experiment_control(
        config,
        dry_run=True,
        repo_root=tmp_path,
    )

    assert result.status == "success"


@pytest.mark.parametrize(
    ("provider", "api_key_name"),
    [
        ("deepseek", "DEEPSEEK_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
    ],
)
def test_real_run_preflight_fails_when_provider_api_key_is_missing(
    provider: str,
    api_key_name: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _clear_managed_env(monkeypatch)
    config = _write_valid_experiment(tmp_path, provider=provider)

    result = experiment_launcher.run_experiment_control(
        config,
        dry_run=False,
        repo_root=tmp_path,
    )

    assert result.status == "preflight_failed"
    assert api_key_name in result.message


def test_launcher_success_detects_latest_experiment_dir(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    config = _write_valid_experiment(tmp_path, provider="mock")

    def fake_run_streaming_command(command, cwd, env=None, on_stdout=None, on_stderr=None):
        run_dir = tmp_path / "results" / "experiments" / "fake_experiment"
        run_dir.mkdir()
        if on_stdout is not None:
            on_stdout("fake experiment output")
        now = datetime.now().astimezone()
        return ProcessResult(command, cwd, 0, now, now, 0.0)

    monkeypatch.setattr(
        experiment_launcher,
        "run_streaming_command",
        fake_run_streaming_command,
    )
    stdout_lines: list[str] = []

    result = experiment_launcher.run_experiment_control(
        config,
        repo_root=tmp_path,
        on_stdout=stdout_lines.append,
    )

    assert result.status == "success"
    assert stdout_lines == ["fake experiment output"]
    assert result.latest_experiment_dir == tmp_path / "results" / "experiments" / "fake_experiment"


def test_launcher_failed_process_reports_failure(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    config = _write_valid_experiment(tmp_path, provider="mock")

    def fake_run_streaming_command(command, cwd, env=None, on_stdout=None, on_stderr=None):
        now = datetime.now().astimezone()
        return ProcessResult(command, cwd, 5, now, now, 0.0)

    monkeypatch.setattr(
        experiment_launcher,
        "run_streaming_command",
        fake_run_streaming_command,
    )

    result = experiment_launcher.run_experiment_control(config, repo_root=tmp_path)

    assert result.status == "failed"
    assert result.exit_code == 5
