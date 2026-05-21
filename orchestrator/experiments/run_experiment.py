"""Closed-loop experiment runner entry point.

This runner executes one closed-loop optimization experiment. It never promotes
candidates into the main ``cpp/`` source tree. Accepted candidates are promoted
only into the experiment-local ``current_best_source`` workspace.

Build type for candidate verification:
  The candidate verification stage defaults to Release builds (optimized) so
  that runtime metrics collected during verification reflect production
  performance. To override, set the CMAKE_BUILD_TYPE environment variable
  before launching the experiment runner.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from . import experiment_artifacts as artifacts
from . import experiment_environment as env
from . import experiment_planner as planner
from . import iteration_runner
from .closed_loop_state import ClosedLoopIterationRecord, ClosedLoopPaths, ClosedLoopSummary, CurrentBestState
from .experiment_config import (
    ExperimentConfig,
    ExperimentConfigError,
    load_experiment_config,
)
from orchestrator.storage.experiment_registry import allocate_next_experiment_run


REPO_ROOT = env.REPO_ROOT
RESULTS_ROOT = env.RESULTS_ROOT
EXPERIMENTS_ROOT = env.EXPERIMENTS_ROOT
WORKSPACE_ROOT = env.WORKSPACE_ROOT

# Patchable compatibility exports used by tests and external callers.
_resolve_variant_llm_config = planner._resolve_variant_llm_config
_run_stage = iteration_runner._run_stage
_build_generation_command = iteration_runner._build_generation_command
_build_materialization_command = iteration_runner._build_materialization_command
_build_verification_command = iteration_runner._build_verification_command
evaluate_candidate_against_reference = iteration_runner.evaluate_candidate_against_reference
run_final_selection_report = artifacts.run_final_selection_report
generate_basic_report = artifacts.generate_basic_report
refresh_report_artifact_map = artifacts.refresh_report_artifact_map


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or dry-run an experiment config."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to an experiment config JSON file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned experiment without running pipeline steps.",
    )
    return parser.parse_args(argv)


def _sync_compat_overrides() -> None:
    env.REPO_ROOT = REPO_ROOT
    env.RESULTS_ROOT = RESULTS_ROOT
    env.EXPERIMENTS_ROOT = EXPERIMENTS_ROOT
    env.WORKSPACE_ROOT = WORKSPACE_ROOT

    planner._resolve_variant_llm_config = _resolve_variant_llm_config

    iteration_runner._run_stage = _run_stage
    iteration_runner._build_generation_command = _build_generation_command
    iteration_runner._build_materialization_command = _build_materialization_command
    iteration_runner._build_verification_command = _build_verification_command
    iteration_runner.evaluate_candidate_against_reference = evaluate_candidate_against_reference

    artifacts.run_final_selection_report = run_final_selection_report
    artifacts.generate_basic_report = generate_basic_report
    artifacts.refresh_report_artifact_map = refresh_report_artifact_map


def _resolve_path(path_text: str) -> Path:
    _sync_compat_overrides()
    return env._resolve_path(path_text)


def _display_path(path: Path) -> str:
    _sync_compat_overrides()
    return env._display_path(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _sync_compat_overrides()
    env._write_json(path, payload)


def _read_json_object(path: Path) -> dict[str, Any]:
    _sync_compat_overrides()
    return env._read_json_object(path)


def _read_json_file_object(path: Path, label: str) -> dict[str, Any]:
    _sync_compat_overrides()
    return env._read_json_file_object(path, label)


def _experiment_repository_info() -> dict[str, Any]:
    _sync_compat_overrides()
    return env._experiment_repository_info()


def _experiment_environment_info() -> dict[str, Any]:
    _sync_compat_overrides()
    return env._experiment_environment_info()


def _write_experiment_metadata(
    experiment_dir: Path,
    started_at: datetime,
    finished_at: str | None = None,
) -> Path:
    _sync_compat_overrides()
    return env._write_experiment_metadata(experiment_dir, started_at, finished_at)


def _now_iso() -> str:
    _sync_compat_overrides()
    return env._now_iso()


def _portable_plain_dict(value: Any) -> Any:
    _sync_compat_overrides()
    return env._portable_plain_dict(value)


def _ensure_path_inside(path: Path, root: Path, label: str) -> None:
    _sync_compat_overrides()
    env._ensure_path_inside(path, root, label)


def initialize_current_best_source(paths: ClosedLoopPaths, config: ExperimentConfig) -> None:
    _sync_compat_overrides()
    env.initialize_current_best_source(paths, config)


def _initialize_current_best_state(
    paths: ClosedLoopPaths,
    experiment_id: str,
    config: ExperimentConfig,
    baseline_run_dir: Path,
) -> CurrentBestState:
    _sync_compat_overrides()
    return env._initialize_current_best_state(paths, experiment_id, config, baseline_run_dir)


def _write_current_best_state(paths: ClosedLoopPaths, state: CurrentBestState) -> None:
    _sync_compat_overrides()
    env._write_current_best_state(paths, state)


def update_current_best_source_from_workspace(
    paths: ClosedLoopPaths,
    workspace_path: Path,
    config: ExperimentConfig,
) -> None:
    _sync_compat_overrides()
    env.update_current_best_source_from_workspace(paths, workspace_path, config)


def _total_iterations(config: ExperimentConfig) -> int:
    return planner._total_iterations(config)


def _apply_llm_overrides(
    base_config: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    return planner._apply_llm_overrides(base_config, overrides)


def _llm_metadata(variant: Any, resolved_config: dict[str, Any], resolved_config_path: Path | None) -> dict[str, Any]:
    _sync_compat_overrides()
    return planner._llm_metadata(variant, resolved_config, resolved_config_path)


def _variant_llm_config_path(experiment_dir: Path, variant_id: str) -> Path:
    return planner._variant_llm_config_path(experiment_dir, variant_id)


def _write_resolved_variant_llm_configs(
    experiment_dir: Path,
    config: ExperimentConfig,
) -> dict[str, dict[str, Any]]:
    _sync_compat_overrides()
    return planner._write_resolved_variant_llm_configs(experiment_dir, config)


def _print_plan(config: ExperimentConfig, dry_run: bool) -> None:
    _sync_compat_overrides()
    planner._print_plan(config, dry_run)


def _write_effective_experiment_config(experiment_dir: Path, config: ExperimentConfig) -> Path:
    _sync_compat_overrides()
    return planner._write_effective_experiment_config(experiment_dir, config)


def _safe_artifact_name(value: str) -> str:
    return planner._safe_artifact_name(value)


def _parse_candidate_run_dir(stdout: str) -> str | None:
    _sync_compat_overrides()
    return iteration_runner._parse_candidate_run_dir(stdout)


def _looks_like_candidate_run_dir(value: str) -> bool:
    _sync_compat_overrides()
    return iteration_runner._looks_like_candidate_run_dir(value)


def is_noop_candidate(candidate: dict[str, Any]) -> bool:
    return iteration_runner.is_noop_candidate(candidate)


def _append_closed_loop_record_and_state(
    paths: ClosedLoopPaths,
    state: CurrentBestState,
    record: ClosedLoopIterationRecord,
) -> None:
    _sync_compat_overrides()
    iteration_runner._append_closed_loop_record_and_state(paths, state, record)


def _write_early_failure_artifacts(
    experiment_dir: Path,
    experiment_id: str,
    config: ExperimentConfig,
    started_at: datetime,
    failed_step: str,
    error_message: str,
) -> None:
    _sync_compat_overrides()
    artifacts._write_early_failure_artifacts(
        experiment_dir,
        experiment_id,
        config,
        started_at,
        failed_step,
        error_message,
    )


def copy_final_optimized_source(paths: ClosedLoopPaths, config: ExperimentConfig) -> Path:
    _sync_compat_overrides()
    return artifacts.copy_final_optimized_source(paths, config)


def write_final_optimized_source_diff(paths: ClosedLoopPaths, config: ExperimentConfig) -> Path:
    _sync_compat_overrides()
    return artifacts.write_final_optimized_source_diff(paths, config)


def write_final_diff_stats(paths: ClosedLoopPaths) -> dict[str, Any]:
    _sync_compat_overrides()
    return artifacts.write_final_diff_stats(paths)


def copy_results_current_best_state(paths: ClosedLoopPaths) -> Path:
    _sync_compat_overrides()
    return artifacts.copy_results_current_best_state(paths)


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
    _sync_compat_overrides()
    return artifacts.finalize_closed_loop_artifacts(
        paths=paths,
        experiment_id=experiment_id,
        config=config,
        state=state,
        records=records,
        started_at=started_at,
        finished_at=finished_at,
    )


def _update_closed_loop_summary_with_final_selection(
    paths: ClosedLoopPaths,
    summary: ClosedLoopSummary,
    report_path: Path,
) -> dict[str, Any]:
    _sync_compat_overrides()
    return artifacts._update_closed_loop_summary_with_final_selection(paths, summary, report_path)


def _closed_loop_overall_status(
    *,
    final_selection_status: dict[str, Any] | None = None,
) -> str:
    return artifacts._closed_loop_overall_status(final_selection_status=final_selection_status)


def write_closed_loop_selection_report(
    experiment_dir: Path,
    state: CurrentBestState,
    summary: ClosedLoopSummary,
    records: list[ClosedLoopIterationRecord] | None = None,
) -> Path:
    _sync_compat_overrides()
    return artifacts.write_closed_loop_selection_report(experiment_dir, state, summary, records)


def _closed_loop_status_block(
    paths: ClosedLoopPaths,
    summary: ClosedLoopSummary,
    results_state_path: Path,
    accepted_improvements: int,
    final_selection_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _sync_compat_overrides()
    return artifacts._closed_loop_status_block(
        paths,
        summary,
        results_state_path,
        accepted_improvements,
        final_selection_status,
    )


def _run_final_reporting(experiment_dir: Path, config: ExperimentConfig) -> dict[str, Any]:
    _sync_compat_overrides()
    return artifacts._run_final_reporting(experiment_dir, config)


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
    _sync_compat_overrides()
    return artifacts._build_closed_loop_summary_text(
        experiment_id=experiment_id,
        config=config,
        summary=summary,
        results_state_path=results_state_path,
        accepted_improvements=accepted_improvements,
        reporting_status=reporting_status,
        final_selection_status=final_selection_status,
        finished_at=finished_at,
    )


def _run_closed_loop_experiment(
    config: ExperimentConfig,
    experiment_id: str,
    experiment_dir: Path,
    llm_metadata_by_variant: dict[str, dict[str, Any]],
    started_at: datetime,
) -> dict[str, Any]:
    _sync_compat_overrides()
    variant = config.variants[0]
    baseline_run_dir = env._resolve_path(config.baseline_run_dir)
    baseline_metrics_path = baseline_run_dir / "metrics.json"
    if not baseline_metrics_path.exists():
        raise ExperimentConfigError(f"Closed-loop baseline metrics not found: {baseline_metrics_path}")

    closed_loop_paths, state, records, closed_loop_finished_at = iteration_runner.run_closed_loop_iterations(
        config,
        experiment_id,
        experiment_dir,
        llm_metadata_by_variant,
    )
    summary, results_state_path = finalize_closed_loop_artifacts(
        paths=closed_loop_paths,
        experiment_id=experiment_id,
        config=config,
        state=state,
        records=records,
        started_at=started_at,
        finished_at=closed_loop_finished_at,
    )
    selection_report_path = write_closed_loop_selection_report(experiment_dir, state, summary, records)
    final_selection_report_path = run_final_selection_report(
        experiment_dir=experiment_dir,
        experiment_id=experiment_id,
        repo_root=env.REPO_ROOT,
        baseline_run_dir=state.original_baseline_run_dir,
        final_source_dir=closed_loop_paths.final_optimized_source_dir,
        final_best_run_dir=state.current_best_run_dir,
        target_file=config.target_file,
        final_best_is_baseline=state.current_best_is_baseline,
    )
    final_selection_status = _update_closed_loop_summary_with_final_selection(
        closed_loop_paths,
        summary,
        final_selection_report_path,
    )
    finished_at = env._now_iso()
    _write_experiment_metadata(experiment_dir, started_at, finished_at)
    reporting_status = _run_final_reporting(experiment_dir, config)
    final_status = {
        "experiment_id": experiment_id,
        "experiment_name": config.experiment_name,
        "overall_status": _closed_loop_overall_status(
            final_selection_status=final_selection_status,
        ),
        "closed_loop": _closed_loop_status_block(
            closed_loop_paths,
            summary,
            results_state_path,
            state.accepted_improvements,
            final_selection_status,
        ),
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at,
        "planned_iterations": variant.iterations,
        "completed_iterations": len(records),
        "target_file": config.target_file,
        "baseline_run_dir": config.baseline_run_dir,
        "closed_loop_selection_report_path": env._display_path(selection_report_path),
        "final_selection_report_path": env._display_path(final_selection_report_path),
        "reporting": reporting_status,
    }
    env._write_json(experiment_dir / "experiment_status.json", final_status)
    (experiment_dir / "summary.txt").write_text(
        _build_closed_loop_summary_text(
            experiment_id=experiment_id,
            config=config,
            summary=summary,
            results_state_path=results_state_path,
            accepted_improvements=state.accepted_improvements,
            reporting_status=reporting_status,
            final_selection_status=final_selection_status,
            finished_at=finished_at,
        ),
        encoding="utf-8",
    )
    refresh_report_artifact_map(experiment_dir)
    return final_status


def _run_experiment(
    config: ExperimentConfig,
    config_snapshot: dict[str, Any],
) -> int:
    _sync_compat_overrides()
    started_at = datetime.now().astimezone()
    try:
        allocation = allocate_next_experiment_run(EXPERIMENTS_ROOT)
    except OSError as exc:
        print(f"ERROR: Could not create experiment directory: {exc}", file=sys.stderr)
        return 1
    experiment_id = allocation.experiment_id
    experiment_dir = allocation.experiment_dir

    env._write_json(experiment_dir / "experiment_config_snapshot.json", config_snapshot)
    _write_effective_experiment_config(experiment_dir, config)
    _write_experiment_metadata(experiment_dir, started_at)
    try:
        llm_metadata_by_variant = _write_resolved_variant_llm_configs(
            experiment_dir,
            config,
        )
    except (ExperimentConfigError, OSError) as exc:
        _write_early_failure_artifacts(
            experiment_dir,
            experiment_id,
            config,
            started_at,
            "prepare_variant_llm_configs",
            str(exc),
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Artifacts saved to: {env._display_path(experiment_dir)}")
        return 1

    print("Experiment execution")
    print(f"Experiment: {config.experiment_name}")
    print(f"Experiment id: {experiment_id}")
    print(f"Experiment directory: {env._display_path(experiment_dir)}")
    print("Mode: closed-loop optimization")
    print(f"Variant: {config.variants[0].variant_id}")
    print(f"Baseline run dir: {config.baseline_run_dir}")
    print(f"Planned iterations: {planner._total_iterations(config)}")

    try:
        status = _run_closed_loop_experiment(
            config,
            experiment_id,
            experiment_dir,
            llm_metadata_by_variant,
            started_at,
        )
    except (ExperimentConfigError, OSError, ValueError) as exc:
        _write_early_failure_artifacts(
            experiment_dir,
            experiment_id,
            config,
            started_at,
            "closed_loop_initialization_or_execution",
            str(exc),
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Artifacts saved to: {env._display_path(experiment_dir)}")
        return 1

    print("")
    print(f"Final experiment status: {status['overall_status']}")
    print(f"Completed iterations: {status['completed_iterations']}")
    print(f"Artifacts saved to: {env._display_path(experiment_dir)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config_path = _resolve_path(args.config)

    try:
        config = load_experiment_config(config_path)
        config_snapshot = _read_json_file_object(config_path, "experiment config")
    except ExperimentConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        try:
            _print_plan(config, dry_run=True)
        except ExperimentConfigError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        return 0

    return _run_experiment(config, config_snapshot)


def __getattr__(name: str) -> Any:
    for module in (env, planner, iteration_runner, artifacts):
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    raise SystemExit(main())
