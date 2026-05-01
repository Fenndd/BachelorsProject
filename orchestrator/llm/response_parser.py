"""Parse and validate controlled optimization candidates returned by an LLM."""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any


ALLOWED_SCHEMA_VERSION = "1.0"
ALLOWED_CANDIDATE_TYPE = "unified_diff"
ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
ALLOWED_EXPECTED_EFFECTS = {"runtime", "memory", "both", "none"}


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
    requires_manual_review: bool


def parse_optimization_candidate(raw_content: str) -> OptimizationCandidate:
    """Parse and validate one optimization candidate JSON object."""
    payload = _parse_json_object(raw_content)
    expected_effect = _validate_enum(
        payload, "expected_effect", ALLOWED_EXPECTED_EFFECTS
    )
    unified_diff = _validate_string(payload, "unified_diff", allow_empty=True)
    _validate_unified_diff(expected_effect, unified_diff)

    return OptimizationCandidate(
        schema_version=_validate_literal(
            payload, "schema_version", ALLOWED_SCHEMA_VERSION
        ),
        candidate_type=_validate_literal(
            payload, "candidate_type", ALLOWED_CANDIDATE_TYPE
        ),
        summary=_validate_string(payload, "summary"),
        rationale=_validate_string(payload, "rationale"),
        risk_level=_validate_enum(payload, "risk_level", ALLOWED_RISK_LEVELS),
        expected_effect=expected_effect,
        target_files=_validate_string_list(payload, "target_files"),
        correctness_notes=_validate_string(payload, "correctness_notes"),
        unified_diff=unified_diff,
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
