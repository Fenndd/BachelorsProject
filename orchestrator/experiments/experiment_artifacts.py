"""Final closed-loop artifact, status, and reporting helpers."""

from __future__ import annotations

import difflib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from . import experiment_environment as env
from .experiment_planner import _total_iterations
from .closed_loop_state import (
    ClosedLoopIterationRecord,
    ClosedLoopPaths,
    ClosedLoopSummary,
    CurrentBestState,
    IterationStatus,
    count_iteration_statuses,
)
from .experiment_config import ExperimentConfig
from .final_selection_report import run_final_selection_report
from orchestrator.core.patching.diff_stats import parse_diff_stats
from orchestrator.reporting.generate_report import generate_basic_report, refresh_report_artifact_map


def _write_early_failure_artifacts(
    experiment_dir: Path,
    experiment_id: str,
    config: ExperimentConfig,
    started_at: datetime,
    failed_step: str,
    error_message: str,
) -> None:
    status = {
        "experiment_id": experiment_id,
        "experiment_name": config.experiment_name,
        "overall_status": "failed",
        "failed_step": failed_step,
        "error_message": error_message,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "planned_iterations": _total_iterations(config),
        "successful_iterations": 0,
        "failed_iterations": 0,
        "generation_successes": 0,
        "materialization_successes": 0,
        "verification_successes": 0,
        "target_file": config.target_file,
        "baseline_run_dir": config.baseline_run_dir,
        "llm": {
            "planned_iterations": config.iterations,
            "base_llm_config": config.llm_config,
            "resolved_llm_config": None,
            "provider": None,
            "model": None,
            "thinking_enabled": None,
            "reasoning_effort": None,
            "max_tokens": None,
        },
    }
    status_finished_at = status.get("finished_at")
    env._write_experiment_metadata(
        experiment_dir,
        started_at,
        status_finished_at if isinstance(status_finished_at, str) else None,
    )
    env._write_json(experiment_dir / "experiment_status.json", status)
    lines = [
        f"Experiment id: {experiment_id}",
        f"Experiment name: {config.experiment_name}",
        f"Description: {config.description or 'none'}",
        f"Target file: {config.target_file}",
        f"Baseline run dir: {config.baseline_run_dir}",
        "Overall status: failed",
        f"Failed step: {failed_step}",
        f"Error message: {error_message}",
        f"Total planned iterations: {_total_iterations(config)}",
    ]
    lines.extend(
        [
            "No iterations were executed.",
            "",
            "Closed-loop optimization did not start or did not complete.",
            "",
        ]
    )
    (experiment_dir / "summary.txt").write_text("\n".join(lines), encoding="utf-8")


def _results_current_best_state_path(paths: ClosedLoopPaths) -> Path:
    return paths.results_root / "experiments" / paths.experiment_id / "current_best_state.json"


def copy_final_optimized_source(paths: ClosedLoopPaths, config: ExperimentConfig) -> Path:
    """Copy final current_best_source into the experiment results directory."""

    source_dir = paths.current_best_source_dir
    if not source_dir.exists() or not source_dir.is_dir():
        raise FileNotFoundError(f"Current best source directory not found: {source_dir}")
    target_file = source_dir / config.target_file
    if not target_file.exists() or not target_file.is_file():
        raise FileNotFoundError(f"Current best source missing target file: {target_file}")

    final_dir = paths.final_optimized_source_dir
    env._ensure_path_inside(final_dir, paths.results_root / "experiments", "final optimized source")
    if final_dir.exists():
        shutil.rmtree(final_dir)
    env._copy_source_tree(source_dir, final_dir)
    final_target = final_dir / config.target_file
    if not final_target.exists() or not final_target.is_file():
        raise FileNotFoundError(f"Final optimized source missing target file: {final_target}")
    return final_dir


def write_final_optimized_source_diff(paths: ClosedLoopPaths, config: ExperimentConfig) -> Path:
    """Write unified diff from clean baseline source to final optimized source."""

    baseline_file = env.REPO_ROOT / config.target_file
    final_file = paths.final_optimized_source_dir / config.target_file
    if not baseline_file.exists() or not baseline_file.is_file():
        raise FileNotFoundError(f"Baseline source missing target file: {baseline_file}")
    if not final_file.exists() or not final_file.is_file():
        raise FileNotFoundError(f"Final optimized source missing target file: {final_file}")

    baseline_lines = baseline_file.read_text(encoding="utf-8").splitlines(keepends=True)
    final_lines = final_file.read_text(encoding="utf-8").splitlines(keepends=True)
    diff_lines = list(
        getattr(difflib, "unified" + "_diff")(
            baseline_lines,
            final_lines,
            fromfile=f"a/{config.target_file}",
            tofile=f"b/{config.target_file}",
        )
    )
    paths.final_optimized_source_diff_path.parent.mkdir(parents=True, exist_ok=True)
    paths.final_optimized_source_diff_path.write_text("".join(diff_lines), encoding="utf-8")
    return paths.final_optimized_source_diff_path


