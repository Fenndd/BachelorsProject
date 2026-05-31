"""Shared formatting helpers for report narrative and HTML filters.

These functions are pure string formatters with no Jinja or data-model
dependencies.  Both the HTML renderer and the narrative collector import
from here, avoiding circular imports.
"""

from __future__ import annotations

from typing import Any

_EM_DASH = "\u2014"
_THIN_SPACE = "\u202f"
_MULTIPLY_SIGN = "\u00d7"
_ZERO_EPSILON = 0.005


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def format_human_int(value: Any) -> str:
    """Format an integer with thin-space thousands separator."""
    if value is None:
        return _EM_DASH
    num = _to_int(value)
    if num is None:
        return str(value)
    result = f"{num:,}"
    if num < 0:
        return "-" + result[1:].replace(",", _THIN_SPACE)
    return result.replace(",", _THIN_SPACE)


def format_human_duration(value: Any) -> str:
    """Format seconds as a human-readable duration string."""
    if value is None:
        return _EM_DASH
    num = _to_float(value)
    if num is None:
        return str(value)

    total_seconds = max(num, 0.0)
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}h {minutes:02d}m {int(seconds):02d}s"
    if minutes > 0:
        return f"{minutes}m {int(seconds):02d}s"
    if seconds == int(seconds):
        return f"{int(seconds)}s"
    return f"{seconds:.1f}s"


def format_percent(value: Any) -> str:
    """Format a number as a percentage with zero-normalization."""
    if value is None:
        return _EM_DASH
    num = _to_float(value)
    if num is None:
        return str(value)
    if abs(num) < _ZERO_EPSILON:
        num = 0.0
    return f"{num:.2f}%"


def format_speedup(value: Any) -> str:
    """Format a speedup factor with multiply sign."""
    if value is None:
        return _EM_DASH
    num = _to_float(value)
    if num is None:
        return str(value)
    return f"{num:.3f}{_MULTIPLY_SIGN}"


def format_runtime_ns(value: Any) -> str:
    """Format nanoseconds with thin-space thousands and two decimals."""
    if value is None:
        return _EM_DASH
    num = _to_float(value)
    if num is None:
        return str(value)
    if abs(num) < _ZERO_EPSILON:
        num = 0.0
    result = f"{num:,.2f}"
    if num < 0:
        return "-" + result[1:].replace(",", _THIN_SPACE)
    return result.replace(",", _THIN_SPACE)

def format_delta_pp(value: Any) -> str:
    """Format a percentage-point delta with zero-normalization and pp suffix."""
    if value is None:
        return _EM_DASH
    num = _to_float(value)
    if num is None:
        return str(value)
    if abs(num) < _ZERO_EPSILON:
        num = 0.0
    formatted = f"{num:,.2f}"
    if num < 0:
        formatted = "-" + formatted[1:].replace(",", _THIN_SPACE)
    else:
        formatted = formatted.replace(",", _THIN_SPACE)
    return f"{formatted}{_THIN_SPACE}pp"
