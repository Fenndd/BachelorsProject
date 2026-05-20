"""Small generated-diff statistics helper for reporting artifacts."""

from __future__ import annotations

from typing import Any


def parse_diff_stats(diff_text: str) -> dict[str, Any]:
    """Return compact statistics for generated diff text."""

    files: set[str] = set()
    pending_old_path: str | None = None
    lines_added = 0
    lines_removed = 0
    changed_blocks = 0

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            changed_blocks += 1
            continue
        if line.startswith("--- "):
            pending_old_path = _clean_header_path(line[4:])
            continue
        if line.startswith("+++ "):
            new_path = _clean_header_path(line[4:])
            touched = new_path if new_path != "/dev/null" else pending_old_path
            if touched and touched != "/dev/null":
                files.add(_strip_diff_prefix(touched))
            pending_old_path = None
            continue
        if line.startswith("+"):
            lines_added += 1
        elif line.startswith("-"):
            lines_removed += 1

    return {
        "files_changed": len(files),
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "changed_blocks": changed_blocks,
    }


def _clean_header_path(path_text: str) -> str:
    path = path_text.strip()
    if "\t" in path:
        path = path.split("\t", 1)[0]
    return path


def _strip_diff_prefix(path_text: str) -> str:
    if path_text.startswith("a/") or path_text.startswith("b/"):
        return path_text[2:]
    return path_text


__all__ = ["parse_diff_stats"]