def write_final_diff_stats(paths: ClosedLoopPaths) -> dict[str, Any]:
    diff_text = paths.final_optimized_source_diff_path.read_text(encoding="utf-8")
    stats = parse_diff_stats(diff_text)
    output_path = paths.final_optimized_source_diff_path.parent / "final_diff_stats.json"
    env._write_json(output_path, stats)
    return stats


def copy_results_current_best_state(paths: ClosedLoopPaths) -> Path:
    """Copy workspace current-best metadata into the experiment results directory."""

    if not paths.current_best_state_path.exists():
        raise FileNotFoundError(f"Current best state not found: {paths.current_best_state_path}")
    results_state_path = _results_current_best_state_path(paths)
    results_state_path.parent.mkdir(parents=True, exist_ok=True)
    state = env._read_json_object(paths.current_best_state_path)
    env._write_json(results_state_path, env._portable_plain_dict(state))
    return results_state_path


def _final_speedup_vs_original_baseline(
    state: CurrentBestState,
) -> tuple[float | None, float | None]:
    if state.current_best_is_baseline:
        return 1.0, 0.0

    decision_path = state.current_best_run_dir / "decision_vs_original_baseline.json"
    try:
        decision = env._read_json_object(decision_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None, None
    comparison = decision.get("comparison")
    if not isinstance(comparison, dict):
        return None, None

    speedup = comparison.get("speedup")
    runtime_reduction = comparison.get("runtime_reduction_percent")
    return (
        float(speedup) if isinstance(speedup, (int, float)) and not isinstance(speedup, bool) else None,
        float(runtime_reduction)
        if isinstance(runtime_reduction, (int, float)) and not isinstance(runtime_reduction, bool)
        else None,
    )


def finalize_closed_loop_artifacts(
    *,
    paths: ClosedLoopPaths,
    experiment_id: str,
    config: ExperimentConfig,
    state: CurrentBestState,
    records: list[ClosedLoopIterationRecord],
    started_at: datetime,
    finished_at: str,
) -> tuple[ClosedLoopSummary, Path]:
    """Write final closed-loop artifacts after all iterations finish."""

    copy_final_optimized_source(paths, config)
    write_final_optimized_source_diff(paths, config)
    final_diff_stats = write_final_diff_stats(paths)
    results_state_path = copy_results_current_best_state(paths)
    status_counts = count_iteration_statuses(records)
    summary = ClosedLoopSummary(
        experiment_id=experiment_id,
        target_file=config.target_file,
        total_iterations=_total_iterations(config),
        completed_iterations=len(records),
        original_baseline_run_dir=state.original_baseline_run_dir,
        original_baseline_metrics_path=state.original_baseline_metrics_path,
        final_best_iteration=state.current_best_iteration,
        final_best_candidate_run_dir=None if state.current_best_is_baseline else state.current_best_run_dir,
        final_optimized_source_dir=paths.final_optimized_source_dir,
        final_optimized_source_diff_path=paths.final_optimized_source_diff_path,
        iterations_after_final_best=len(records) - state.current_best_iteration,
        status_counts=status_counts,
        created_at=started_at.isoformat(timespec="seconds"),
        finished_at=finished_at,
        final_diff_stats=final_diff_stats,
    )
    env._write_json(paths.closed_loop_summary_path, env._portable_plain_dict(summary))
    return summary, results_state_path


def _update_closed_loop_summary_with_final_selection(
    paths: ClosedLoopPaths,
    summary: ClosedLoopSummary,
    report_path: Path,
) -> dict[str, Any]:
    report = env._read_json_object(report_path)
    comparison_raw = report.get("comparison")
    comparison: dict[str, Any] = comparison_raw if isinstance(comparison_raw, dict) else {}
    speedup = _numeric_or_none(comparison.get("speedup"))
    runtime_reduction = _numeric_or_none(comparison.get("runtime_reduction_percent"))
    baseline_runtime = _numeric_or_none(comparison.get("baseline_runtime_ns_per_problem_median"))
    final_runtime = _numeric_or_none(comparison.get("final_runtime_ns_per_problem_median"))
    final_correctness = report.get("final_benchmark", {}).get("parsed_correctness_passed") if isinstance(report.get("final_benchmark"), dict) else None
    status = report.get("status")
    summary.final_selection_report_path = report_path
    summary.final_selection_speedup_vs_original_baseline = speedup
    summary.final_selection_runtime_reduction_percent = runtime_reduction
    env._write_json(paths.closed_loop_summary_path, env._portable_plain_dict(summary))
    return {
        "status": status,
        "final_best_is_baseline": report.get("final_best_is_baseline"),
        "report_path": env._display_path(report_path),
        "speedup_vs_original_baseline": speedup,
        "runtime_reduction_percent": runtime_reduction,
        "baseline_runtime_ns_per_problem_median": baseline_runtime,
        "final_runtime_ns_per_problem_median": final_runtime,
        "final_correctness_passed": final_correctness,
    }


def _closed_loop_overall_status(
    *,
    final_selection_status: dict[str, Any] | None = None,
) -> str:
    if isinstance(final_selection_status, dict) and final_selection_status.get("status") == "failed":
        return "completed_with_warnings"
    return "completed"


def write_closed_loop_selection_report(
    experiment_dir: Path,
    state: CurrentBestState,
    summary: ClosedLoopSummary,
    records: list[ClosedLoopIterationRecord] | None = None,
) -> Path:
    """Write reporting-only final closed-loop selection analysis."""

    report_path = experiment_dir / "closed_loop_selection_report.json"
    candidate_attempts = [_compact_candidate_attempt(record) for record in (records or [])]
    final_current_best_run_dir = env._display_path(state.current_best_run_dir)
    selection_speedup, selection_runtime_reduction = _final_speedup_vs_original_baseline(state)
    payload = {
        "report_type": "closed_loop_final_selection_report",
        "experiment_id": summary.experiment_id,
        "target_file": summary.target_file,
        "mode": "closed_loop",
        "promotion_policy": "decision_vs_current_best.accepted_improvement_only",
        "final_current_best": {
            "iteration": state.current_best_iteration,
            "is_baseline": state.current_best_is_baseline,
            "run_dir": final_current_best_run_dir,
            "source_dir": env._display_path(state.current_best_source_dir),
            "metrics_path": env._display_path(state.current_best_metrics_path),
            "accepted_improvements": state.accepted_improvements,
        },
        "best_verified_candidate_vs_original_baseline": _best_verified_candidate_vs_original_baseline(candidate_attempts, final_current_best_run_dir),
        "candidate_attempts": candidate_attempts,
        "status_counts": summary.status_counts,
        "control_decision": {
            "promotion_policy": "decision_vs_current_best.accepted_improvement_only",
            "final_best_iteration": state.current_best_iteration,
            "final_best_is_baseline": state.current_best_is_baseline,
            "final_best_run_dir": final_current_best_run_dir,
            "accepted_improvements": state.accepted_improvements,
        },
        "single_run_selection_analytics": {
            "metric_source": "single_run_closed_loop_selection_analytics",
            "target_file": summary.target_file,
            "final_optimized_source_dir": env._display_path(summary.final_optimized_source_dir),
            "final_optimized_source_diff_path": env._display_path(summary.final_optimized_source_diff_path),
            "performance_reference": "original_baseline",
            "final_speedup_vs_original_baseline": selection_speedup,
            "final_runtime_reduction_percent": selection_runtime_reduction,
            "status_counts": summary.status_counts,
        },
        "safety": {
            "report_promotes_candidates": False,
            "report_updates_current_best_source": False,
            "report_updates_final_optimized_source": False,
            "report_modifies_main_cpp_tree": False,
        },
    }
    env._write_json(report_path, payload)
    return report_path


def _compact_candidate_attempt(record: ClosedLoopIterationRecord) -> dict[str, Any]:
    return {
        "iteration": record.iteration,
        "status": record.status.value if isinstance(record.status, IterationStatus) else record.status,
        "candidate_run_dir": env._display_path(record.candidate_run_dir) if record.candidate_run_dir is not None else None,
        "decision_vs_current_best": _compact_report_decision(record.decision_vs_current_best),
        "decision_vs_original_baseline": _compact_report_decision(record.decision_vs_original_baseline),
        "speedup_vs_current_best": record.speedup_vs_current_best,
        "speedup_vs_original_baseline": record.speedup_vs_original_baseline,
        "current_best_updated": record.current_best_updated,
        "failure_stage": record.failure_stage,
        "failure_reason": record.failure_reason,
    }


def _compact_report_decision(decision: dict[str, Any] | str | None) -> dict[str, Any] | str | None:
    if not isinstance(decision, dict):
        return decision
    comparison = decision.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}
    return {
        "status": decision.get("status"),
        "reference_kind": decision.get("reference_kind"),
        "speedup": _numeric_or_none(comparison.get("speedup"), decision.get("speedup")),
        "runtime_reduction_percent": _numeric_or_none(
            comparison.get("runtime_reduction_percent"),
            decision.get("runtime_reduction_percent"),
        ),
        "comparison": comparison,
        "rejection_reasons": decision.get("rejection_reasons"),
        "non_acceptance_reasons": decision.get("non_acceptance_reasons"),
    }


