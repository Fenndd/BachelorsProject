"""Parsers for project-owned family benchmark stdout."""

from __future__ import annotations

import math
import json
import re
from typing import Any


_KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")

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

_OPTIONAL_FIELD_TYPES = {
    "tolerance": "float",
    "camera_fov": "float",
    "n_point_point": "int",
    "n_point_line": "int",
    "timed_iterations": "int",
    "runtime_unit": "str",
}

# Combined map for parsing; only REQUIRED_FIELDS govern parse_success.
_ALL_FIELD_TYPES: dict[str, str] = {}
_ALL_FIELD_TYPES.update(_FIELD_TYPES)
_ALL_FIELD_TYPES.update(_OPTIONAL_FIELD_TYPES)

_REQUIRED_FIELDS = tuple(_FIELD_TYPES.keys())
_POSELIB_JSON_PREFIX = "POSELIB_BENCHMARK_JSON="


def parse_absolute_pose_benchmark_output(text: str) -> dict[str, Any]:
    """Parse stable key-value metrics from absolute-pose family benchmark output."""
    metrics: dict[str, object] = {}
    parse_errors: list[str] = []

    for line in text.splitlines():
        match = _KEY_VALUE_RE.match(line)
        if match is None:
            continue

        key, raw_value = match.groups()
        field_type = _ALL_FIELD_TYPES.get(key)
        if field_type is None:
            continue

        try:
            metrics[key] = _convert_value(raw_value, field_type)
        except ValueError as exc:
            parse_errors.append(f"{key}: {exc}")

    missing_fields = [
        field_name for field_name in _REQUIRED_FIELDS if field_name not in metrics
    ]

    return {
        "parse_success": not missing_fields and not parse_errors,
        "missing_fields": missing_fields,
        "parse_errors": parse_errors,
        "metrics": metrics,
    }


def parse_poselib_native_benchmark_output(
    text: str,
    *,
    min_gt_found_percent: float = 99.0,
    min_valid_solutions_percent: float = 99.0,
) -> dict[str, Any]:
    """Parse the prefixed JSON line emitted by the PoseLib native benchmark."""
    parse_errors: list[str] = []
    json_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_POSELIB_JSON_PREFIX):
            json_lines.append(stripped[len(_POSELIB_JSON_PREFIX) :].strip())
    if len(json_lines) != 1:
        return {
            "parse_success": False,
            "missing_fields": list(_REQUIRED_FIELDS),
            "parse_errors": [
                f"expected exactly one {_POSELIB_JSON_PREFIX} line, found {len(json_lines)}"
            ],
            "metrics": {},
        }

    try:
        payload = json.loads(json_lines[0])
    except json.JSONDecodeError as exc:
        return {
            "parse_success": False,
            "missing_fields": list(_REQUIRED_FIELDS),
            "parse_errors": [f"invalid JSON: {exc}"],
            "metrics": {},
        }
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
        "tolerance": ("tolerance", "float"),
    }
    for output_key, (input_key, field_type) in field_map.items():
        if input_key not in payload:
            continue
        try:
            metrics[output_key] = _convert_value(str(payload[input_key]), field_type)
        except ValueError as exc:
            parse_errors.append(f"{output_key}: {exc}")

    gt_found_percent = metrics.get("gt_found_percent")
    valid_solutions_percent = metrics.get("valid_solutions_percent")
    if isinstance(gt_found_percent, (int, float)) and isinstance(valid_solutions_percent, (int, float)):
        metrics["correctness_passed"] = (
            float(gt_found_percent) >= min_gt_found_percent
            and float(valid_solutions_percent) >= min_valid_solutions_percent
        )
    elif "correctness_passed" in payload:
        try:
            metrics["correctness_passed"] = _convert_value(
                str(payload["correctness_passed"]), "bool"
            )
        except ValueError as exc:
            parse_errors.append(f"correctness_passed: {exc}")

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
