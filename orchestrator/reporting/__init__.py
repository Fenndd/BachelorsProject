"""Reporting data contracts and helpers."""

from orchestrator.reporting.report_data import (
    KNOWN_ITERATION_STATUSES,
    REPORT_GENERATOR,
    REPORT_PROFILE_BASIC_SINGLE_EXPERIMENT,
    REPORT_SCHEMA_VERSION,
    ExperimentReportInfo,
    ReportArtifactMap,
    ReportBaselineMetrics,
    ReportBenchmarkConfig,
    ReportClosedLoopSelection,
    ReportData,
    ReportExperimentConfigDetails,
    ReportFinalBestCandidate,
    ReportFinalResult,
    ReportIterationSummary,
    ReportLlmInfo,
    ReportMetadata,
    ReportReasonSummaryItem,
    ReportReportingStatus,
    ReportStatusCounts,
    default_status_counts,
    make_empty_report_data,
    to_report_dict,
    write_report_data,
)
from orchestrator.reporting.report_data_collector import (
    collect_and_write_report_data,
    collect_report_data,
)
from orchestrator.reporting.figure_builder import build_report_figures
from orchestrator.reporting.generate_report import (
    generate_basic_html_report,
    generate_basic_report,
)
from orchestrator.reporting.html_renderer import render_report_html
from orchestrator.reporting.pdf_exporter import PdfExportError, export_pdf_from_html

__all__ = [
    "KNOWN_ITERATION_STATUSES",
    "REPORT_GENERATOR",
    "REPORT_PROFILE_BASIC_SINGLE_EXPERIMENT",
    "REPORT_SCHEMA_VERSION",
    "ExperimentReportInfo",
    "ReportArtifactMap",
    "ReportBaselineMetrics",
    "ReportBenchmarkConfig",
    "ReportClosedLoopSelection",
    "ReportData",
    "ReportExperimentConfigDetails",
    "ReportFinalBestCandidate",
    "ReportFinalResult",
    "ReportIterationSummary",
    "ReportLlmInfo",
    "ReportMetadata",
    "ReportReportingStatus",
    "ReportStatusCounts",
    "PdfExportError",
    "ReportReasonSummaryItem",
    "build_report_figures",
    "collect_and_write_report_data",
    "collect_report_data",
    "default_status_counts",
    "generate_basic_html_report",
    "generate_basic_report",
    "make_empty_report_data",
    "render_report_html",
    "export_pdf_from_html",
    "to_report_dict",
    "write_report_data",
]
