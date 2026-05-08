"""Parse and validate controlled optimization candidates returned by an LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any


SCHEMA_VERSION_BY_CANDIDATE_TYPE = {
    "unified_diff": "1.0",
    "line_range_edits": "1.1",
}
ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
ALLOWED_EXPECTED_EFFECTS = {"runtime", "memory", "both", "none"}


@dataclass(frozen=True)
class LineRangeEdit:
    """Validated line-range edit candidate operation."""

    file: str
    start_line: int
    end_line: int
    original: str
    replace: str


@dataclass(frozen=True)
class OptimizationCandidate:
    """Validated LLM optimization candidate."""

    schema_version: str
    candidate_type: str
    summary: str
    rationale: str
    risk_level: str
    expected_effect: str
    target_files: list[str]
    correctness_notes: str
    unified_diff: str
    edits: list[LineRangeEdit]
    requires_manual_review: bool


def parse_optimization_candidate(raw_content: str) -> OptimizationCandidate:
    """Parse and validate one optimization candidate JSON object."""
    payload = _parse_json_object(raw_content)
    candidate_type = _validate_candidate_type(payload)
    schema_version = _validate_schema_version(payload, candidate_type)
    expected_effect = _validate_enum(
        payload, "expected_effect", ALLOWED_EXPECTED_EFFECTS
    )
    target_files = _validate_string_list(payload, "target_files")
    if candidate_type == "unified_diff":
        unified_diff, edits = _parse_unified_diff_fields(payload, expected_effect)
    elif candidate_type == "line_range_edits":
        unified_diff, edits = _parse_line_range_edits_fields(
            payload,
            expected_effect,
            target_files,
        )
    else:
        raise ValueError(f"Unsupported candidate_type: {candidate_type}")

    return OptimizationCandidate(
        schema_version=schema_version,
        candidate_type=candidate_type,
        summary=_validate_string(payload, "summary"),
        rationale=_validate_string(payload, "rationale"),
        risk_level=_validate_enum(payload, "risk_level", ALLOWED_RISK_LEVELS),
        expected_effect=expected_effect,
        target_files=target_files,
        correctness_notes=_validate_string(payload, "correctness_notes"),
        unified_diff=unified_diff,
        edits=edits,
        requires_manual_review=_validate_bool(payload, "requires_manual_review"),
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


def _validate_literal(
    payload: dict[str, Any], field_name: str, expected_value: str
) -> str:
    value = _validate_string(payload, field_name)
    if value != expected_value:
        raise ValueError(
            f"Field '{field_name}' must be {expected_value!r}, got {value!r}."
        )
    return value


def _validate_candidate_type(payload: dict[str, Any]) -> str:
    candidate_type = _validate_string(payload, "candidate_type")
    if candidate_type not in SCHEMA_VERSION_BY_CANDIDATE_TYPE:
        raise ValueError(f"Unsupported candidate_type: {candidate_type}")
    return candidate_type


def _validate_schema_version(payload: dict[str, Any], candidate_type: str) -> str:
    schema_version = _validate_string(payload, "schema_version")
    expected_schema_version = SCHEMA_VERSION_BY_CANDIDATE_TYPE[candidate_type]
    if schema_version != expected_schema_version:
        raise ValueError(
            f"schema_version must be {expected_schema_version!r} for {candidate_type}."
        )
    return schema_version


def _validate_enum(
    payload: dict[str, Any], field_name: str, allowed_values: set[str]
) -> str:
    value = _validate_string(payload, field_name)
    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise ValueError(f"Field '{field_name}' must be one of: {allowed}.")
    return value


def _validate_string_list(payload: dict[str, Any], field_name: str) -> list[str]:
    value = _require_field(payload, field_name)
    if not isinstance(value, list):
        raise ValueError(f"Field '{field_name}' must be a list of strings.")
    if not value:
        raise ValueError(f"Field '{field_name}' must contain at least one file path.")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Field '{field_name}' must contain only non-empty strings.")
    return value


def _validate_bool(payload: dict[str, Any], field_name: str) -> bool:
    value = _require_field(payload, field_name)
    if not isinstance(value, bool):
        raise ValueError(f"Field '{field_name}' must be a boolean.")
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


def _parse_unified_diff_fields(
    payload: dict[str, Any],
    expected_effect: str,
) -> tuple[str, list[LineRangeEdit]]:
    if "edits" in payload:
        raise ValueError("Field 'edits' is not allowed for unified_diff candidates.")
    unified_diff = _validate_string(payload, "unified_diff", allow_empty=True)
    _validate_unified_diff(expected_effect, unified_diff)
    return unified_diff, []


def _parse_line_range_edits_fields(
    payload: dict[str, Any],
    expected_effect: str,
    target_files: list[str],
) -> tuple[str, list[LineRangeEdit]]:
    unified_diff = payload.get("unified_diff", "")
    if not isinstance(unified_diff, str):
        raise ValueError("Field 'unified_diff' must be a string if present.")
    if unified_diff:
        raise ValueError(
            "Field 'unified_diff' must be empty for line_range_edits candidates."
        )

    edits_value = _require_field(payload, "edits")
    if not isinstance(edits_value, list):
        raise ValueError("Field 'edits' must be a list.")
    if expected_effect != "none" and not edits_value:
        raise ValueError(
            "Field 'edits' must be non-empty when expected_effect is not 'none'."
        )

    edits = [
        _validate_line_range_edit(edit, index, target_files)
        for index, edit in enumerate(edits_value)
    ]
    return "", edits


def _validate_line_range_edit(
    edit: Any,
    index: int,
    target_files: list[str],
) -> LineRangeEdit:
    field_prefix = f"edits[{index}]"
    if not isinstance(edit, dict):
        raise ValueError(f"Field '{field_prefix}' must be an object.")

    file = _validate_edit_string(edit, "file", f"{field_prefix}.file")
    if file not in target_files:
        raise ValueError(
            f"Field '{field_prefix}.file' must be included in target_files."
        )
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
        file=file,
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


def _validate_unified_diff(expected_effect: str, unified_diff: str) -> None:
    diff = unified_diff.strip()
    if expected_effect != "none" and not diff:
        raise ValueError(
            "Field 'unified_diff' must be non-empty when expected_effect is not 'none'."
        )
    if not diff:
        return

    lowered = diff.lower()
    placeholder_markers = [
        "1234567..abcdefg",
        "abcdefg",
        "fake hash",
        "fake_hash",
        "<hash",
        "placeholder hash",
    ]
    for marker in placeholder_markers:
        if marker in lowered:
            raise ValueError(
                "Field 'unified_diff' contains placeholder or fake diff metadata."
            )

    if "--- " not in diff or "+++ " not in diff:
        raise ValueError(
            "Field 'unified_diff' must contain both '--- ' and '+++ ' file headers."
        )
    if "@@" not in diff:
        raise ValueError("Field 'unified_diff' must contain at least one '@@' hunk.")


def main() -> int:
    """Run an offline parser smoke test with one hardcoded valid candidate."""
    sample = json.dumps(
        {
            "schema_version": "1.0",
            "candidate_type": "unified_diff",
            "summary": "Avoid repeated temporary allocation in a hot helper.",
            "rationale": "Reusing a local value may reduce per-call overhead.",
            "risk_level": "low",
            "expected_effect": "runtime",
            "target_files": ["cpp/src/example.cpp"],
            "correctness_notes": "The proposed change preserves arithmetic order.",
            "unified_diff": (
                "diff --git a/cpp/src/example.cpp b/cpp/src/example.cpp\n"
                "--- a/cpp/src/example.cpp\n"
                "+++ b/cpp/src/example.cpp\n"
                "@@ -1,3 +1,3 @@\n"
                "-double value = make_value();\n"
                "+const double value = make_value();\n"
            ),
            "requires_manual_review": True,
        }
    )
    candidate = parse_optimization_candidate(sample)

    print(f"Parsed summary: {candidate.summary}")
    print(f"Target files: {', '.join(candidate.target_files)}")
    print(f"Risk level: {candidate.risk_level}")
    print(f"Unified diff present: {bool(candidate.unified_diff)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