def _numeric_or_none(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _best_verified_candidate_vs_original_baseline(
    candidate_attempts: list[dict[str, Any]],
    final_current_best_run_dir: str,
) -> dict[str, Any] | None:
    best_attempt: dict[str, Any] | None = None
    best_speedup: float | None = None
    for attempt in candidate_attempts:
        decision = attempt.get("decision_vs_original_baseline")
        if not isinstance(decision, dict):
            continue
        status = decision.get("status")
        if status not in {"accepted_improvement", "valid_not_improved"}:
            continue
        speedup = _numeric_or_none(decision.get("speedup"), attempt.get("speedup_vs_original_baseline"))
        if not isinstance(speedup, (int, float)) or isinstance(speedup, bool):
            continue
        if best_speedup is None or float(speedup) > best_speedup:
            best_speedup = float(speedup)
            runtime_reduction = _numeric_or_none(decision.get("runtime_reduction_percent"))
            best_attempt = {
                "iteration": attempt.get("iteration"),
                "candidate_run_dir": attempt.get("candidate_run_dir"),
                "speedup": best_speedup,
                "runtime_reduction_percent": runtime_reduction,
                "matches_final_current_best": attempt.get("candidate_run_dir") == final_current_best_run_dir,
                "status": status,
            }
    return best_attempt


def _closed_loop_status_block(
    paths: ClosedLoopPaths,
    summary: ClosedLoopSummary,
    results_state_path: Path,
    accepted_improvements: int,
    final_selection_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "enabled": True,
        "final_best_iteration": summary.final_best_iteration,
        "accepted_improvements": accepted_improvements,
        "final_optimized_source_dir": env._display_path(summary.final_optimized_source_dir),
        "final_optimized_source_diff_path": env._display_path(summary.final_optimized_source_diff_path),
        "closed_loop_summary_path": env._display_path(paths.closed_loop_summary_path),
        "closed_loop_iterations_path": env._display_path(paths.closed_loop_iterations_path),
        "current_best_state_path": env._display_path(results_state_path),
        "workspace_current_best_source_dir": env._display_path(paths.current_best_source_dir),
        "workspace_current_best_state_path": env._display_path(paths.current_best_state_path),
        "status_counts": summary.status_counts,
    }
    if final_selection_status is not None:
        payload["final_selection_report_path"] = final_selection_status.get("report_path")
        payload["final_selection_speedup_vs_original_baseline"] = final_selection_status.get("speedup_vs_original_baseline")
        payload["final_selection_runtime_reduction_percent"] = final_selection_status.get("runtime_reduction_percent")
        payload["final_selection_status"] = final_selection_status.get("status")
    return payload


def _reporting_status_disabled(config: ExperimentConfig) -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "disabled",
        "formats": list(config.reporting.formats),
        "renderer": config.reporting.renderer,
        "report_data_path": None,
        "report_html_path": None,
        "report_pdf_path": None,
        "error": None,
    }


