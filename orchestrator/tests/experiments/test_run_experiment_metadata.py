from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

from orchestrator.experiments.run_experiment import _experiment_environment_info


def test_experiment_environment_info_defaults_build_type_to_release(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("CMAKE_BUILD_TYPE", raising=False)

    info = _experiment_environment_info()

    assert info["cmake_build_type"] == "Release"


def test_experiment_environment_info_keeps_explicit_build_type(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CMAKE_BUILD_TYPE", "Debug")

    info = _experiment_environment_info()

    assert info["cmake_build_type"] == "Debug"
