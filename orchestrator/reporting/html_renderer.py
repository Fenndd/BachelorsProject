"""Render the basic HTML report from normalized report data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from orchestrator.reporting.report_data import ReportData, to_report_dict


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
    )
    env.filters["display"] = _display_value
    env.filters["yes_no"] = _yes_no

    template = env.get_template("report_v1.html.j2")
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
    if value is None or value == "":
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "Not available"
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        import json
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _yes_no(value: Any) -> str:
    if value is None:
        return "Not available"
    return "Yes" if value is True else "No"


__all__ = ["render_report_html"]