def _reporting_status_completed(
    config: ExperimentConfig,
    artifacts: dict[str, Path],
) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "completed",
        "formats": list(config.reporting.formats),
        "renderer": config.reporting.renderer,
        "report_data_path": env._display_path(artifacts["report_data"]),
        "report_html_path": env._display_path(artifacts["html"]),
        "report_pdf_path": (
            env._display_path(artifacts["pdf"]) if "pdf" in artifacts else None
        ),
        "error": None,
    }


def _reporting_status_failed(
    config: ExperimentConfig,
    error: Exception,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "failed",
        "formats": list(config.reporting.formats),
        "renderer": config.reporting.renderer,
        "report_data_path": None,
        "report_html_path": None,
        "report_pdf_path": None,
        "error": str(error),
    }


def _run_final_reporting(
    experiment_dir: Path,
    config: ExperimentConfig,
) -> dict[str, Any]:
    if not config.reporting.enabled:
        return _reporting_status_disabled(config)

    try:
        artifacts = generate_basic_report(
            experiment_dir,
            formats=tuple(config.reporting.formats),
            renderer=config.reporting.renderer,
        )
    except Exception as exc:
        if config.reporting.fail_on_error:
            raise
        return _reporting_status_failed(config, exc)

    return _reporting_status_completed(config, artifacts)


