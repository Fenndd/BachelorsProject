from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

from pathlib import Path

import pytest

from orchestrator.reporting import PdfExportError, export_pdf_from_html
from orchestrator.reporting import pdf_exporter


def test_unknown_renderer_raises_pdf_export_error(tmp_path: Path) -> None:
    html_path = tmp_path / "report.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    with pytest.raises(PdfExportError, match="Unsupported PDF renderer"):
        export_pdf_from_html(html_path, tmp_path / "report.pdf", renderer="unknown")


def test_missing_html_path_raises_pdf_export_error(tmp_path: Path) -> None:
    with pytest.raises(PdfExportError, match="HTML report does not exist"):
        export_pdf_from_html(
            tmp_path / "missing.html",
            tmp_path / "report.pdf",
            renderer="weasyprint",
        )


def test_weasyprint_renderer_writes_pdf_with_monkeypatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html></html>", encoding="utf-8")

    def fake_export(source: Path, destination: Path) -> Path:
        assert source == html_path
        destination.write_bytes(b"%PDF-weasyprint")
        return destination

    monkeypatch.setattr(pdf_exporter, "_export_with_weasyprint", fake_export)

    output_path = export_pdf_from_html(html_path, pdf_path, renderer="weasyprint")

    assert output_path == pdf_path
    assert pdf_path.read_bytes() == b"%PDF-weasyprint"


def test_playwright_renderer_writes_pdf_with_monkeypatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html></html>", encoding="utf-8")

    def fake_export(source: Path, destination: Path) -> Path:
        assert source == html_path
        destination.write_bytes(b"%PDF-playwright")
        return destination

    monkeypatch.setattr(pdf_exporter, "_export_with_playwright", fake_export)

    output_path = export_pdf_from_html(html_path, pdf_path, renderer="playwright")

    assert output_path == pdf_path
    assert pdf_path.read_bytes() == b"%PDF-playwright"


def test_auto_renderer_falls_back_to_playwright(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text("<html></html>", encoding="utf-8")

    def fake_weasyprint(source: Path, destination: Path) -> Path:
        raise PdfExportError("weasyprint unavailable")

    def fake_playwright(source: Path, destination: Path) -> Path:
        destination.write_bytes(b"%PDF-fallback")
        return destination

    monkeypatch.setattr(pdf_exporter, "_export_with_weasyprint", fake_weasyprint)
    monkeypatch.setattr(pdf_exporter, "_export_with_playwright", fake_playwright)

    output_path = export_pdf_from_html(html_path, pdf_path, renderer="auto")

    assert output_path == pdf_path
    assert pdf_path.read_bytes() == b"%PDF-fallback"
