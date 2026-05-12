from __future__ import annotations

from pathlib import Path

from orchestrator.control.environment import (
    get_env_specs,
    load_environment,
    mask_secret,
    summarize_environment,
)


def _clear_managed_env(monkeypatch) -> None:
    for spec in get_env_specs():
        monkeypatch.delenv(spec.name, raising=False)


def _repo_root(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def _status_by_name(statuses):
    return {status.name: status for status in statuses}


def test_mask_secret_does_not_reveal_full_secret() -> None:
    secret = "sk-test-secret-value"

    masked = mask_secret(secret)

    assert masked != secret
    assert secret not in masked
    assert masked.startswith("sk-t")
    assert masked.endswith("alue")


def test_env_local_values_are_loaded(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)
    eigen_dir = tmp_path / "eigen"
    eigen_dir.mkdir()
    (root / ".env.local").write_text(
        f"EIGEN3_INCLUDE_DIR={eigen_dir}\nDEEPSEEK_API_KEY=deepseek-secret-value\n",
        encoding="utf-8",
    )

    statuses = _status_by_name(load_environment(root))

    assert statuses["EIGEN3_INCLUDE_DIR"].source == ".env.local"
    assert statuses["EIGEN3_INCLUDE_DIR"].status == "ok"
    assert statuses["DEEPSEEK_API_KEY"].source == ".env.local"
    assert statuses["DEEPSEEK_API_KEY"].status == "secret_set"
    assert "deepseek-secret-value" not in statuses["DEEPSEEK_API_KEY"].display_value


def test_process_environment_overrides_env_local(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)
    env_local_dir = tmp_path / "env-local-eigen"
    process_dir = tmp_path / "process-eigen"
    env_local_dir.mkdir()
    process_dir.mkdir()
    (root / ".env.local").write_text(
        f"EIGEN3_INCLUDE_DIR={env_local_dir}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EIGEN3_INCLUDE_DIR", str(process_dir))

    statuses = _status_by_name(load_environment(root))

    assert statuses["EIGEN3_INCLUDE_DIR"].source == "process"
    assert statuses["EIGEN3_INCLUDE_DIR"].value == str(process_dir)


def test_defaults_are_applied(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)

    statuses = _status_by_name(load_environment(root))

    assert statuses["CMAKE_GENERATOR"].source == "default"
    assert statuses["CMAKE_GENERATOR"].value == "Ninja"
    assert statuses["BENCHMARK_CMAKE_BUILD_TYPE"].source == "default"
    assert statuses["BENCHMARK_CMAKE_BUILD_TYPE"].value == "Release"


def test_missing_required_eigen_dir_is_reported(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)

    statuses = _status_by_name(load_environment(root))

    assert statuses["EIGEN3_INCLUDE_DIR"].status == "missing"
    summary = summarize_environment(list(statuses.values()), root)
    assert summary.missing_required == 1
    assert not summary.is_ok


def test_invalid_required_path_is_reported(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)
    (root / ".env.local").write_text(
        f"EIGEN3_INCLUDE_DIR={tmp_path / 'missing'}\n",
        encoding="utf-8",
    )

    statuses = _status_by_name(load_environment(root))

    assert statuses["EIGEN3_INCLUDE_DIR"].status == "invalid"
    assert "Directory does not exist" in statuses["EIGEN3_INCLUDE_DIR"].message


def test_optional_missing_secrets_do_not_fail_hard(tmp_path: Path, monkeypatch) -> None:
    _clear_managed_env(monkeypatch)
    root = _repo_root(tmp_path)
    eigen_dir = tmp_path / "eigen"
    eigen_dir.mkdir()
    (root / ".env.local").write_text(
        f"EIGEN3_INCLUDE_DIR={eigen_dir}\n",
        encoding="utf-8",
    )

    statuses = _status_by_name(load_environment(root))
    summary = summarize_environment(list(statuses.values()), root)

    assert statuses["OPENAI_API_KEY"].status == "secret_missing"
    assert statuses["ANTHROPIC_API_KEY"].status == "secret_missing"
    assert statuses["DEEPSEEK_API_KEY"].status == "secret_missing"
    assert summary.secrets_configured == 0
    assert summary.is_ok