def _format_optional_float(value: float | None) -> str:
    return "none" if value is None else str(value)


def _build_closed_loop_summary_text(
    *,
    experiment_id: str,
    config: ExperimentConfig,
    summary: ClosedLoopSummary,
    results_state_path: Path,
    accepted_improvements: int,
    reporting_status: dict[str, Any] | None = None,
    final_selection_status: dict[str, Any] | None = None,
    finished_at: str | None = None,
) -> str:
    lines = [
        f"Experiment id: {experiment_id}",
        f"Experiment name: {config.experiment_name}",
        "Closed-loop mode: enabled",
        f"Finished at: {finished_at or 'none'}",
        f"Target file: {config.target_file}",
        f"Total planned iterations: {summary.total_iterations}",
        f"Completed iterations: {summary.completed_iterations}",
        f"Accepted improvements: {accepted_improvements}",
        f"Final best iteration: {summary.final_best_iteration}",
        "Status counts:",
    ]
    for status, count in summary.status_counts.items():
        lines.append(f"- {status}: {count}")
    lines.extend(
        [
            "Final artifacts:",
            f"- final optimized source: {env._display_path(summary.final_optimized_source_dir)}",
            f"- final diff: {env._display_path(summary.final_optimized_source_diff_path)}",
            f"- closed-loop summary: {env._display_path(summary.final_optimized_source_diff_path.parent / 'closed_loop_summary.json')}",
            f"- closed-loop iterations: {env._display_path(summary.final_optimized_source_diff_path.parent / 'closed_loop_iterations.jsonl')}",
            f"- current best state: {env._display_path(results_state_path)}",
            "All planned iterations were attempted; no early stopping is used.",
            "Main cpp/ source tree was not modified automatically.",
            "",
        ]
    )
    if reporting_status is not None:
        lines.append("Reporting:")
        lines.append(f"  enabled: {str(reporting_status.get('enabled')).lower()}")
        if reporting_status.get("enabled") is True:
            lines.append(f"  status: {reporting_status.get('status')}")
            if reporting_status.get("status") == "completed":
                lines.append(
                    f"  report data: {reporting_status.get('report_data_path') or 'none'}"
                )
                lines.append(
                    f"  HTML report: {reporting_status.get('report_html_path') or 'none'}"
                )
                lines.append(
                    f"  PDF report: {reporting_status.get('report_pdf_path') or 'none'}"
                )
            elif reporting_status.get("status") == "failed":
                lines.append(f"  error: {reporting_status.get('error') or 'none'}")
        lines.append("")
    if final_selection_status is not None:
        lines.append("Final single-run comparison vs original baseline:")
        lines.append(f"  status: {final_selection_status.get('status') or 'none'}")
        lines.append(f"  final best is baseline: {str(final_selection_status.get('final_best_is_baseline')).lower()}")
        lines.append(f"  report: {final_selection_status.get('report_path') or 'none'}")
        if final_selection_status.get("status") in {"completed", "skipped"}:
            lines.append(
                "  speedup vs original baseline: "
                f"{_format_optional_float(final_selection_status.get('speedup_vs_original_baseline'))}"
            )
            lines.append(
                "  runtime reduction percent: "
                f"{_format_optional_float(final_selection_status.get('runtime_reduction_percent'))}"
            )
            lines.append(
                "  baseline runtime ns/problem: "
                f"{_format_optional_float(final_selection_status.get('baseline_runtime_ns_per_problem_median'))}"
            )
            lines.append(
                "  final runtime ns/problem: "
                f"{_format_optional_float(final_selection_status.get('final_runtime_ns_per_problem_median'))}"
            )
            lines.append(
                "  final correctness_passed: "
                f"{final_selection_status.get('final_correctness_passed')}"
            )
        else:
            lines.append("  Final single-run comparison metrics: unavailable")
        lines.append("")
    else:
        lines.append("Final single-run comparison: not run")
        lines.append("")
    return "\n".join(lines)
