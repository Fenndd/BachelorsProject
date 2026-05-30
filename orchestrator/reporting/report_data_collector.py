"""Read-only collector for normalized experiment report data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.reporting.report_data import (
    ExperimentReportInfo,
    ReportArtifactMap,
    ReportBaselineMetrics,
    ReportBenchmarkConfig,
    ReportClosedLoopSelection,
    ReportData,
    ReportExperimentConfigDetails,
    ReportExperimentMetadata,
    ReportFinalBestCandidate,
    ReportFinalSelection,
    ReportFinalResult,
    ReportDiffStats,
    ReportIterationSummary,
    ReportLlmUsage,
    ReportLlmInfo,
    ReportLlmUsageSummary,
    ReportOutcomeReason,
    ReportPhaseTimings,
    ReportReasonCodeCount,
    ReportReasonSummaryItem,
    ReportReportingStatus,
    ReportSelectionPolicy,
    default_status_counts,
    write_report_data,
)
from orchestrator.paths import paths
from orchestrator.shared.io.json_io import read_json, read_json_object

from orchestrator.experiments.outcome_reason import build_outcome_reason, outcome_reason_to_dict


def collect_report_data(
    experiment_dir: Path | str,
    *,
    output_path: Path | str | None = None,
    reporting_formats_override: tuple[str, ...] | list[str] | None = None,
    reporting_renderer_override: str | None = None,
) -> ReportData:
    """Collect normalized report data from persisted closed-loop artifacts."""

    experiment_path = Path(experiment_dir)
    summary_path = experiment_path / "closed_loop_summary.json"
    iterations_path = experiment_path / "closed_loop_iterations.jsonl"
    _require_file(summary_path, "closed-loop summary")
    _require_file(iterations_path, "closed-loop iterations")

    summary = read_json_object(summary_path)
    records = _read_jsonl_objects(iterations_path)
    report_data_path = (
        Path(output_path)
        if output_path is not None
        else experiment_path / "report" / "report_data.json"
    )

    # Optional artifacts — never raise on missing/invalid
    config_snapshot = _safe_read_json_object(
        experiment_path / "experiment_config_snapshot.json"
    ) or {}
    config_effective = _safe_read_json_object(
        experiment_path / "experiment_config_effective.json"
    ) or {}
    status_payload = _safe_read_json_object(
        experiment_path / "experiment_status.json"
    ) or {}
    current_best_state = _safe_read_json_object(
        experiment_path / "current_best_state.json"
    ) or {}
    selection_report = _safe_read_json_object(
        experiment_path / "closed_loop_selection_report.json"
    ) or {}
    experiment_metadata = _safe_read_json_object(
        experiment_path / "experiment_metadata.json"
    ) or {}
    final_selection = _build_final_selection(experiment_path)

    # Resolve LLM config
    variant_llm_config = _load_resolved_llm_config(experiment_path, config_snapshot)

    # Load baseline metrics (dict form for benchmark config extraction too)
    baseline_metrics, baseline_raw = _load_baseline_metrics_with_raw(
        summary.get("original_baseline_metrics_path"),
        experiment_path,
    )

    status_counts = _status_counts(summary, records)

    # Build iteration summaries first (needed for correctness_preserved and final_best)
    iterations = [_iteration_summary(record, experiment_path) for record in records]

    final_best_iter = _int_or_default(summary.get("final_best_iteration"))

    llm_info = _build_llm_info(config_snapshot, variant_llm_config)

    final_result = ReportFinalResult(
        final_best_iteration=final_best_iter,
        final_speedup_vs_baseline=None,
        final_runtime_reduction_percent=None,
        accepted_improvements=status_counts["accepted_improvement"],
        correctness_preserved=None,
    )
    final_best_candidate = _build_final_best_candidate(
        summary, iterations, baseline_metrics, records, experiment_path
    )
    _apply_final_selection_overrides(
        final_result,
        final_best_candidate,
        final_selection,
    )

    report_data = ReportData(
        experiment=ExperimentReportInfo(
            experiment_id=_string_or_default(summary.get("experiment_id")),
            experiment_name=_first_string(
                config_snapshot.get("experiment_name"),
                summary.get("experiment_id"),
            ),
            target_file=_string_or_default(summary.get("target_file")),
            model=llm_info.model,
            total_iterations=_int_or_default(summary.get("total_iterations")),
            completed_iterations=_int_or_default(summary.get("completed_iterations")),
            experiment_mode="closed_loop",
            benchmark_family=_string_or_none(
                _nested_get(baseline_raw, "benchmark", "family")
            )
            if baseline_raw
            else None,
        ),
        final_result=final_result,
        selection_policy=_build_selection_policy(config_snapshot),
        baseline_metrics=baseline_metrics,
        iterations=iterations,
        status_counts=status_counts,
        artifacts=_artifact_map(
            experiment_path,
            summary,
            report_data_path=report_data_path,
        ),
        llm=llm_info,
        llm_usage_summary=_build_llm_usage_summary(iterations),
        experiment_config_details=_build_experiment_config_details(
            config_snapshot, config_effective, experiment_path
        ),
        benchmark_config=_build_benchmark_config(baseline_raw, experiment_metadata),
        closed_loop_selection=_build_closed_loop_selection(
            selection_report, current_best_state, experiment_path
        ),
        final_best_candidate=final_best_candidate,
        reporting_status=_build_reporting_status(
            experiment_path, config_snapshot, status_payload,
            formats_override=reporting_formats_override,
            renderer_override=reporting_renderer_override,
        ),
        final_selection=final_selection,
        reason_summary=_build_reason_summary(iterations),
        reason_code_counts=_build_reason_code_counts(iterations),
        experiment_metadata=_build_experiment_metadata(experiment_metadata),
    )

    report_data.final_code_diff = _load_final_code_diff(summary, experiment_path)
    report_data.executive_narrative = _build_executive_narrative(report_data)
    report_data.closed_loop_selection_explanation = _build_closed_loop_selection_explanation(
        report_data
    )

    if output_path is not None:
        write_report_data(report_data_path, report_data)
    return report_data


def collect_and_write_report_data(
    experiment_dir: Path | str,
    output_path: Path | str | None = None,
    *,
    reporting_formats_override: tuple[str, ...] | list[str] | None = None,
    reporting_renderer_override: str | None = None,
) -> Path:
    """Collect report data and write report/report_data.json."""

    experiment_path = Path(experiment_dir)
    report_data_path = (
        Path(output_path)
        if output_path is not None
        else experiment_path / "report" / "report_data.json"
    )
    collect_report_data(
        experiment_path,
        output_path=report_data_path,
        reporting_formats_override=reporting_formats_override,
        reporting_renderer_override=reporting_renderer_override,
    )
    return report_data_path


# ---------------------------------------------------------------------------
# Display path helper (repo-relative for UI output)
# ---------------------------------------------------------------------------

def _display_path(path: Any, experiment_dir: Path | None = None) -> str | None:
    """Convert a path to a repo-relative POSIX string for display."""

    if path is None:
        return None
    path_text = _path_text_or_none(path)
    if not path_text:
        return None

    _KNOWN_PREFIXES = (
        "results/", "workspace/", "configs/", "cpp/",
        "orchestrator/", "tests/",
    )

    path_obj = Path(path_text)
    if not path_obj.is_absolute():
        normalized = path_obj.as_posix()
        if any(normalized.startswith(p) for p in _KNOWN_PREFIXES):
            return normalized
        try:
            candidate = (paths.repo_root / normalized).resolve()
            return candidate.relative_to(paths.repo_root).as_posix()
        except (ValueError, OSError):
            pass
        if experiment_dir is not None:
            try:
                candidate = (experiment_dir / normalized).resolve()
                return candidate.relative_to(paths.repo_root).as_posix()
            except (ValueError, OSError):
                pass
        try:
            candidate = (Path.cwd() / normalized).resolve()
            return candidate.relative_to(paths.repo_root).as_posix()
        except (ValueError, OSError):
            pass
        return normalized

    try:
        resolved = path_obj.resolve()
    except (OSError, ValueError):
        return path_text

    try:
        return resolved.relative_to(paths.repo_root).as_posix()
    except ValueError:
        pass

    workspace_root = paths.repo_root / "workspace"
    try:
        return (Path("workspace") / resolved.relative_to(workspace_root)).as_posix()
    except ValueError:
        pass

    if experiment_dir is not None:
        try:
            return resolved.relative_to(experiment_dir.parent).as_posix()
        except ValueError:
            pass

    return path_text


# ---------------------------------------------------------------------------
# Artifact loaders
# ---------------------------------------------------------------------------

def _load_resolved_llm_config(
    experiment_path: Path,
    config_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Load the resolved LLM config JSON."""

    if not config_snapshot:
        return {}

    exact_path = experiment_path / "resolved_llm_config.json"
    result = _safe_read_json_object(exact_path)
    if result is not None:
        return result

    # Compatibility for older experiment artifacts that wrote a variant_configs directory.
    variant_configs_dir = experiment_path / "variant_configs"
    if variant_configs_dir.is_dir():
        for json_file in sorted(variant_configs_dir.glob("*.json")):
            result = _safe_read_json_object(json_file)
            if result is not None:
                return result

    return {}


