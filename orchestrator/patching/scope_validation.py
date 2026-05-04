"""Path normalization, security validation, and scope enforcement helpers.

These shared functions are used by experiment config loading, candidate
generation, and candidate materialization to enforce the optimization
scope consistently.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Sequence


def normalize_repo_path(path_text: str) -> str:
    """Normalize a repository-relative path and validate it is safe.

    Rules:
    - Strip whitespace, convert backslashes to forward slashes
    - Must not be empty
    - Must not contain null bytes
    - Must not be absolute (starting with /)
    - Must not contain Windows drive prefix (e.g. C:)
    - Must not contain '..' components
    - Must not reduce to an empty path after normalization

    Returns a POSIX-normalized relative path string.
    """
    raw = path_text.strip().replace("\\", "/")

    if not raw:
        raise ValueError("path is empty")

    if "\x00" in raw:
        raise ValueError(f"path contains a null byte: {path_text!r}")

    if raw.startswith("/"):
        raise ValueError(f"path must be relative (starts with /): {path_text!r}")

    if len(raw) >= 2 and raw[1] == ":":
        raise ValueError(
            f"path must not include a Windows drive prefix: {path_text!r}"
        )

    parts = raw.split("/")
    if ".." in parts:
        raise ValueError(f"path must not contain '..': {path_text!r}")

    path = PurePosixPath(raw)
    if not path.parts:
        raise ValueError("path is empty after normalization")

    return path.as_posix()


def validate_allowed_files_list(
    raw_files: Sequence[str], label: str = "allowed_files"
) -> list[str]:
    """Validate a list of allowed-file paths and return normalized versions."""
    if not raw_files:
        raise ValueError(f"{label} must be a non-empty list.")

    normalized: list[str] = []
    seen: set[str] = set()
    for index, raw_file in enumerate(raw_files):
        if not isinstance(raw_file, str):
            raise ValueError(
                f"{label} must contain only strings; "
                f"item {index} is {type(raw_file).__name__}."
            )
        normal = normalize_repo_path(raw_file)
        if normal not in seen:
            normalized.append(normal)
            seen.add(normal)

    return normalized


def validate_patch_scope(
    target_files: list[str],
    patched_files: list[str],
    allowed_files: list[str],
) -> None:
    """Validate that a candidate patch stays within the allowed scope.

    Raises ValueError with a descriptive message if any check fails.
    """
    allowed_set = set(allowed_files)
    target_set = set(target_files)

    # Check 1: candidate target_files ⊆ external allowed_files
    outside_target = sorted(target_set - allowed_set)
    if outside_target:
        raise ValueError(
            "candidate target_files outside allowed optimization scope: "
            + ", ".join(outside_target)
        )

    # Check 2: patched files from diff ⊆ candidate target_files
    if patched_files:
        patched_set = set(patched_files)
        outside_candidate = sorted(patched_set - target_set)
        if outside_candidate:
            raise ValueError(
                "candidate.diff modifies files not listed in "
                "candidate.json['target_files']: "
                + ", ".join(outside_candidate)
            )

        # Check 3: patched files from diff ⊆ external allowed_files
        outside_allowed = sorted(patched_set - allowed_set)
        if outside_allowed:
            raise ValueError(
                "candidate.diff modifies files outside allowed "
                f"optimization scope: " + ", ".join(outside_allowed)
            )
