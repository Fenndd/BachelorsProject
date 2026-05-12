"""Safe OS-open helper for existing result artifacts."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


class OpenArtifactError(RuntimeError):
    """Raised when an artifact cannot be opened."""


def open_path(path: Path) -> None:
    resolved = path.resolve()
    if not resolved.exists():
        raise OpenArtifactError(f"Path does not exist: {resolved}")

    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(str(resolved))  # type: ignore[attr-defined]
            return
        if system == "Darwin":
            result = subprocess.run(["open", str(resolved)], check=False)
        else:
            result = subprocess.run(["xdg-open", str(resolved)], check=False)
    except OSError as exc:
        raise OpenArtifactError(f"Could not open path: {resolved}: {exc}") from exc

    if result.returncode != 0:
        raise OpenArtifactError(f"Could not open path: {resolved}")