def _build_llm_info(
    config_snapshot: dict[str, Any],
    variant_llm_config: dict[str, Any],
) -> ReportLlmInfo:
    """Build ReportLlmInfo from config snapshot and resolved LLM config."""

    if not config_snapshot and not variant_llm_config:
        return ReportLlmInfo()

    thinking = variant_llm_config.get("thinking") or {}

    return ReportLlmInfo(
        provider=_string_or_none(variant_llm_config.get("provider")),
        model=_string_or_none(variant_llm_config.get("model")),
        llm_config=_string_or_none(config_snapshot.get("llm_config")),
        thinking_enabled=_bool_or_none(thinking.get("enabled")),
        thinking_effort=_string_or_none(thinking.get("effort")),
        max_tokens=_int_or_none(variant_llm_config.get("max_tokens")),
    )


def _build_experiment_config_details(
    config_snapshot: dict[str, Any],
    config_effective: dict[str, Any],
    experiment_path: Path,
) -> ReportExperimentConfigDetails:
    """Build ReportExperimentConfigDetails from config snapshot and effective config."""

    if not config_snapshot:
        return ReportExperimentConfigDetails()

    sel = config_snapshot.get("selection") or {}
    rep = config_snapshot.get("reporting") or {}

    scope_snapshot = config_snapshot.get("optimization_scope")
    scope_effective = config_effective.get("optimization_scope")
    allowed_files = (
        scope_effective.get("allowed_files")
        if isinstance(scope_effective, dict) and scope_effective.get("allowed_files")
        else scope_snapshot.get("allowed_files")
        if isinstance(scope_snapshot, dict)
        else None
    )
    reporting_formats = rep.get("formats")

    baseline_run_dir = _string_or_none(config_snapshot.get("baseline_run_dir"))
    if baseline_run_dir is None and isinstance(sel, dict):
        # Compatibility for reports generated from older experiment snapshots.
        baseline_run_dir = _string_or_none(sel.get("baseline_run_dir"))

    return ReportExperimentConfigDetails(
        description=_string_or_none(config_snapshot.get("description")),
        baseline_run_dir=_display_path(baseline_run_dir, experiment_path)
        if baseline_run_dir
        else None,
        optimization_scope_allowed_files=list(allowed_files)
        if isinstance(allowed_files, list)
        else [],
        reporting_enabled=_bool_or_none(rep.get("enabled")),
        reporting_formats=list(reporting_formats)
        if isinstance(reporting_formats, list)
        else [],
        reporting_renderer=_string_or_none(rep.get("renderer")),
    )


def _build_selection_policy(config_snapshot: dict[str, Any]) -> ReportSelectionPolicy:
    selection = config_snapshot.get("selection")
    selection = selection if isinstance(selection, dict) else {}
    gt_found_max_drop_points = _number_or_none(selection.get("gt_found_max_drop_points"))
    return ReportSelectionPolicy(
        gt_found_gate_enabled=gt_found_max_drop_points is not None,
        gt_found_max_drop_points=gt_found_max_drop_points,
    )


def _build_benchmark_config(
    baseline_raw: dict[str, Any] | None,
    experiment_metadata: dict[str, Any] | None = None,
) -> ReportBenchmarkConfig:
    """Build ReportBenchmarkConfig from raw baseline metrics payload."""

    experiment_metadata = experiment_metadata or {}
    metadata_environment = experiment_metadata.get("environment")
    if not isinstance(metadata_environment, dict):
        metadata_environment = {}

    if not baseline_raw:
        return ReportBenchmarkConfig(
            build_type=_first_string(metadata_environment.get("cmake_build_type"), "Release")
            or "Release"
        )

    bm = baseline_raw.get("benchmark") or {}

    # Try nested option dicts in priority order
    opts: dict[str, Any] = {}
    for key in ("benchmark_options", "options", "config"):
        candidate = bm.get(key)
        if isinstance(candidate, dict):
            opts = candidate
            break

    def _b_str(key: str, *fallbacks: str) -> str | None:
        for k in (key, *fallbacks):
            v = _string_or_none(bm.get(k))
            if v is not None:
                return v
        return None

    def _o_int(key: str, *fallbacks: str) -> int | None:
        for k in (key, *fallbacks):
            v = _int_or_none(opts.get(k))
            if v is not None:
                return v
            v = _int_or_none(bm.get(k))
            if v is not None:
                return v
        return None

    def _o_float(key: str, *fallbacks: str) -> float | None:
        for k in (key, *fallbacks):
            v = _number_or_none(opts.get(k))
            if v is not None:
                return v
            v = _number_or_none(bm.get(k))
            if v is not None:
                return v
        return None

    def _o_bool(key: str) -> bool | None:
        v = _bool_or_none(opts.get(key))
        if v is not None:
            return v
        return _bool_or_none(bm.get(key))

    def _o_str(key: str, *fallbacks: str) -> str | None:
        for k in (key, *fallbacks):
            v = _string_or_none(opts.get(k))
            if v is not None:
                return v
            v = _string_or_none(bm.get(k))
            if v is not None:
                return v
        return None

    return ReportBenchmarkConfig(
        family=_b_str("family"),
        solver=_b_str("solver", "parsed_solver_name"),
        num_problems=_o_int("num_problems", "parsed_num_problems"),
        n_point_point=_o_int("n_point_point"),
        n_point_line=_o_int("n_point_line"),
        tolerance=_o_float("tolerance"),
        camera_fov=_o_float("camera_fov"),
        timed_iterations=_o_int("timed_iterations"),
        seed=_o_int("random_seed", "seed"),
        runtime_unit=_o_str("runtime_unit"),
        build_type=_first_string(
            _o_str("build_type"),
            _b_str("build_type"),
            metadata_environment.get("cmake_build_type"),
            "Release",
        ),
    )


