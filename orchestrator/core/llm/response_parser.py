"""Parse and validate controlled optimization candidates returned by an LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any


@dataclass(frozen=True)
class LineRangeEdit:
    """Validated line-range edit candidate operation."""

    start_line: int
    end_line: int
    original: str
    replace: str


@dataclass(frozen=True)
class OptimizationCandidate:
    """Validated LLM optimization candidate."""

    summary: str
    rationale: str
    correctness_notes: str
    edits: list[LineRangeEdit]


def parse_optimization_candidate(raw_content: str) -> OptimizationCandidate:
    """Parse and validate one optimization candidate JSON object."""
    payload = _parse_json_object(raw_content)
    edits = _parse_line_range_edits(payload)

    return OptimizationCandidate(
        summary=_validate_string(payload, "summary"),
        rationale=_validate_string(payload, "rationale"),
        correctness_notes=_validate_string(payload, "correctness_notes"),
        edits=edits,
    )


def _parse_json_object(raw_content: str) -> dict[str, Any]:
    if not isinstance(raw_content, str) or not raw_content.strip():
        raise ValueError("Optimization candidate content must be a non-empty string.")

    content = _strip_accidental_wrapping(raw_content.strip())
    try:
        parsed = json.loads(content)
    except JSONDecodeError:
        extracted = _extract_first_json_object(content)
        if extracted is None:
            raise ValueError("Optimization candidate is not valid JSON.") from None
        try:
            parsed = json.loads(extracted)
        except JSONDecodeError as exc:
            raise ValueError(f"Optimization candidate JSON is invalid: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Optimization candidate must be a JSON object.")
    return parsed


def _strip_accidental_wrapping(content: str) -> str:
    lines = content.splitlines()
    if lines and lines[0].strip().lower() in {"```json", "```"}:
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    lowered = content.lower()
    if lowered.startswith("json\n") or lowered.startswith("json "):
        content = content[4:].strip()

    return content


def _extract_first_json_object(content: str) -> str | None:
    start = content.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(content)):
        char = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[start : index + 1]

    return None


def _require_field(payload: dict[str, Any], field_name: str) -> Any:
    if field_name not in payload:
        raise ValueError(f"Missing required field: {field_name}")
    return payload[field_name]


def _validate_string(
    payload: dict[str, Any], field_name: str, allow_empty: bool = False
) -> str:
    value = _require_field(payload, field_name)
    if not isinstance(value, str):
        raise ValueError(f"Field '{field_name}' must be a string.")
    if not allow_empty and not value.strip():
        raise ValueError(f"Field '{field_name}' must not be empty.")
    return value


def _validate_positive_int_value(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Field '{field_name}' must be a positive integer.")
    return value


def _validate_edit_string(
    edit: dict[str, Any],
    key: str,
    field_name: str,
    allow_empty: bool = False,
) -> str:
    if key not in edit:
        raise ValueError(f"Missing required field: {field_name}")
    value = edit[key]
    if not isinstance(value, str):
        raise ValueError(f"Field '{field_name}' must be a string.")
    if not allow_empty and not value.strip():
        raise ValueError(f"Field '{field_name}' must not be empty.")
    return value


def _validate_edit_positive_int(
    edit: dict[str, Any],
    key: str,
    field_name: str,
) -> int:
    if key not in edit:
        raise ValueError(f"Missing required field: {field_name}")
    return _validate_positive_int_value(edit[key], field_name)


def _parse_line_range_edits(
    payload: dict[str, Any],
) -> list[LineRangeEdit]:
    edits_value = _require_field(payload, "edits")
    if not isinstance(edits_value, list):
        raise ValueError("Field 'edits' must be a list.")

    edits = [
        _validate_line_range_edit(edit, index)
        for index, edit in enumerate(edits_value)
    ]
    return edits


def _validate_line_range_edit(
    edit: Any,
    index: int,
) -> LineRangeEdit:
    field_prefix = f"edits[{index}]"
    if not isinstance(edit, dict):
        raise ValueError(f"Field '{field_prefix}' must be an object.")

    start_line = _validate_edit_positive_int(
        edit,
        "start_line",
        f"{field_prefix}.start_line",
    )
    end_line = _validate_edit_positive_int(
        edit,
        "end_line",
        f"{field_prefix}.end_line",
    )
    if end_line < start_line:
        raise ValueError(
            f"Field '{field_prefix}.end_line' must be greater than or equal to start_line."
        )

    return LineRangeEdit(
        start_line=start_line,
        end_line=end_line,
        original=_validate_edit_string(edit, "original", f"{field_prefix}.original"),
        replace=_validate_edit_string(
            edit,
            "replace",
            f"{field_prefix}.replace",
            allow_empty=True,
        ),
    )


def main() -> int:
    """Run an offline parser smoke test with one hardcoded valid candidate."""
    sample = json.dumps(
        {
            "summary": "Avoid repeated temporary allocation in a hot helper.",
            "rationale": "Reusing a local value may reduce per-call overhead.",
            "correctness_notes": "The proposed change preserves arithmetic order.",
            "edits": [
                {
                    "start_line": 1,
                    "end_line": 1,
                    "original": "double value = make_value();",
                    "replace": "const double value = make_value();",
                }
            ],
        }
    )
    candidate = parse_optimization_candidate(sample)

    print(f"Parsed summary: {candidate.summary}")
    print(f"Edit count: {len(candidate.edits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
