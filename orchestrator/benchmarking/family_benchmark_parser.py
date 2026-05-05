"""Parsers for project-owned family benchmark stdout.

The C++ benchmark runners intentionally print stable snake_case key-value lines
instead of JSON to avoid adding C++ serialization dependencies at this stage.
"""

from __future__ import annotations

import math
import re
from typing import Any


_KEY_VALUE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")

_FIELD_TYPES = {
    "solver_name": "str",
    "num_cases": "int",
    "success_rate": "float",
    "mean_best_reprojection_error": "float",
    "max_best_reprojection_error": "float",
    "runtime_ns_total_median": "float",
    "runtime_ns_per_case_median": "float",
    "correctness_passed": "bool",
}

_OPTIONAL_FIELD_TYPES = {
    "valid_cases": "int",
    "total_solutions": "int",
    "warmup_iterations": "int",
    "timed_iterations": "int",
    "random_seed": "int",
    "points_per_case": "int",
    "reprojection_error_threshold": "float",
    "min_success_rate": "float",
    "require_all_cases_valid": "bool",
    "use_max_reprojection_error_as_hard_gate": "bool",
    "runtime_unit": "str",
}

# Combined map for parsing; only REQUIRED_FIELDS govern parse_success.
_ALL_FIELD_TYPES: dict[str, str] = {}
_ALL_FIELD_TYPES.update(_FIELD_TYPES)
_ALL_FIELD_TYPES.update(_OPTIONAL_FIELD_TYPES)

_REQUIRED_FIELDS = tuple(_FIELD_TYPES.keys())


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