def _build_closed_loop_selection(
    selection_report: dict[str, Any],
    current_best_state: dict[str, Any],
    experiment_path: Path,
) -> ReportClosedLoopSelection:
    """Build ReportClosedLoopSelection from selection report and current_best_state."""

    if not selection_report and not current_best_state:
        return ReportClosedLoopSelection()

    fcb = selection_report.get("final_current_best") or {}
    bvc = selection_report.get("best_verified_candidate_vs_original_baseline") or {}

    return ReportClosedLoopSelection(
        promotion_policy=_string_or_none(selection_report.get("promotion_policy")),
        final_current_best_iteration=_first_available_int(
            fcb.get("iteration"),
            current_best_state.get("current_best_iteration"),
        ),
        final_current_best_is_baseline=_first_available_bool(
            fcb.get("is_baseline"),
            current_best_state.get("current_best_is_baseline"),
        ),
        final_current_best_run_dir=_display_path(
            _first_string(
                fcb.get("run_dir"),
                current_best_state.get("current_best_run_dir"),
            ),
            experiment_path,
        ),
        final_current_best_source_dir=_display_path(
            _first_string(
                fcb.get("source_dir"),
                current_best_state.get("current_best_source_dir"),
            ),
            experiment_path,
        ),
        final_current_best_metrics_path=_display_path(
            _first_string(
                fcb.get("metrics_path"),
                current_best_state.get("current_best_metrics_path"),
            ),
            experiment_path,
        ),
        best_verified_candidate_iteration=_int_or_none(bvc.get("iteration")),
        best_verified_candidate_run_dir=_display_path(
            bvc.get("candidate_run_dir"), experiment_path
        ),
        best_verified_candidate_speedup_vs_baseline=_number_or_none(bvc.get("speedup")),
        best_verified_candidate_runtime_reduction_percent=_number_or_none(
            bvc.get("runtime_reduction_percent")
        ),
        matches_final_current_best=_bool_or_none(bvc.get("matches_final_current_best")),
    )


def _build_final_selection(experiment_path: Path) -> ReportFinalSelection:
    report_path = experiment_path / "final_selection_report.json"
    payload = _safe_read_json_object(report_path)
    if not isinstance(payload, dict):
        return ReportFinalSelection()
    comparison_raw = payload.get("comparison")
    comparison: dict[str, Any] = comparison_raw if isinstance(comparison_raw, dict) else {}
    final_benchmark = payload.get("final_benchmark")
    final_benchmark = final_benchmark if isinstance(final_benchmark, dict) else {}
    final_aggregate = final_benchmark.get("repeated_benchmark_aggregate")
    final_aggregate = final_aggregate if isinstance(final_aggregate, dict) else {}
    return ReportFinalSelection(
        status=_string_or_none(payload.get("status")),
        final_best_is_baseline=_bool_or_none(payload.get("final_best_is_baseline")),
        report_path=_display_path(report_path, experiment_path),
        speedup_vs_original_baseline=_number_or_none(comparison.get("speedup")),
        runtime_reduction_percent=_number_or_none(comparison.get("runtime_reduction_percent")),
        baseline_runtime_ns_per_problem_median=_number_or_none(
            comparison.get("baseline_runtime_ns_per_problem_median")
        ),
        final_runtime_ns_per_problem_median=_number_or_none(
            comparison.get("final_runtime_ns_per_problem_median")
        ),
        baseline_gt_found_percent=_number_or_none(
            comparison.get("baseline_gt_found_percent")
        ),
        final_gt_found_percent=_number_or_none(
            comparison.get("final_gt_found_percent")
        ),
        final_gt_found_delta_points=_number_or_none(
            comparison.get("final_gt_found_delta_points")
        ),
        final_correctness_passed=_bool_or_none(
            (payload.get("final_benchmark") or {}).get("parsed_correctness_passed")
            if isinstance(payload.get("final_benchmark"), dict)
            else None
        ),
        baseline_benchmark_run_count=_int_or_none(comparison.get("baseline_benchmark_run_count")),
        final_benchmark_run_count=_int_or_none(comparison.get("final_benchmark_run_count")),
        decision_metric=_string_or_none(comparison.get("decision_metric")),
        baseline_valid_solutions_percent=_number_or_none(
            comparison.get("baseline_valid_solutions_percent")
        ),
        final_valid_solutions_percent=_number_or_none(
            comparison.get("final_valid_solutions_percent")
        ),
        final_valid_solutions_delta_points=_number_or_none(
            comparison.get("final_valid_solutions_delta_points")
        ),
        final_min_runtime_ns_per_problem_median=_number_or_none(
            final_aggregate.get("min_runtime_ns_per_problem_median")
        ),
        final_total_benchmark_wall_seconds=_number_or_none(
            final_aggregate.get("total_benchmark_wall_seconds")
        ),
    )


def _apply_final_selection_overrides(
    final_result: ReportFinalResult,
    final_best_candidate: ReportFinalBestCandidate,
    final_selection: ReportFinalSelection,
) -> None:
    if final_selection.status not in {"completed", "skipped"}:
        return
    speedup = final_selection.speedup_vs_original_baseline
    reduction = final_selection.runtime_reduction_percent
    if speedup is None or reduction is None:
        return

    final_result.final_speedup_vs_baseline = speedup
    final_result.final_runtime_reduction_percent = reduction
    final_result.correctness_preserved = final_selection.final_correctness_passed

    baseline_runtime = final_selection.baseline_runtime_ns_per_problem_median
    final_runtime = final_selection.final_runtime_ns_per_problem_median
    final_best_candidate.runtime_ns_per_problem_median = final_runtime
    final_best_candidate.baseline_runtime_ns_per_problem_median = baseline_runtime
    final_best_candidate.absolute_runtime_difference_ns_per_problem = (
        baseline_runtime - final_runtime
        if baseline_runtime is not None and final_runtime is not None
        else None
    )
    final_best_candidate.speedup_vs_baseline = speedup
    final_best_candidate.runtime_reduction_percent = reduction
    final_best_candidate.correctness_passed = final_selection.final_correctness_passed
    final_best_candidate.baseline_gt_found_percent = final_selection.baseline_gt_found_percent
    final_best_candidate.gt_found_percent = final_selection.final_gt_found_percent
    final_best_candidate.gt_found_delta_points = final_selection.final_gt_found_delta_points
    final_best_candidate.benchmark_run_count = final_selection.final_benchmark_run_count
    final_best_candidate.decision_metric = final_selection.decision_metric
    final_best_candidate.min_runtime_ns_per_problem_median = final_selection.final_min_runtime_ns_per_problem_median
    final_best_candidate.total_benchmark_wall_seconds = final_selection.final_total_benchmark_wall_seconds


