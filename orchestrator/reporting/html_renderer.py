"""Render the basic HTML report from normalized report data."""

from __future__ import annotations

import html as _html
from datetime import datetime as _datetime
from pathlib import Path
from typing import Any

from jinja2 import (
    ChainableUndefined,
    Environment,
    FileSystemLoader,
    Undefined,
    select_autoescape,
)
from markupsafe import Markup

from orchestrator.reporting.report_data import ReportData, to_report_dict

_EM_DASH = "\u2014"


def render_report_html(
    report_data: ReportData | dict[str, Any],
    plot_paths: dict[str, str],
    output_path: Path | str,
) -> Path:
    """Render a standalone HTML report and return its path."""

    data = _as_report_dict(report_data)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(("html", "xml", "j2")),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=ChainableUndefined,
    )
    env.filters["display"] = _display_value
    env.filters["yes_no"] = _yes_no
    env.filters["human_int"] = _human_int
    env.filters["human_duration"] = _human_duration
    env.filters["percent"] = _percent
    env.filters["speedup"] = _speedup
    env.filters["human_datetime"] = _human_datetime
    env.filters["diff_highlight"] = _diff_highlight

    template = env.get_template("report.html.j2")
    html = template.render(
        report=data,
        plots=plot_paths,
        artifact_items=_artifact_items(data),
        status_items=_status_items(data),
    )
    destination.write_text(html, encoding="utf-8")
    return destination


def _as_report_dict(report_data: ReportData | dict[str, Any]) -> dict[str, Any]:
    payload = to_report_dict(report_data)
    if not isinstance(payload, dict):
        raise TypeError("report_data must be a ReportData instance or dictionary")
    return payload


def _artifact_items(data: dict[str, Any]) -> list[tuple[str, Any]]:
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    return [(key, value) for key, value in artifacts.items()]


def _status_items(data: dict[str, Any]) -> list[tuple[str, int]]:
    status_counts = data.get("status_counts")
    if not isinstance(status_counts, dict):
        return []
    return [
        (str(status), value)
        for status, value in status_counts.items()
        if isinstance(value, int) and not isinstance(value, bool)
    ]


def _display_value(value: Any) -> str:
    if isinstance(value, Undefined):
        return _EM_DASH
    if value is None or value == "":
        return _EM_DASH
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple)):
        if not value:
            return _EM_DASH
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        import json

        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _yes_no(value: Any) -> str:
    if isinstance(value, Undefined):
        return _EM_DASH
    if value is None:
        return _EM_DASH
    return "Yes" if value is True else "No"


def _human_int(value: Any) -> str:
    if value is None or isinstance(value, Undefined):
        return _EM_DASH
    if isinstance(value, bool):
        return str(value)
    try:
        num = int(value)
        return f"{num:,}".replace(",", "\u202f")
    except (ValueError, TypeError):
        return str(value)


def _human_duration(value: Any) -> str:
    if value is None or isinstance(value, Undefined):
        return _EM_DASH
    try:
        total_seconds = float(value)
    except (ValueError, TypeError):
        return str(value)

    if total_seconds < 0:
        total_seconds = 0.0

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


def _percent(value: Any) -> str:
    if value is None or isinstance(value, Undefined):
        return _EM_DASH
    try:
        num = float(value)
        return f"{num:.2f}%"
    except (ValueError, TypeError):
        return str(value)


def _speedup(value: Any) -> str:
    if value is None or isinstance(value, Undefined):
        return _EM_DASH
    try:
        num = float(value)
        return f"{num:.3f}\u00d7"
    except (ValueError, TypeError):
        return str(value)


def _human_datetime(value: Any) -> str:
    if value is None or isinstance(value, Undefined):
        return _EM_DASH
    text = str(value).strip()
    if not text:
        return _EM_DASH
    normalized = text.replace("Z", "+00:00")
    try:
        dt = _datetime.fromisoformat(normalized)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, AttributeError):
        return text


def _diff_highlight(value: Any) -> Markup:
    if isinstance(value, Undefined):
        return Markup(_EM_DASH)

    if not value:
        return Markup("")

    text = str(value)

    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import DiffLexer

        formatter = HtmlFormatter(nowrap=True, noclasses=True)
        result = highlight(text, DiffLexer(), formatter)
        return Markup(result)
    except Exception:
        return Markup(_html.escape(text))


__all__ = ["render_report_html"]
