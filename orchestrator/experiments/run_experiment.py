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
from typing import Any

from . import experiment_artifacts as artifacts
from . import experiment_environment as env
from . import experiment_planner as planner
from . import iteration_runner
from .experiment_config import (
    ExperimentConfig,
    ExperimentConfigError,
    load_experiment_config,
)
from orchestrator.storage.experiment_registry import allocate_next_experiment_run


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


def _run_closed_loop_experiment(
    config: ExperimentConfig,
    experiment_id: str,
    experiment_dir: Any,
    llm_metadata_by_variant: dict[str, dict[str, Any]],
    started_at: datetime,
) -> dict[str, Any]:
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
    summary, results_state_path = artifacts.finalize_closed_loop_artifacts(
        paths=closed_loop_paths,
        experiment_id=experiment_id,
        config=config,
        state=state,
        records=records,
        started_at=started_at,
        finished_at=closed_loop_finished_at,
    )
    selection_report_path = artifacts.write_closed_loop_selection_report(experiment_dir, state, summary, records)
    final_selection_report_path = artifacts.run_final_selection_report(
        experiment_dir=experiment_dir,
        experiment_id=experiment_id,
        repo_root=env.REPO_ROOT,
        baseline_run_dir=state.original_baseline_run_dir,
        final_source_dir=closed_loop_paths.final_optimized_source_dir,
        final_best_run_dir=state.current_best_run_dir,
        target_file=config.target_file,
        final_best_is_baseline=state.current_best_is_baseline,
    )
    final_selection_status = artifacts._update_closed_loop_summary_with_final_selection(
        closed_loop_paths,
        summary,
        final_selection_report_path,
    )
    finished_at = env._now_iso()
    env._write_experiment_metadata(experiment_dir, started_at, finished_at)
    reporting_status = artifacts._run_final_reporting(experiment_dir, config)
    final_status = {
        "experiment_id": experiment_id,
        "experiment_name": config.experiment_name,
        "overall_status": artifacts._closed_loop_overall_status(
            final_selection_status=final_selection_status,
        ),
        "closed_loop": artifacts._closed_loop_status_block(
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
        artifacts._build_closed_loop_summary_text(
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
    artifacts.refresh_report_artifact_map(experiment_dir)
    return final_status


def _run_experiment(
    config: ExperimentConfig,
    config_snapshot: dict[str, Any],
) -> int:
    started_at = datetime.now().astimezone()
    try:
        allocation = allocate_next_experiment_run(env.EXPERIMENTS_ROOT)
    except OSError as exc:
        print(f"ERROR: Could not create experiment directory: {exc}", file=sys.stderr)
        return 1
    experiment_id = allocation.experiment_id
    experiment_dir = allocation.experiment_dir

    env._write_json(experiment_dir / "experiment_config_snapshot.json", config_snapshot)
    planner._write_effective_experiment_config(experiment_dir, config)
    env._write_experiment_metadata(experiment_dir, started_at)
    try:
        llm_metadata_by_variant = planner._write_resolved_variant_llm_configs(
            experiment_dir,
            config,
        )
    except (ExperimentConfigError, OSError) as exc:
        artifacts._write_early_failure_artifacts(
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
        artifacts._write_early_failure_artifacts(
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
    config_path = env._resolve_path(args.config)

    try:
        config = load_experiment_config(config_path)
        config_snapshot = env._read_json_file_object(config_path, "experiment config")
    except ExperimentConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        try:
            planner._print_plan(config, dry_run=True)
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