def _build_experiment_metadata(
    payload: dict[str, Any],
) -> ReportExperimentMetadata | None:
    if not payload:
        return None
    repository = payload.get("repository")
    environment = payload.get("environment")
    return ReportExperimentMetadata(
        schema_version=_string_or_none(payload.get("schema_version")),
        started_at=_string_or_none(payload.get("started_at")),
        finished_at=_string_or_none(payload.get("finished_at")),
        total_duration_seconds=_number_or_none(payload.get("total_duration_seconds")),
        repository=repository if isinstance(repository, dict) else {},
        environment=environment if isinstance(environment, dict) else {},
    )


def _build_final_best_candidate(
    summary: dict[str, Any],
    iterations: list[ReportIterationSummary],
    baseline_metrics: ReportBaselineMetrics,
    records: list[dict[str, Any]],
    experiment_path: Path,
) -> ReportFinalBestCandidate:
    """Build ReportFinalBestCandidate from summary, iterations, and per-candidate artifacts."""

    final_best_iter = _int_or_default(summary.get("final_best_iteration"))
    baseline_rt = baseline_metrics.runtime_ns_per_problem_median

    # Find matching iteration summary
    best_iter_summary: ReportIterationSummary | None = None
    for it in iterations:
        if it.iteration == final_best_iter:
            if best_iter_summary is None or it.promoted:
                best_iter_summary = it

    if final_best_iter == 0:
        # Baseline is best
        final_rt = baseline_rt
        correctness = baseline_metrics.correctness_passed
        candidate_summary = None
        expected_effect = None
        risk_level = None
        candidate_run_dir_display = None
    else:
        final_rt = best_iter_summary.runtime_ns_per_problem_median if best_iter_summary else None
        correctness = best_iter_summary.correctness_passed if best_iter_summary else None
        candidate_summary = best_iter_summary.candidate_summary if best_iter_summary else None
        expected_effect = best_iter_summary.expected_effect if best_iter_summary else None
        risk_level = best_iter_summary.risk_level if best_iter_summary else None
        candidate_run_dir_display = _display_path(
            summary.get("final_best_candidate_run_dir"), experiment_path
        )

    # Absolute runtime difference
    abs_diff: float | None = None
    if final_rt is not None and baseline_rt is not None:
        abs_diff = baseline_rt - final_rt

    # Changed files from materialization.json of the best candidate record
    changed_files: list[str] = []
    if final_best_iter > 0 and best_iter_summary is not None:
        best_candidate_run_dir_text = _path_text_or_none(
            best_iter_summary.candidate_run_dir
        )
        if best_candidate_run_dir_text:
            candidate_dir = _resolve_existing_dir_or_display_path(
                best_candidate_run_dir_text, experiment_path
            )
            mat = _safe_read_json_object(candidate_dir / "materialization.json")
            if isinstance(mat, dict):
                raw_files = mat.get("changed_files")
                if isinstance(raw_files, list):
                    changed_files = [str(f) for f in raw_files if f]

    final_diff_stats = _safe_read_json_object(experiment_path / "final_diff_stats.json")
    if not isinstance(final_diff_stats, dict):
        final_diff_stats = summary.get("final_diff_stats") if isinstance(summary.get("final_diff_stats"), dict) else None

    return ReportFinalBestCandidate(
        iteration=final_best_iter,
        candidate_run_dir=candidate_run_dir_display if final_best_iter > 0 else None,
        runtime_ns_per_problem_median=None,
        baseline_runtime_ns_per_problem_median=None,
        absolute_runtime_difference_ns_per_problem=None,
        speedup_vs_baseline=None,
        runtime_reduction_percent=None,
        correctness_passed=None,
        candidate_summary=candidate_summary,
        expected_effect=expected_effect,
        risk_level=risk_level,
        changed_files=changed_files,
        final_optimized_source=_display_path(
            summary.get("final_optimized_source_dir"), experiment_path
        ),
        final_diff=_display_path(
            summary.get("final_optimized_source_diff_path"), experiment_path
        ),
        diff_stats=_build_diff_stats(final_diff_stats),
    )


def _build_reporting_status(
    experiment_path: Path,
    config_snapshot: dict[str, Any],
    status_payload: dict[str, Any],
    formats_override: tuple[str, ...] | list[str] | None = None,
    renderer_override: str | None = None,
) -> ReportReportingStatus:
    """Build ReportReportingStatus from runner status block and config snapshot."""

    runner_rep = status_payload.get("reporting") or {}
    config_rep = config_snapshot.get("reporting") or {}

    enabled = _first_available_bool(
        runner_rep.get("enabled"),
        config_rep.get("enabled"),
    )
    status = _string_or_none(runner_rep.get("status"))

    # Priority for formats: override > runner > config > empty
    if formats_override is not None:
        seen: set[str] = set()
        deduped: list[str] = []
        for fmt in formats_override:
            f = fmt.strip().lower()
            if f in ("html", "pdf") and f not in seen:
                seen.add(f)
                deduped.append(f)
        formats = deduped
    else:
        formats_raw = runner_rep.get("formats") or config_rep.get("formats")
        formats = list(formats_raw) if isinstance(formats_raw, list) else []

    # Priority for renderer: override > runner > config > "auto"
    renderer = _first_string(
        renderer_override,
        runner_rep.get("renderer"),
        config_rep.get("renderer"),
    ) or "auto"

    error = _string_or_none(runner_rep.get("error"))

    report_dir = experiment_path / "report"
    report_data_file = report_dir / "report_data.json"
    report_html_file = report_dir / "report.html"
    report_pdf_file = report_dir / "report.pdf"

    report_data_path = _display_path(report_data_file, experiment_path)
    report_html_path = _display_path(report_html_file, experiment_path)

    if report_pdf_file.exists():
        pdf_generated = True
        report_pdf_path = _display_path(report_pdf_file, experiment_path)
        pdf_display = report_pdf_path
    else:
        pdf_generated = False
        report_pdf_path = None
        if "pdf" not in formats:
            formats_json = json.dumps(formats)
            pdf_display = f"Not generated. Current reporting formats: {formats_json}"
        else:
            pdf_display = "PDF requested; generation pending or file missing"

    return ReportReportingStatus(
        enabled=enabled,
        status=status,
        formats=formats,
        renderer=renderer,
        report_data_path=report_data_path,
        report_html_path=report_html_path,
        report_pdf_path=report_pdf_path,
        pdf_generated=pdf_generated,
        pdf_display=pdf_display,
        error=error,
    )


def _derive_correctness_preserved(
    final_best_iter: int,
    iterations: list[ReportIterationSummary],
    baseline_metrics: ReportBaselineMetrics,
) -> bool | None:
    """Infer correctness_preserved from baseline or the promoted final iteration."""

    if final_best_iter == 0:
        return baseline_metrics.correctness_passed

    best: ReportIterationSummary | None = None
    for it in iterations:
        if it.iteration == final_best_iter:
            if best is None or it.promoted:
                best = it
    if best is not None:
        return best.correctness_passed
    return None


# ---------------------------------------------------------------------------
# Internal helpers (unchanged from v1)
# ---------------------------------------------------------------------------

def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required {label} artifact: {path}")


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object on line {line_number} in: {path}")
        records.append(payload)
    return records


