"""Lightweight solver manifest discovery for control-layer UI surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .project_paths import get_project_paths


@dataclass(frozen=True)
class SolverManifestOption:
    solver_id: str
    display_name: str
    display_label: str
    default_target_file: str | None
    default_allowed_files: tuple[str, ...]
    manifest_path: Path


def list_solver_manifest_options(repo_root: Path | None = None) -> list[SolverManifestOption]:
    """Return solver choices from ``cpp/bench/*/solvers/*.json`` manifests."""
    if repo_root is None:
        paths = get_project_paths()
        root = paths.repo_root
        bench_root = paths.cpp / "bench"
    else:
        root = Path(repo_root).resolve()
        bench_root = root / "cpp" / "bench"

    options: list[SolverManifestOption] = []
    for manifest_path in sorted(bench_root.glob("*/solvers/*.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue

        solver_id = data.get("solver_id")
        if not isinstance(solver_id, str) or not solver_id:
            continue
        display_name = data.get("display_name")
        if not isinstance(display_name, str) or not display_name:
            display_name = solver_id

        default_target = data.get("default_target_file")
        if not isinstance(default_target, str) or not default_target:
            default_target = None

        default_allowed_raw = data.get("default_allowed_files")
        if isinstance(default_allowed_raw, list) and all(
            isinstance(item, str) and item for item in default_allowed_raw
        ):
            default_allowed = tuple(default_allowed_raw)
        elif default_target is not None:
            default_allowed = (default_target,)
        else:
            default_allowed = ()

        options.append(
            SolverManifestOption(
                solver_id=solver_id,
                display_name=display_name,
                display_label=f"{display_name} ({solver_id})",
                default_target_file=default_target,
                default_allowed_files=default_allowed,
                manifest_path=manifest_path.relative_to(root),
            )
        )
    return options
