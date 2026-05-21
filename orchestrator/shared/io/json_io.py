from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path | str) -> Any:
    """Read a JSON file with BOM handling (utf-8-sig)."""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def read_json_object(path: Path | str) -> dict[str, Any]:
    """Read a JSON file and validate the top-level value is a dict."""
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in: {path}")
    return payload


def write_json(path: Path | str, payload: Any, *, compact: bool = False) -> Path:
    """Write payload as UTF-8 JSON, creating parent directories.

    Returns the written Path.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_kwargs: dict[str, Any] = {"ensure_ascii": False}
    if not compact:
        dump_kwargs["indent"] = 2
    path.write_text(json.dumps(payload, **dump_kwargs) + "\n", encoding="utf-8")
    return path