def _status_counts(
    summary: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, int]:
    counts = default_status_counts()
    raw_counts = summary.get("status_counts")
    if isinstance(raw_counts, dict):
        for status, value in raw_counts.items():
            if (
                status in counts
                and isinstance(value, int)
                and not isinstance(value, bool)
            ):
                counts[status] = value
        return counts

    for record in records:
        status = record.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _iteration_summary(
    record: dict[str, Any],
    experiment_dir: Path,
) -> ReportIterationSummary:
    candidate_run_dir_text = _path_text_or_none(record.get("candidate_run_dir"))
    candidate_run_dir = (
        _resolve_existing_dir_or_display_path(candidate_run_dir_text, experiment_dir)
        if candidate_run_dir_text is not None
        else None
    )
    artifacts = _candidate_artifacts(candidate_run_dir)
    candidate = artifacts.get("candidate") or {}
    verification = artifacts.get("verification") or {}
    decision_vs_current_best = _decision_object(
        record.get("decision_vs_current_best"),
        artifacts.get("decision_vs_current_best"),
    )
    decision_vs_original_baseline = _decision_object(
        record.get("decision_vs_original_baseline"),
        artifacts.get("decision_vs_original_baseline"),
    )
    outcome_reason = _build_outcome_reason(
        record,
        candidate_run_dir,
        candidate_run_dir_text,
        artifacts,
        candidate,
        decision_vs_current_best,
    )

    return ReportIterationSummary(
        iteration=_int_or_default(record.get("iteration")),
        status=_string_or_default(record.get("status")),
        candidate_summary=_first_summary_text(
            record.get("candidate_summary"),
            candidate.get("summary"),
        ),
        expected_effect=_first_string(
            record.get("candidate_expected_effect"),
            candidate.get("expected_effect"),
        ),
        risk_level=_first_string(
            record.get("candidate_risk_level"),
            candidate.get("risk_level"),
        ),
        runtime_ns_per_problem_median=_first_available_number(
            record.get("runtime_ns_per_problem_median"),
            _verification_runtime(verification),
        ),
        gt_found_percent=_first_available_number(
            record.get("gt_found_percent"),
            _verification_gt_found(verification),
            _decision_comparison_number(decision_vs_current_best, "candidate_gt_found_percent"),
            _decision_comparison_number(decision_vs_original_baseline, "candidate_gt_found_percent"),
        ),
        gt_found_delta_points_vs_original_baseline=_first_available_number(
            record.get("gt_found_delta_points_vs_original_baseline"),
            _decision_comparison_number(decision_vs_original_baseline, "gt_found_delta_points"),
        ),
        gt_found_delta_points_vs_current_best=_first_available_number(
            record.get("gt_found_delta_points_vs_current_best"),
            _decision_comparison_number(decision_vs_current_best, "gt_found_delta_points"),
        ),
        speedup_vs_current_best=_first_available_number(
            record.get("speedup_vs_current_best"),
            _decision_speedup(decision_vs_current_best),
        ),
        speedup_vs_baseline=_first_available_number(
            record.get("speedup_vs_original_baseline"),
            _decision_speedup(decision_vs_original_baseline),
        ),
        correctness_passed=_first_available_bool(
            record.get("correctness_passed"),
            _verification_correctness(verification),
        ),
        benchmark_run_count=_first_available_int(
            record.get("benchmark_run_count"),
            _verification_benchmark_run_count(verification),
        ),
        decision_metric=_first_string(
            record.get("decision_metric"),
            _verification_decision_metric(verification),
        ),
        min_runtime_ns_per_problem_median=_first_available_number(
            record.get("min_runtime_ns_per_problem_median"),
            _verification_aggregate_number(verification, "min_runtime_ns_per_problem_median"),
        ),
        total_benchmark_wall_seconds=_first_available_number(
            record.get("total_benchmark_wall_seconds"),
            _verification_aggregate_number(verification, "total_benchmark_wall_seconds"),
        ),
        promoted=record.get("current_best_updated") is True,
        reason=_extract_reason(
            record,
            decision_vs_current_best=artifacts.get("decision_vs_current_best"),
        ),
        candidate_run_dir=candidate_run_dir_text,
        phase_timings=_build_phase_timings(record.get("phase_timings")),
        llm_usage=_build_llm_usage((artifacts.get("llm_response") or {}).get("llm_usage")),
        diff_stats=_build_diff_stats((artifacts.get("materialization") or {}).get("diff_stats")),
        outcome_reason=outcome_reason,
    )


def _candidate_artifacts(candidate_run_dir: Path | None) -> dict[str, dict[str, Any] | None]:
    if candidate_run_dir is None:
        return {}
    return {
        "verification": _safe_read_json_object(candidate_run_dir / "verification.json"),
        "decision_vs_current_best": _safe_read_json_object(
            candidate_run_dir / "decision_vs_current_best.json"
        ),
        "decision_vs_original_baseline": _safe_read_json_object(
            candidate_run_dir / "decision_vs_original_baseline.json"
        ),
        "candidate": _safe_read_json_object(candidate_run_dir / "candidate.json"),
        "status": _safe_read_json_object(candidate_run_dir / "status.json"),
        "llm_response": _safe_read_json_object(candidate_run_dir / "llm_response.json"),
        "materialization": _safe_read_json_object(
            candidate_run_dir / "materialization.json"
        ),
    }


def _build_phase_timings(value: Any) -> ReportPhaseTimings | None:
    if not isinstance(value, dict):
        return None
    return ReportPhaseTimings(
        generation_seconds=_number_or_none(value.get("generation_seconds")),
        materialization_seconds=_number_or_none(value.get("materialization_seconds")),
        verification_seconds=_number_or_none(value.get("verification_seconds")),
        benchmark_seconds=_number_or_none(value.get("benchmark_seconds")),
        total_iteration_seconds=_number_or_none(value.get("total_iteration_seconds")),
    )


def _build_outcome_reason(
    record: dict[str, Any],
    candidate_run_dir: Path | None,
    candidate_run_dir_text: str | None,
    artifacts: dict[str, dict[str, Any] | None],
    candidate: dict[str, Any],
    decision_vs_current_best: dict[str, Any] | None,
) -> ReportOutcomeReason:
    existing = record.get("outcome_reason")
    if isinstance(existing, dict):
        return _report_outcome_reason(existing)
    source_artifacts = _source_artifacts(candidate_run_dir, candidate_run_dir_text)
    generation = artifacts.get("status") if record.get("status") == "generation_failed" else None
    reason = build_outcome_reason(
        status=_string_or_default(record.get("status")),
        record=record,
        candidate_run_dir=candidate_run_dir_text,
        candidate=candidate,
        generation=generation,
        materialization=artifacts.get("materialization"),
        verification=artifacts.get("verification"),
        decision_vs_current_best=decision_vs_current_best,
        source_artifacts=source_artifacts,
    )
    return _report_outcome_reason(outcome_reason_to_dict(reason) or {})


def _report_outcome_reason(value: dict[str, Any]) -> ReportOutcomeReason:
    return ReportOutcomeReason(
        category=_string_or_none(value.get("category")),
        code=_string_or_none(value.get("code")),
        severity=_string_or_none(value.get("severity")),
        message=_string_or_none(value.get("message")),
        source_artifact=_string_or_none(value.get("source_artifact")),
    )


