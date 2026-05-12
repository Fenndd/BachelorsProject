"""Local environment loading and validation for control-layer diagnostics."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

from .project_paths import find_repo_root


EnvKind = Literal["path_dir", "path_file", "plain", "secret"]
EnvSource = Literal[".env.local", "process", "default", "missing"]
EnvStatusName = Literal[
    "ok",
    "missing",
    "optional_missing",
    "invalid",
    "secret_set",
    "secret_missing",
]


@dataclass(frozen=True)
class EnvVarSpec:
    name: str
    required: bool
    secret: bool
    kind: EnvKind
    default: str | None
    description: str


@dataclass(frozen=True)
class EnvVarStatus:
    name: str
    value: str | None
    display_value: str
    source: EnvSource
    status: EnvStatusName
    message: str


@dataclass(frozen=True)
class EnvironmentSummary:
    total: int
    ok: int
    missing_required: int
    invalid: int
    optional_missing: int
    secrets_configured: int
    secrets_missing: int
    env_local_exists: bool

    @property
    def is_ok(self) -> bool:
        return self.missing_required == 0 and self.invalid == 0

    @property
    def label(self) -> str:
        if self.invalid:
            return "invalid vars"
        if self.missing_required:
            return "missing required vars"
        return "OK"

    @property
    def api_keys_label(self) -> str:
        if self.secrets_configured:
            return "one or more configured"
        return "none configured"


def get_env_specs() -> list[EnvVarSpec]:
    return [
        EnvVarSpec(
            name="EIGEN3_INCLUDE_DIR",
            required=True,
            secret=False,
            kind="path_dir",
            default=None,
            description="Eigen include directory containing Eigen/.",
        ),
        EnvVarSpec(
            name="CMAKE_EXE",
            required=False,
            secret=False,
            kind="path_file",
            default=None,
            description="Optional path to cmake executable.",
        ),
        EnvVarSpec(
            name="CMAKE_GENERATOR",
            required=False,
            secret=False,
            kind="plain",
            default="Ninja",
            description="Optional CMake generator.",
        ),
        EnvVarSpec(
            name="CMAKE_CXX_COMPILER",
            required=False,
            secret=False,
            kind="path_file",
            default=None,
            description="Optional C++ compiler executable.",
        ),
        EnvVarSpec(
            name="CMAKE_MAKE_PROGRAM",
            required=False,
            secret=False,
            kind="path_file",
            default=None,
            description="Optional build tool executable.",
        ),
        EnvVarSpec(
            name="BENCHMARK_CMAKE_BUILD_TYPE",
            required=False,
            secret=False,
            kind="plain",
            default="Release",
            description="Benchmark CMake build type.",
        ),
        EnvVarSpec(
            name="OPENAI_API_KEY",
            required=False,
            secret=True,
            kind="secret",
            default=None,
            description="Optional OpenAI API key.",
        ),
        EnvVarSpec(
            name="ANTHROPIC_API_KEY",
            required=False,
            secret=True,
            kind="secret",
            default=None,
            description="Optional Anthropic API key.",
        ),
        EnvVarSpec(
            name="DEEPSEEK_API_KEY",
            required=False,
            secret=True,
            kind="secret",
            default=None,
            description="Optional DeepSeek API key.",
        ),
    ]


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _clean_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _status_for_value(spec: EnvVarSpec, value: str | None, source: EnvSource) -> EnvVarStatus:
    display_value = ""
    if value is not None:
        display_value = mask_secret(value) if spec.secret else value

    if value is None:
        if spec.secret:
            return EnvVarStatus(
                spec.name,
                None,
                "",
                "missing",
                "secret_missing",
                "Optional API key is not configured.",
            )
        if spec.required:
            return EnvVarStatus(
                spec.name,
                None,
                "",
                "missing",
                "missing",
                "Required variable is missing.",
            )
        return EnvVarStatus(
            spec.name,
            None,
            "",
            "missing",
            "optional_missing",
            "Optional variable is not configured.",
        )

    if spec.kind == "path_dir" and not Path(value).is_dir():
        return EnvVarStatus(
            spec.name,
            value,
            display_value,
            source,
            "invalid",
            "Directory does not exist.",
        )

    if spec.kind == "path_file" and not Path(value).is_file():
        return EnvVarStatus(
            spec.name,
            value,
            display_value,
            source,
            "invalid",
            "File does not exist.",
        )

    if spec.secret:
        return EnvVarStatus(
            spec.name,
            value,
            display_value,
            source,
            "secret_set",
            "Optional API key is configured.",
        )

    message = "Using default value." if source == "default" else "Configured."
    return EnvVarStatus(spec.name, value, display_value, source, "ok", message)


def load_environment(repo_root: Path | None = None) -> list[EnvVarStatus]:
    root = find_repo_root(repo_root)
    env_local_path = root / ".env.local"
    env_local_values = dotenv_values(env_local_path) if env_local_path.is_file() else {}
    statuses: list[EnvVarStatus] = []

    for spec in get_env_specs():
        process_value = _clean_value(os.environ.get(spec.name))
        file_value = _clean_value(env_local_values.get(spec.name))
        if process_value is not None:
            value = process_value
            source: EnvSource = "process"
        elif file_value is not None:
            value = file_value
            source = ".env.local"
        elif spec.default is not None:
            value = spec.default
            source = "default"
        else:
            value = None
            source = "missing"
        statuses.append(_status_for_value(spec, value, source))

    return statuses


def summarize_environment(
    statuses: list[EnvVarStatus],
    repo_root: Path | None = None,
) -> EnvironmentSummary:
    root = find_repo_root(repo_root)
    return EnvironmentSummary(
        total=len(statuses),
        ok=sum(1 for status in statuses if status.status in {"ok", "secret_set"}),
        missing_required=sum(1 for status in statuses if status.status == "missing"),
        invalid=sum(1 for status in statuses if status.status == "invalid"),
        optional_missing=sum(
            1 for status in statuses if status.status in {"optional_missing", "secret_missing"}
        ),
        secrets_configured=sum(1 for status in statuses if status.status == "secret_set"),
        secrets_missing=sum(1 for status in statuses if status.status == "secret_missing"),
        env_local_exists=(root / ".env.local").is_file(),
    )
