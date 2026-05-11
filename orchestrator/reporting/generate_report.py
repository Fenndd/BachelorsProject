"""Generate basic single-experiment reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from orchestrator.reporting.figure_builder import build_report_figures
from orchestrator.reporting.html_renderer import render_report_html
from orchestrator.reporting.pdf_exporter import export_pdf_from_html
from orchestrator.reporting.report_data_collector import collect_and_write_report_data


REPO_ROOT = Path(__file__).resolve().parents[2]
SUPPORTED_FORMATS = {"html", "pdf"}


def generate_basic_report(
    experiment_dir: Path | str,
    *,
    formats: tuple[str, ...] = ("html", "pdf"),
    renderer: str = "auto",
) -> dict[str, Path]:
    """Generate report_data.json, plots, HTML, and optionally PDF."""

    experiment_path = Path(experiment_dir)
    report_dir = experiment_path / "report"
    requested_formats = _normalize_formats(formats)

    report_data_path = collect_and_write_report_data(experiment_path)
    report_data = json.loads(report_data_path.read_text(encoding="utf-8"))
    plot_paths = build_report_figures(report_data, report_dir / "plots")
    html_path = render_report_html(report_data, plot_paths, report_dir / "report.html")

    artifacts = {
        "report_data": report_data_path,
        "html": html_path,
    }
    if "pdf" in requested_formats:
        artifacts["pdf"] = export_pdf_from_html(
            html_path,
            report_dir / "report.pdf",
            renderer=renderer,
        )
    return artifacts


def generate_basic_html_report(experiment_dir: Path | str) -> Path:
    """Generate report_data.json, SVG plots, and report.html for an experiment."""

    return generate_basic_report(experiment_dir, formats=("html",))["html"]


def _normalize_formats(formats: tuple[str, ...]) -> set[str]:
    normalized = {format_name.strip().lower() for format_name in formats}
    unknown = normalized - SUPPORTED_FORMATS
    if unknown:
        raise ValueError(
            "Unsupported report format(s): "
            f"{', '.join(sorted(unknown))}. Expected one or both of: html, pdf."
        )
    return normalized


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a basic single-experiment report."
    )
    parser.add_argument(
        "--experiment-dir",
        required=True,
        help="Completed closed-loop experiment directory.",
    )
    parser.add_argument(
        "--formats",
        default="html,pdf",
        help="Comma-separated output formats. Supported: html,pdf.",
    )
    parser.add_argument(
        "--renderer",
        default="auto",
        choices=("auto", "weasyprint", "playwright"),
        help="PDF renderer to use when PDF output is requested.",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Generate only report_data.json, plots, and HTML.",
    )
    return parser.parse_args(argv)


def _resolve_experiment_dir(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _formats_from_args(args: argparse.Namespace) -> tuple[str, ...]:
    if args.no_pdf:
        return ("html",)
    return tuple(item for item in args.formats.split(",") if item.strip())


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parse_args(sys.argv[1:] if argv is None else argv)
        artifacts = generate_basic_report(
            _resolve_experiment_dir(args.experiment_dir),
            formats=_formats_from_args(args),
            renderer=args.renderer,
        )
        for name, path in artifacts.items():
            print(f"{name}: {path}")
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    except Exception as exc:
        print(f"report_generation_error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "generate_basic_html_report",
    "generate_basic_report",
    "main",
]