def _source_artifacts(
    candidate_run_dir: Path | None,
    candidate_run_dir_text: str | None,
) -> dict[str, str | None]:
    if candidate_run_dir is None:
        return {}
    display_root = candidate_run_dir_text or str(candidate_run_dir)
    return {
        "status": _display_path(candidate_run_dir / "status.json"),
        "candidate": _display_path(candidate_run_dir / "candidate.json"),
        "materialization": _display_path(candidate_run_dir / "materialization.json"),
        "verification": _display_path(candidate_run_dir / "verification.json"),
        "decision_vs_current_best": _display_path(candidate_run_dir / "decision_vs_current_best.json"),
        "decision_vs_original_baseline": _display_path(candidate_run_dir / "decision_vs_original_baseline.json"),
        "candidate_run_dir": display_root,
    }


def _build_llm_usage(value: Any) -> ReportLlmUsage | None:
    if not isinstance(value, dict):
        return None
    return ReportLlmUsage(
        prompt_tokens=_int_or_none(value.get("prompt_tokens")),
        completion_tokens=_int_or_none(value.get("completion_tokens")),
        total_tokens=_int_or_none(value.get("total_tokens")),
        api_latency_seconds=_number_or_none(value.get("api_latency_seconds")),
        finish_reason=_string_or_none(value.get("finish_reason")),
        model=_string_or_none(value.get("model")),
        model_version=_string_or_none(value.get("model_version")),
    )


def _build_llm_usage_summary(
    iterations: list[ReportIterationSummary],
) -> ReportLlmUsageSummary:
    prompt_total = 0
    completion_total = 0
    total_tokens = 0
    latency_total = 0.0
    usage_count = 0
    latency_count = 0
    most_expensive_iteration: int | None = None
    highest_latency_iteration: int | None = None
    max_tokens: int | None = None
    max_latency: float | None = None

    for iteration in iterations:
        usage = iteration.llm_usage
        if usage is None:
            continue

        has_usage = False
        if usage.prompt_tokens is not None:
            prompt_total += usage.prompt_tokens
            has_usage = True
        if usage.completion_tokens is not None:
            completion_total += usage.completion_tokens
            has_usage = True
        iteration_total_tokens = usage.total_tokens
        if iteration_total_tokens is None:
            token_parts = [usage.prompt_tokens, usage.completion_tokens]
            if any(part is not None for part in token_parts):
                iteration_total_tokens = sum(part or 0 for part in token_parts)
        if iteration_total_tokens is not None:
            total_tokens += iteration_total_tokens
            has_usage = True
            if max_tokens is None or iteration_total_tokens > max_tokens:
                max_tokens = iteration_total_tokens
                most_expensive_iteration = iteration.iteration
        if usage.api_latency_seconds is not None:
            latency_total += usage.api_latency_seconds
            latency_count += 1
            has_usage = True
            if max_latency is None or usage.api_latency_seconds > max_latency:
                max_latency = usage.api_latency_seconds
                highest_latency_iteration = iteration.iteration
        if has_usage:
            usage_count += 1

    if usage_count == 0:
        return ReportLlmUsageSummary()

    return ReportLlmUsageSummary(
        prompt_tokens_total=prompt_total,
        completion_tokens_total=completion_total,
        total_tokens=total_tokens,
        api_latency_seconds_total=latency_total if latency_count else None,
        api_latency_seconds_average=(latency_total / latency_count)
        if latency_count
        else None,
        iterations_with_usage=usage_count,
        most_expensive_iteration=most_expensive_iteration,
        highest_latency_iteration=highest_latency_iteration,
    )


def _build_diff_stats(value: Any) -> ReportDiffStats | None:
    if not isinstance(value, dict):
        return None
    return ReportDiffStats(
        files_changed=_int_or_default(value.get("files_changed")),
        lines_added=_int_or_default(value.get("lines_added")),
        lines_removed=_int_or_default(value.get("lines_removed")),
        changed_blocks=_int_or_default(value.get("changed_blocks")),
        edit_count=_int_or_none(value.get("edit_count")),
        fallback_used=_bool_or_none(value.get("fallback_used")),
    )


def _safe_read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _decision_object(
    record_decision: Any,
    artifact_decision: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if isinstance(record_decision, dict):
        return record_decision
    return artifact_decision


def _verification_payloads(verification: dict[str, Any]) -> list[dict[str, Any]]:
    payloads = [verification]
    for key in ("benchmark", "metrics"):
        value = verification.get(key)
        if isinstance(value, dict):
            payloads.insert(0, value)
    return payloads


def _verification_runtime(verification: dict[str, Any]) -> float | None:
    return _first_number(
        _verification_payloads(verification),
        (
            "runtime_ns_per_problem_median",
            "parsed_runtime_ns_per_problem_median",
        ),
    )


def _verification_correctness(verification: dict[str, Any]) -> bool | None:
    return _first_bool(
        _verification_payloads(verification),
        ("correctness_passed", "parsed_correctness_passed"),
    )


def _verification_gt_found(verification: dict[str, Any]) -> float | None:
    return _first_number(
        _verification_payloads(verification),
        ("gt_found_percent", "parsed_gt_found_percent"),
    )


def _verification_benchmark(verification: dict[str, Any]) -> dict[str, Any]:
    benchmark = verification.get("benchmark")
    return benchmark if isinstance(benchmark, dict) else {}


def _verification_benchmark_run_count(verification: dict[str, Any]) -> int | None:
    return _int_or_none(_verification_benchmark(verification).get("benchmark_run_count"))


def _verification_decision_metric(verification: dict[str, Any]) -> str | None:
    return _string_or_none(_verification_benchmark(verification).get("decision_metric"))


def _verification_aggregate_number(verification: dict[str, Any], key: str) -> float | None:
    aggregate = _verification_benchmark(verification).get("repeated_benchmark_aggregate")
    if not isinstance(aggregate, dict):
        return None
    return _number_or_none(aggregate.get(key))


def _decision_comparison_number(
    decision: dict[str, Any] | None,
    key: str,
) -> float | None:
    if not isinstance(decision, dict):
        return None
    comparison = decision.get("comparison")
    if not isinstance(comparison, dict):
        return None
    return _number_or_none(comparison.get(key))


def _decision_speedup(decision: dict[str, Any] | None) -> float | None:
    if not isinstance(decision, dict):
        return None
    comparison = decision.get("comparison")
    if isinstance(comparison, dict):
        speedup = _number_or_none(comparison.get("speedup"))
        if speedup is not None:
            return speedup
    return _number_or_none(decision.get("speedup"))


def _first_available_number(*values: Any) -> float | None:
    for value in values:
        number = _number_or_none(value)
        if number is not None:
            return number
    return None


def _first_available_bool(*values: Any) -> bool | None:
    for value in values:
        boolean = _bool_or_none(value)
        if boolean is not None:
            return boolean
    return None


def _first_available_int(*values: Any) -> int | None:
    for value in values:
        v = _int_or_none(value)
        if v is not None:
            return v
    return None


def _first_string(*values: Any) -> str | None:
    for value in values:
        text = _string_or_none(value)
        if text is not None:
            return text
    return None


def _first_summary_text(*values: Any) -> str | None:
    for value in values:
        text = _summary_text(value)
        if text is not None:
            return text
    return None


def _extract_reason(
    record: dict[str, Any],
    decision_vs_current_best: dict[str, Any] | None = None,
) -> str | None:
    failure_reason = _reason_text(record.get("failure_reason"))
    if failure_reason is not None:
        return failure_reason

    reason_sources = [
        (record.get("decision_vs_current_best"), "rejection_reasons"),
        (record.get("decision_vs_current_best"), "non_acceptance_reasons"),
        (decision_vs_current_best, "rejection_reasons"),
        (decision_vs_current_best, "non_acceptance_reasons"),
    ]
    for decision, reason_key in reason_sources:
        if not isinstance(decision, dict):
            continue
        reason = _reason_text(decision.get(reason_key))
        if reason is not None:
            return reason

    if record.get("status") == "valid_not_improved":
        return "runtime_not_improved"
    return None


def _reason_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, list):
        values = [str(item) for item in value if item is not None and str(item)]
        return "; ".join(values) if values else None
    return None


