"""Parsers for project-owned family benchmark stdout."""

from __future__ import annotations

import math
import json
from typing import Any


_FIELD_TYPES = {
    "solver_name": "str",
    "num_problems": "int",
    "total_solutions": "int",
    "solutions_per_problem": "float",
    "valid_solutions": "int",
    "valid_solutions_percent": "float",
    "gt_found": "int",
    "gt_found_percent": "float",
    "runtime_ns_total_median": "float",
    "runtime_ns_per_problem_median": "float",
    "correctness_passed": "bool",
}

_REQUIRED_FIELDS = tuple(_FIELD_TYPES.keys())
_POSELIB_JSON_PREFIX = "POSELIB_BENCHMARK_JSON="


def parse_poselib_native_benchmark_output(text: str) -> dict[str, Any]:
    """Parse the prefixed JSON line emitted by the PoseLib native benchmark."""
    parse_errors: list[str] = []
    raw_json_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_POSELIB_JSON_PREFIX):
            raw_json_lines.append(stripped[len(_POSELIB_JSON_PREFIX) :].strip())
    if not raw_json_lines:
        return {
            "parse_success": False,
            "missing_fields": list(_REQUIRED_FIELDS),
            "parse_errors": [
                f"no {_POSELIB_JSON_PREFIX} line found in output"
            ],
            "metrics": {},
        }

    valid_payloads: list[dict[str, Any]] = []
    for raw in raw_json_lines:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            valid_payloads.append(parsed)

    if len(valid_payloads) == 0:
        return {
            "parse_success": False,
            "missing_fields": list(_REQUIRED_FIELDS),
            "parse_errors": [f"no valid JSON object found among {len(raw_json_lines)} line(s)"],
            "metrics": {},
        }
    if len(valid_payloads) > 1:
        keys = [p.get("solver_key", "?") for p in valid_payloads]
        return {
            "parse_success": False,
            "missing_fields": list(_REQUIRED_FIELDS),
            "parse_errors": [
                f"ambiguous output: {len(valid_payloads)} JSON objects found "
                f"(solver_keys: {keys})"
            ],
            "metrics": {},
        }

    payload = valid_payloads[0]
    if not isinstance(payload, dict):
        return {
            "parse_success": False,
            "missing_fields": list(_REQUIRED_FIELDS),
            "parse_errors": ["PoseLib benchmark JSON must be an object"],
            "metrics": {},
        }

    metrics: dict[str, object] = {}
    field_map = {
        "solver_name": ("solver_key", "str"),
        "solver_key": ("solver_key", "str"),
        "benchmark_kind": ("benchmark_kind", "str"),
        "num_problems": ("instances", "int"),
        "instances": ("instances", "int"),
        "total_solutions": ("solutions_total", "int"),
        "solutions_per_problem": ("solutions_per_problem", "float"),
        "valid_solutions": ("valid_solutions", "int"),
        "valid_solutions_percent": ("valid_solutions_percent", "float"),
        "gt_found": ("gt_found", "int"),
        "gt_found_percent": ("gt_found_percent", "float"),
        "runtime_ns_total_median": ("runtime_ns_total_median", "float"),
        "runtime_ns_per_problem_median": ("runtime_ns_per_problem_median", "float"),
        "parsed_runtime_ns_per_problem_median": ("runtime_ns_per_problem_median", "float"),
        "correctness_passed": ("correctness_passed", "bool"),
        "tolerance": ("tolerance", "float"),
    }
    for output_key, (input_key, field_type) in field_map.items():
        if input_key not in payload:
            continue
        try:
            metrics[output_key] = _convert_value(str(payload[input_key]), field_type)
        except ValueError as exc:
            parse_errors.append(f"{output_key}: {exc}")

    if "correctness_passed" not in metrics:
        required_without_correctness = [
            field_name
            for field_name in _REQUIRED_FIELDS
            if field_name != "correctness_passed"
        ]
        if all(field_name in metrics for field_name in required_without_correctness):
            metrics["correctness_passed"] = True
    if "correctness_passed" in metrics:
        metrics["parsed_correctness_passed"] = metrics["correctness_passed"]

    missing_fields = [
        field_name for field_name in _REQUIRED_FIELDS if field_name not in metrics
    ]
    return {
        "parse_success": not missing_fields and not parse_errors,
        "missing_fields": missing_fields,
        "parse_errors": parse_errors,
        "metrics": metrics,
    }


def _convert_value(raw_value: str, field_type: str) -> object:
    stripped = raw_value.strip()
    if field_type == "str":
        if not stripped:
            raise ValueError("empty string")
        return stripped
    if field_type == "int":
        return int(stripped)
    if field_type == "float":
        value = float(stripped)
        if not math.isfinite(value):
            raise ValueError("non-finite float")
        return value
    if field_type == "bool":
        lowered = stripped.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        raise ValueError(f"expected true/false, got {raw_value!r}")

    raise ValueError(f"unsupported field type {field_type!r}")
