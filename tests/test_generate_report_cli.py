from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.reporting import generate_basic_report
from orchestrator.reporting import generate_report


TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"
EXPECTED_PLOTS = (
    "runtime_progress.svg",
    "candidate_runtime_by_iteration.svg",
    "runtime_reduction_by_iteration.svg",
    "correctness_metrics.svg",
    "status_breakdown.svg",
    "candidate_funnel.svg",
    "phase_timings.svg",
    "llm_tokens_by_iteration.svg",
    "llm_latency_by_iteration.svg",
    "failure_reason_breakdown.svg",
    "diff_stats_by_iteration.svg",
    "final_validation_runtime_distribution.svg",
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _summary() -> dict:
    return {
        "experiment_id": "exp_001",
        "target_file": TARGET_FILE,
        "total_iterations": 2,
        "completed_iterations": 2,
        "original_baseline_metrics_path": "missing_metrics.json",
        "final_best_iteration": 1,
        "final_optimized_source_dir": "results/experiments/exp_001/final_optimized_source",
        "final_optimized_source_diff_path": "results/experiments/exp_001/final_optimized_source.diff",
        "final_speedup_vs_original_baseline": 1.25,
        "final_runtime_reduction_percent": 20.0,
        "status_counts": {
            "accepted_improvement": 1,
            "valid_not_improved": 1,
        },
    }


def _experiment_dir(tmp_path: Path) -> Path:
    experiment_dir = tmp_path / "results" / "experiments" / "exp_001"
    _write_json(experiment_dir / "closed_loop_summary.json", _summary())
    _write_jsonl(
        experiment_dir / "closed_loop_iterations.jsonl",
        [
            {
                "iteration": 1,
                "status": "accepted_improvement",
                "candidate_summary": "Simplify arithmetic.",
                "runtime_ns_per_case_median": 800.0,
                "speedup_vs_original_baseline": 1.25,
                "correctness_passed": True,
                "current_best_updated": True,
            },
            {
                "iteration": 2,
                "status": "valid_not_improved",
                "runtime_ns_per_case_median": 820.0,
                "speedup_vs_original_baseline": 1.22,
                "correctness_passed": True,
            },
        ],
    )
    return experiment_dir


def _input_texts(experiment_dir: Path) -> tuple[str, str]:
    return (
        (experiment_dir / "closed_loop_summary.json").read_text(encoding="utf-8"),
        (experiment_dir / "closed_loop_iterations.jsonl").read_text(encoding="utf-8"),
    )


def _assert_inputs_unchanged(
    experiment_dir: Path,
    before: tuple[str, str],
) -> None:
    assert (experiment_dir / "closed_loop_summary.json").read_text(
        encoding="utf-8"
    ) == before[0]
    assert (experiment_dir / "closed_loop_iterations.jsonl").read_text(
        encoding="utf-8"
    ) == before[1]


def _assert_html_report_outputs(experiment_dir: Path) -> None:
    assert (experiment_dir / "report" / "report_data.json").is_file()
    assert (experiment_dir / "report" / "report.html").is_file()
    for filename in EXPECTED_PLOTS:
        assert (experiment_dir / "report" / "plots" / filename).is_file()


def test_generate_basic_report_html_only_does_not_require_pdf_exporter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    before = _input_texts(experiment_dir)

    def fail_pdf_export(*args: object, **kwargs: object) -> Path:
        raise AssertionError("PDF exporter should not be called for HTML-only report")

    monkeypatch.setattr(generate_report, "export_pdf_from_html", fail_pdf_export)

    artifacts = generate_basic_report(experiment_dir, formats=("html",))

    assert set(artifacts) == {"report_data", "html"}
    _assert_html_report_outputs(experiment_dir)
    assert not (experiment_dir / "report" / "report.pdf").exists()
    payload = json.loads((experiment_dir / "report" / "report_data.json").read_text(encoding="utf-8"))
    assert payload["reporting_status"]["status"] == "completed"
    assert payload["reporting_status"]["pdf_generated"] is False
    assert payload["reporting_status"]["report_pdf_path"] is None
    assert payload["reporting_status"]["pdf_display"] == 'Not generated. Current reporting formats: ["html"]'
    html = (experiment_dir / "report" / "report.html").read_text(encoding="utf-8")
    assert "<th>Status</th><td>completed</td>" in html
    _assert_inputs_unchanged(experiment_dir, before)


def test_generate_basic_report_pdf_calls_exporter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    calls: list[Path] = []

    def fake_pdf_export(html_path: Path, pdf_path: Path, *, renderer: str) -> Path:
        calls.append(html_path)
        assert html_path == experiment_dir / "report" / "report.html"
        html = html_path.read_text(encoding="utf-8")
        assert "<th>Status</th><td>completed</td>" in html
        assert "pdf_pending" not in html
        assert 'id="failure-analysis"' in html
        assert 'id="phase-timings"' in html
        assert 'id="llm-usage"' in html
        assert 'id="final-validation"' in html
        assert 'id="diff-statistics"' in html
        assert 'id="iteration-appendix"' in html
        assert renderer == "weasyprint"
        pdf_path.write_bytes(b"%PDF-dummy")
        return pdf_path

    monkeypatch.setattr(generate_report, "export_pdf_from_html", fake_pdf_export)

    artifacts = generate_basic_report(
        experiment_dir,
        formats=("html", "pdf"),
        renderer="weasyprint",
    )

    assert set(artifacts) == {"report_data", "html", "pdf"}
    assert calls == [experiment_dir / "report" / "report.html"]
    assert artifacts["pdf"] == experiment_dir / "report" / "report.pdf"
    assert artifacts["pdf"].read_bytes() == b"%PDF-dummy"
    payload = json.loads((experiment_dir / "report" / "report_data.json").read_text(encoding="utf-8"))
    assert payload["reporting_status"]["status"] == "completed"
    assert payload["reporting_status"]["pdf_generated"] is True
    assert payload["reporting_status"]["report_pdf_path"].endswith("report.pdf")
    html = (experiment_dir / "report" / "report.html").read_text(encoding="utf-8")
    assert "<th>Status</th><td>completed</td>" in html


def test_generate_basic_report_pdf_failure_writes_failed_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment_dir = _experiment_dir(tmp_path)

    def fake_pdf_export(html_path: Path, pdf_path: Path, *, renderer: str) -> Path:
        html = html_path.read_text(encoding="utf-8")
        assert "<th>Status</th><td>completed</td>" in html
        assert "pdf_pending" not in html
        raise RuntimeError("pdf boom")

    monkeypatch.setattr(generate_report, "export_pdf_from_html", fake_pdf_export)

    with pytest.raises(RuntimeError, match="pdf boom"):
        generate_basic_report(experiment_dir, formats=("html", "pdf"))

    payload = json.loads((experiment_dir / "report" / "report_data.json").read_text(encoding="utf-8"))
    assert payload["reporting_status"]["status"] == "failed"
    assert payload["reporting_status"]["pdf_generated"] is False
    assert payload["reporting_status"]["error"] == "pdf boom"
    html = (experiment_dir / "report" / "report.html").read_text(encoding="utf-8")
    assert "<th>Status</th><td>failed</td>" in html
    assert "pdf boom" in html


def test_cli_no_pdf_creates_html_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    experiment_dir = _experiment_dir(tmp_path)
    before = _input_texts(experiment_dir)

    def fail_pdf_export(*args: object, **kwargs: object) -> Path:
        raise AssertionError("PDF exporter should not be called for --no-pdf")

    monkeypatch.setattr(generate_report, "export_pdf_from_html", fail_pdf_export)

    exit_code = generate_report.main(
        ["--experiment-dir", str(experiment_dir), "--no-pdf"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "report_data:" in captured.out
    assert "html:" in captured.out
    assert "pdf:" not in captured.out
    _assert_html_report_outputs(experiment_dir)
    assert not (experiment_dir / "report" / "report.pdf").exists()
    _assert_inputs_unchanged(experiment_dir, before)


def test_cli_unknown_format_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    experiment_dir = _experiment_dir(tmp_path)

    exit_code = generate_report.main(
        ["--experiment-dir", str(experiment_dir), "--formats", "html,docx"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Unsupported report format" in captured.err