def _load_baseline_metrics_with_raw(
    raw_path: Any,
    experiment_dir: Path,
) -> tuple[ReportBaselineMetrics, dict[str, Any] | None]:
    """Load baseline metrics and return both the dataclass and raw dict."""

    path_text = _path_text_or_none(raw_path)
    if path_text is None:
        return ReportBaselineMetrics(), None

    metrics_path = _resolve_existing_or_display_path(path_text, experiment_dir)
    if not metrics_path.is_file():
        return ReportBaselineMetrics(), None

    try:
        payload = read_json(metrics_path)
    except (OSError, json.JSONDecodeError):
        return ReportBaselineMetrics(), None
    if not isinstance(payload, dict):
        return ReportBaselineMetrics(), None

    candidates = [payload]
    benchmark = payload.get("benchmark")
    if isinstance(benchmark, dict):
        candidates.insert(0, benchmark)

    metrics = ReportBaselineMetrics(
        runtime_ns_per_problem_median=_first_number(
            candidates,
            (
                "runtime_ns_per_problem_median",
                "parsed_runtime_ns_per_problem_median",
            ),
        ),
        gt_found_percent=_first_number(
            candidates,
            ("gt_found_percent", "parsed_gt_found_percent"),
        ),
        valid_solutions_percent=_first_number(
            candidates,
            ("valid_solutions_percent", "parsed_valid_solutions_percent"),
        ),
        total_solutions=_first_int(
            candidates,
            ("total_solutions", "parsed_total_solutions"),
        ),
        solutions_per_problem=_first_number(
            candidates,
            ("solutions_per_problem", "parsed_solutions_per_problem"),
        ),
        gt_found=_first_int(
            candidates,
            ("gt_found", "parsed_gt_found"),
        ),
        valid_solutions=_first_int(
            candidates,
            ("valid_solutions", "parsed_valid_solutions"),
        ),
        correctness_passed=_first_bool(
            candidates,
            ("correctness_passed", "parsed_correctness_passed"),
        ),
        benchmark_run_count=_first_int(candidates, ("benchmark_run_count",)),
        decision_metric=_first_string(*(candidate.get("decision_metric") for candidate in candidates if isinstance(candidate, dict))),
        min_runtime_ns_per_problem_median=_aggregate_first_number(
            candidates,
            "min_runtime_ns_per_problem_median",
        ),
        total_benchmark_wall_seconds=_aggregate_first_number(
            candidates,
            "total_benchmark_wall_seconds",
        ),
    )
    return metrics, payload


def _artifact_map(
    experiment_dir: Path,
    summary: dict[str, Any],
    *,
    report_data_path: Path,
) -> ReportArtifactMap:
    report_dir = experiment_dir / "report"
    report_pdf = report_dir / "report.pdf"

    def existing(name: str) -> str | None:
        path = experiment_dir / name
        return _display_path(path) if path.exists() else None

    return ReportArtifactMap(
        experiment_dir=_display_path(experiment_dir),
        report_dir=_display_path(report_dir),
        report_data=_display_path(report_data_path),
        report_html=_display_path(report_dir / "report.html"),
        report_pdf=_display_path(report_pdf) if report_pdf.exists() else None,
        plots_dir=_display_path(report_dir / "plots"),
        final_optimized_source=_display_path(
            _path_text_or_none(summary.get("final_optimized_source_dir")),
            experiment_dir,
        ),
        final_diff=_display_path(
            _path_text_or_none(summary.get("final_optimized_source_diff_path")),
            experiment_dir,
        ),
        closed_loop_summary=_display_path(
            experiment_dir / "closed_loop_summary.json"
        ),
        closed_loop_iterations=_display_path(
            experiment_dir / "closed_loop_iterations.jsonl"
        ),
        experiment_config_snapshot=existing("experiment_config_snapshot.json"),
        experiment_config_effective=existing("experiment_config_effective.json"),
        experiment_metadata=existing("experiment_metadata.json"),
        final_diff_stats=existing("final_diff_stats.json"),
        current_best_state=existing("current_best_state.json"),
        closed_loop_selection_report=existing("closed_loop_selection_report.json"),
        experiment_status=existing("experiment_status.json"),
        summary_txt=existing("summary.txt"),
        final_selection_dir=existing("final_selection"),
        final_selection_report=existing("final_selection_report.json"),
    )


