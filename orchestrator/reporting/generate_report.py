"""Minimal orchestration for basic HTML experiment reports."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.reporting.figure_builder import build_report_figures
from orchestrator.reporting.html_renderer import render_report_html
from orchestrator.reporting.report_data_collector import collect_and_write_report_data


def generate_basic_html_report(experiment_dir: Path | str) -> Path:
    """Generate report_data.json, SVG plots, and report.html for an experiment."""

    experiment_path = Path(experiment_dir)
    report_dir = experiment_path / "report"
    report_data_path = collect_and_write_report_data(experiment_path)
    report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
    plot_paths = build_report_figures(report_data, report_dir / "plots")
    return render_report_html(report_data, plot_paths, report_dir / "report.html")


__all__ = ["generate_basic_html_report"]
