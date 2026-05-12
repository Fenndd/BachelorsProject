"""Optional PDF export helpers for generated HTML reports."""

from __future__ import annotations

from pathlib import Path


PLAYWRIGHT_INSTALL_HINT = (
    "Playwright PDF renderer also requires: python -m playwright install chromium"
)


class PdfExportError(RuntimeError):
    """Raised when HTML-to-PDF export cannot be completed."""


def export_pdf_from_html(
    html_path: Path | str,
    pdf_path: Path | str,
    *,
    renderer: str = "auto",
) -> Path:
    """Export an HTML report to PDF with WeasyPrint or Playwright."""

    source = Path(html_path)
    destination = Path(pdf_path)
    if not source.is_file():
        raise PdfExportError(f"HTML report does not exist: {source}")

    normalized_renderer = renderer.strip().lower()
    if normalized_renderer not in {"auto", "weasyprint", "playwright"}:
        raise PdfExportError(
            "Unsupported PDF renderer "
            f"{renderer!r}. Expected one of: auto, weasyprint, playwright."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    if normalized_renderer == "weasyprint":
        return _export_with_weasyprint(source, destination)
    if normalized_renderer == "playwright":
        return _export_with_playwright(source, destination)

    weasyprint_error: PdfExportError | None = None
    try:
        return _export_with_weasyprint(source, destination)
    except PdfExportError as exc:
        weasyprint_error = exc

    try:
        return _export_with_playwright(source, destination)
    except PdfExportError as playwright_error:
        raise PdfExportError(
            "No PDF renderer could export the report. "
            f"WeasyPrint error: {weasyprint_error}. "
            f"Playwright error: {playwright_error}. "
            "Install dependencies with `python -m pip install weasyprint playwright`. "
            f"{PLAYWRIGHT_INSTALL_HINT}."
        ) from playwright_error


def _export_with_weasyprint(html_path: Path, pdf_path: Path) -> Path:
    try:
        from weasyprint import HTML
    except ImportError as exc:
        raise PdfExportError(
            "WeasyPrint is not available. Install it with "
            "`python -m pip install weasyprint`."
        ) from exc

    try:
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    except Exception as exc:
        raise PdfExportError(f"WeasyPrint failed to export PDF: {exc}") from exc
    return pdf_path


def _export_with_playwright(html_path: Path, pdf_path: Path) -> Path:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PdfExportError(
            "Playwright is not available. Install it with "
            "`python -m pip install playwright`. "
            f"{PLAYWRIGHT_INSTALL_HINT}."
        ) from exc

    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            page.pdf(path=str(pdf_path), format="A4", print_background=True)
            browser.close()
            browser = None
    except PlaywrightError as exc:
        raise PdfExportError(
            "Playwright failed to export PDF. "
            f"{PLAYWRIGHT_INSTALL_HINT}. Error: {exc}"
        ) from exc
    except Exception as exc:
        raise PdfExportError(f"Playwright failed to export PDF: {exc}") from exc
    finally:
        if browser is not None:
            browser.close()
    return pdf_path


__all__ = [
    "PdfExportError",
    "export_pdf_from_html",
]