def _resolve_existing_or_display_path(path_text: str, experiment_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path

    candidates = [experiment_dir / path]
    if len(experiment_dir.parents) >= 3:
        candidates.append(experiment_dir.parents[2] / path)
    candidates.extend([Path.cwd() / path, path])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def _resolve_existing_dir_or_display_path(path_text: str, experiment_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path

    candidates = [experiment_dir / path]
    if len(experiment_dir.parents) >= 3:
        candidates.append(experiment_dir.parents[2] / path)
    candidates.extend([Path.cwd() / path, path])
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[-1]


def _nested_get(d: dict[str, Any], *keys: str) -> Any:
    """Safely traverse nested dicts."""

    current: Any = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_number(
    payloads: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> float | None:
    for payload in payloads:
        for key in keys:
            value = _number_or_none(payload.get(key))
            if value is not None:
                return value
    return None


def _first_bool(
    payloads: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> bool | None:
    for payload in payloads:
        for key in keys:
            value = _bool_or_none(payload.get(key))
            if value is not None:
                return value
    return None


def _first_int(
    payloads: list[dict[str, Any]],
    keys: tuple[str, ...],
) -> int | None:
    for payload in payloads:
        for key in keys:
            value = _int_or_none(payload.get(key))
            if value is not None:
                return value
    return None


def _aggregate_first_number(
    payloads: list[dict[str, Any]],
    key: str,
) -> float | None:
    for payload in payloads:
        aggregate = payload.get("repeated_benchmark_aggregate")
        if not isinstance(aggregate, dict):
            continue
        value = _number_or_none(aggregate.get(key))
        if value is not None:
            return value
    return None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _bool_or_default(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _int_or_default(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    return None


def _string_or_default(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _path_text_or_none(value: Any) -> str | None:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def _summary_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _build_reason_summary(
    iterations: list[ReportIterationSummary],
) -> list[ReportReasonSummaryItem]:
    """Group non-accepted iterations by reason string."""

    _STATUS_REASON_MAP = {
        "no_op": "no_op",
        "generation_failed": "generation_failed",
        "materialization_failed": "materialization_failed",
        "verification_failed": "verification_failed",
        "valid_not_improved": "runtime_not_improved",
    }

    grouped: dict[str, list[int]] = {}
    order: list[str] = []

    for it in sorted(iterations, key=lambda x: x.iteration):
        if it.status == "accepted_improvement":
            continue
        reason: str | None = it.reason if it.reason else _STATUS_REASON_MAP.get(it.status)
        if reason is None:
            continue
        if reason not in grouped:
            grouped[reason] = []
            order.append(reason)
        grouped[reason].append(it.iteration)

    return [
        ReportReasonSummaryItem(reason=r, count=len(grouped[r]), iterations=grouped[r])
        for r in order
    ]


def _build_reason_code_counts(
    iterations: list[ReportIterationSummary],
) -> list[ReportReasonCodeCount]:
    grouped: dict[tuple[str, str], list[int]] = {}
    order: list[tuple[str, str]] = []
    for iteration in sorted(iterations, key=lambda item: item.iteration):
        reason = iteration.outcome_reason
        category = reason.category
        code = reason.code
        if not category or not code:
            continue
        key = (category, code)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(iteration.iteration)
    return [
        ReportReasonCodeCount(
            category=category,
            code=code,
            count=len(grouped[(category, code)]),
            iterations=grouped[(category, code)],
        )
        for category, code in order
    ]


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------


def _read_file_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _load_final_code_diff(summary: dict[str, Any], experiment_path: Path) -> str | None:
    path_text = _path_text_or_none(summary.get("final_optimized_source_diff_path"))
    if path_text is not None:
        diff_path = _resolve_existing_or_display_path(path_text, experiment_path)
        text = _read_file_text(diff_path)
        if text is not None:
            return text

    return _read_file_text(experiment_path / "final_optimized_source.diff")


def _get_sc(
    status_counts: Any,
    key: str,
) -> int:
    if isinstance(status_counts, dict):
        value = status_counts.get(key, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0
    return int(getattr(status_counts, key, 0))


def _build_executive_narrative(report_data: ReportData) -> str:
    sentences: list[str] = []
    exp = report_data.experiment
    sc = report_data.status_counts
    fr = report_data.final_result
    bm = report_data.baseline_metrics
    fbc = report_data.final_best_candidate
    usage = report_data.llm_usage_summary
    meta = report_data.experiment_metadata

    model_name = exp.model or report_data.llm.model
    target = exp.target_file

    parts: list[str] = []
    if model_name:
        parts.append(f"Using {model_name}")
    if target:
        parts.append(f"on {target}")
    parts.append(
        f"the experiment completed {exp.completed_iterations} of {exp.total_iterations} iterations."
    )
    sentences.append(" ".join(parts))

    accepted = _get_sc(sc, "accepted_improvement")
    no_op = _get_sc(sc, "no_op")
    valid_no_improve = _get_sc(sc, "valid_not_improved")
    rejected = _get_sc(sc, "rejected")
    mat_failed = _get_sc(sc, "materialization_failed")
    verif_failed = _get_sc(sc, "verification_failed")
    gen_failed = _get_sc(sc, "generation_failed")
    total_failed = mat_failed + verif_failed + gen_failed + rejected

    speedup = fr.final_speedup_vs_baseline
    reduction = fr.final_runtime_reduction_percent

    if accepted > 0 and speedup is not None and speedup > 1.0:
        baseline_rt = fbc.baseline_runtime_ns_per_problem_median or bm.runtime_ns_per_problem_median
        final_rt = fbc.runtime_ns_per_problem_median
        runtime_parts: list[str] = [
            "Runtime improved",
        ]
        if baseline_rt is not None and final_rt is not None:
            runtime_parts.append(
                f"from {baseline_rt:.0f} ns/problem to {final_rt:.0f} ns/problem"
            )
        metrics: list[str] = []
        if speedup is not None:
            metrics.append(f"speedup {speedup:.2f}x")
        if reduction is not None:
            metrics.append(f"{reduction:.1f}% reduction")
        if metrics:
            runtime_parts.append(f"({', '.join(metrics)})")
        runtime_parts.append(".")
        sentences.append(" ".join(runtime_parts))
    elif accepted == 0:
        sentences.append("No accepted runtime improvement was found.")

    # Candidate counts
    count_parts: list[str] = []
    if accepted:
        count_parts.append(f"{accepted} accepted")
    if valid_no_improve:
        count_parts.append(f"{valid_no_improve} valid but not improved")
    if no_op:
        count_parts.append(f"{no_op} no-op")
    if count_parts:
        sentences.append(f"{', '.join(count_parts)} candidates were produced.")

    # Correctness
    cp = fr.correctness_preserved
    baseline_gt = bm.gt_found_percent
    final_gt = fbc.gt_found_percent
    if cp is False:
        regress_parts: list[str] = ["Correctness regressed."]
        if baseline_gt is not None and final_gt is not None:
            delta = final_gt - baseline_gt
            regress_parts.append(
                f"GT Found dropped from {baseline_gt:.1f}% to {final_gt:.1f}% ({delta:+.1f} pp)."
            )
        sentences.append(" ".join(regress_parts))
    elif cp is True:
        sentences.append("Correctness was preserved.")

    # Pipeline health
    completed = exp.completed_iterations
    if completed > 0 and total_failed > 0 and total_failed > completed * 0.25:
        sentences.append(
            f"Pipeline failures ({total_failed} of {completed} iterations, "
            f"{total_failed / completed:.0%}) limited the session."
        )

    # Token usage and duration
    resource_parts: list[str] = []
    if usage.total_tokens is not None:
        resource_parts.append(f"{usage.total_tokens:,} tokens")
    if meta is not None and meta.total_duration_seconds is not None:
        duration_min = meta.total_duration_seconds / 60
        if duration_min >= 1:
            resource_parts.append(f"{duration_min:.1f} minutes")
        else:
            resource_parts.append(f"{meta.total_duration_seconds:.0f} seconds")
    if resource_parts:
        sentences.append(f"Total LLM usage: {', '.join(resource_parts)}.")

    return " ".join(sentences)


def _build_closed_loop_selection_explanation(report_data: ReportData) -> str | None:
    cs = report_data.closed_loop_selection
    if cs.best_verified_candidate_iteration is None:
        return None
    if cs.final_current_best_iteration is None:
        return None
    if cs.matches_final_current_best is not False:
        return None

    best_iter = cs.best_verified_candidate_iteration
    iter_reason = None
    for it in report_data.iterations:
        if it.iteration == best_iter:
            if it.reason and it.reason != "runtime_not_improved":
                iter_reason = it.reason
            if iter_reason is None and it.outcome_reason and it.outcome_reason.code:
                iter_reason = it.outcome_reason.code
            break

    if iter_reason:
        return (
            f"Iteration {best_iter} was faster on its repeated-median measurement, "
            f"but it was not promoted because the current-best promotion policy "
            f"did not accept it. Recorded reason: {iter_reason}."
        )
    return (
        f"Iteration {best_iter} was faster on its repeated-median measurement, "
        f"but it was not promoted because the current-best promotion policy "
        f"did not accept it."
    )


__all__ = [
    "collect_and_write_report_data",
    "collect_report_data",
]
