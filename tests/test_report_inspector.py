from __future__ import annotations

import json
from pathlib import Path

from orchestrator.reporting import inspect_report
from orchestrator.reporting.report_inspector import EXPECTED_PLOTS, EXPECTED_SECTIONS, main


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_report_data(experiment_dir: Path, payload: dict | None = None) -> None:
    _write_text(
        experiment_dir / "report" / "report_data.json",
        json.dumps(payload or {"schema_version": "report.v1", "iterations": []}) + "\n",
    )


def _section_html(section_ids: tuple[str, ...] = EXPECTED_SECTIONS) -> str:
    sections = "\n".join(f'<section id="{section_id}"></section>' for section_id in section_ids)
    return f"<!doctype html><html><body>{sections}</body></html>\n"


def _write_html(experiment_dir: Path, section_ids: tuple[str, ...] = EXPECTED_SECTIONS) -> None:
    _write_text(experiment_dir / "report" / "report.html", _section_html(section_ids))


def _write_pdf(experiment_dir: Path) -> None:
    path = experiment_dir / "report" / "report.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-fake")


def _write_plots(experiment_dir: Path, filenames: tuple[str, ...] = EXPECTED_PLOTS) -> None:
    for filename in filenames:
        _write_text(experiment_dir / "report" / "plots" / filename, "<svg></svg>\n")


def _write_complete_fake_report(experiment_dir: Path) -> None:
    _write_report_data(experiment_dir)
    _write_html(experiment_dir)
    _write_pdf(experiment_dir)
    _write_plots(experiment_dir)


def test_inspect_report_ok_for_complete_report(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "exp_001"
    _write_complete_fake_report(experiment_dir)

    result = inspect_report(experiment_dir)

    assert result["status"] == "ok"
    assert result["errors"] == []
    assert result["warnings"] == []
    assert result["files"]["report_data_json"]["valid_json"] is True
    assert result["plots"]["missing"] == []
    assert result["sections"]["missing"] == []


def test_inspect_report_warns_when_pdf_missing(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "exp_001"
    _write_report_data(experiment_dir)
    _write_html(experiment_dir)
    _write_plots(experiment_dir)

    result = inspect_report(experiment_dir)

    assert result["status"] == "warning"
    assert result["errors"] == []
    assert any("report.pdf" in warning for warning in result["warnings"])


def test_inspect_report_fails_when_report_data_missing(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "exp_001"
    _write_html(experiment_dir)
    _write_pdf(experiment_dir)
    _write_plots(experiment_dir)

    result = inspect_report(experiment_dir)

    assert result["status"] == "failed"
    assert any("report_data.json" in error for error in result["errors"])


def test_inspect_report_fails_when_report_data_invalid(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "exp_001"
    _write_text(experiment_dir / "report" / "report_data.json", "{not json\n")
    _write_html(experiment_dir)
    _write_pdf(experiment_dir)
    _write_plots(experiment_dir)

    result = inspect_report(experiment_dir)

    assert result["status"] == "failed"
    assert any("Invalid report_data.json" in error for error in result["errors"])
    assert result["files"]["report_data_json"]["valid_json"] is False


def test_inspect_report_warns_when_v2_sections_missing(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "exp_001"
    old_section_ids = tuple(
        section_id
        for section_id in EXPECTED_SECTIONS
        if section_id
        not in {
            "failure-analysis",
            "phase-timings",
            "llm-usage",
            "diff-statistics",
            "iteration-appendix",
        }
    )
    _write_report_data(experiment_dir, {"schema_version": "report.v1", "iterations": []})
    _write_html(experiment_dir, old_section_ids)
    _write_pdf(experiment_dir)
    _write_plots(experiment_dir)

    result = inspect_report(experiment_dir)

    assert result["status"] == "warning"
    assert result["errors"] == []
    assert "failure-analysis" in result["sections"]["missing"]
    assert "iteration-appendix" in result["sections"]["missing"]


def test_inspect_report_handles_v1_like_report_without_crashing(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "exp_old"
    _write_report_data(
        experiment_dir,
        {
            "schema_version": "report.v1",
            "experiment": {"experiment_id": "exp_old"},
            "iterations": [{"iteration": 1, "status": "valid_not_improved"}],
        },
    )
    _write_html(experiment_dir)
    _write_pdf(experiment_dir)
    _write_plots(experiment_dir)

    result = inspect_report(experiment_dir)

    assert result["status"] == "ok"
    assert result["files"]["report_data_json"]["schema_version"] == "report.v1"


def test_report_inspector_cli_json(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    experiment_dir = tmp_path / "results" / "experiments" / "exp_001"
    _write_complete_fake_report(experiment_dir)

    exit_code = main(["--experiment-dir", str(experiment_dir), "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["status"] == "ok"


def test_report_inspector_cli_failed_returns_nonzero(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "missing"

    exit_code = main(["--experiment-dir", str(experiment_dir)])

    assert exit_code == 1
