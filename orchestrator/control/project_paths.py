"""Project path discovery for CLI and TUI control surfaces.

This module is a compatibility wrapper that re-exports from
:mod:`orchestrator.paths`, the canonical path-discovery module.
"""

from orchestrator.paths import (  # noqa: F401  -- re-export for backward compatibility
    ProjectPaths,
    find_repo_root,
    get_project_paths,
    resolve_project_path,
)
