"""Closed-loop per-iteration execution helpers."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from . import experiment_environment as env
from .closed_loop_history import (
    build_closed_loop_history_context,
    build_history_guidance,
    should_include_in_closed_loop_history,
)
from .closed_loop_state import (
    ClosedLoopIterationRecord,
    ClosedLoopPaths,
    CurrentBestState,
    IterationStatus,
    to_plain_dict,
)
from .experiment_config import ExperimentConfig
from .outcome_reason import build_outcome_reason, outcome_reason_to_dict
from orchestrator.core.benchmarking.candidate_decision import (
    evaluate_candidate_against_reference,
    write_candidate_decision,
)
from orchestrator.shared.process.step_runner import StepRunner, format_command


_STEP_RUNNER = StepRunner()


def format_iteration_dir(iteration: int) -> str:
    """Return a short iteration directory name like 'it_01', 'it_99', 'it_100'."""
    return f"it_{iteration:02d}"


def _build_generation_command(
    config: ExperimentConfig,
    llm_config_path: str,
    context_text: str | None,
    source_root: str | None = None,
    candidate_run_dir: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "orchestrator.core.llm.generate_candidate",
        "--config",
        llm_config_path,
        "--source",
        config.target_file,
        "--max-source-chars",
        str(config.candidate_generation.max_source_chars),
    ]
    if source_root is not None:
        command.extend(["--source-root", source_root])
    if candidate_run_dir is not None:
        command.extend(["--candidate-run-dir", candidate_run_dir])
    if context_text is not None:
        command.extend(["--context", context_text])
    for allowed_file in config.optimization_scope.allowed_files:
        command.extend(["--allowed-file", allowed_file])
    return command


def _build_materialization_command(
    candidate_run_dir: str,
    config: ExperimentConfig,
    base_source_root: str | None = None,
    candidate_workspace_dir: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "orchestrator.core.patching.materialize_candidate",
        "--candidate-run",
        candidate_run_dir,
        "--overwrite",
    ]
    if base_source_root is not None:
        command.extend(["--base-source-root", base_source_root])
    if candidate_workspace_dir is not None:
        command.extend(["--candidate-workspace-dir", candidate_workspace_dir])
    for allowed_file in config.optimization_scope.allowed_files:
        command.extend(["--allowed-file", allowed_file])
    return command


def _build_verification_command(candidate_run_dir: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "orchestrator.core.execution.verify_candidate",
        "--candidate-run",
        candidate_run_dir,
    ]


def _write_stage_log(
    log_path: Path,
    global_iteration: int,
    variant_id: str,
    variant_iteration: int,
    stage_name: str,
    command: Sequence[str],
    cwd: Path,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    duration_seconds: float,
) -> None:
    lines = [
        f"GLOBAL_ITERATION: {global_iteration}",
        f"VARIANT_ID: {variant_id}",
        f"VARIANT_ITERATION: {variant_iteration}",
        f"STAGE: {stage_name}",
        f"COMMAND: {format_command(command)}",
        f"CWD: {cwd}",
        f"EXIT_CODE: {exit_code}",
        f"DURATION_SECONDS: {duration_seconds:.3f}",
        "",
        "STDOUT:",
        stdout,
        "",
        "STDERR:",
        stderr,
        "",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(lines), encoding="utf-8")


def _run_stage(
    experiment_dir: Path,
    global_iteration: int,
    variant_id: str,
    variant_iteration: int,
    stage_name: str,
    command: Sequence[str],
) -> dict[str, Any]:
    log_path = experiment_dir / "logs" / f"iteration_{global_iteration:03d}_{stage_name}.log"
    result = _STEP_RUNNER.run_step(
        stage_name,
        list(command),
        env.REPO_ROOT,
        title=f"iteration {global_iteration:03d} {stage_name}",
    )
    exit_code = result.exit_code
    stdout = result.stdout
    stderr = result.stderr
    duration_seconds = result.duration_seconds

    _write_stage_log(
        log_path,
        global_iteration,
        variant_id,
        variant_iteration,
        stage_name,
        command,
        env.REPO_ROOT,
        exit_code,
        stdout,
        stderr,
        duration_seconds,
    )
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": duration_seconds,
    }


def _parse_candidate_run_dir(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if line.startswith("CANDIDATE_RUN_DIR="):
            value = line.split("=", 1)[1].strip()
            return value or None
    for prefix in ("Run directory:", "Artifacts saved to:"):
        for line in stdout.splitlines():
            if not line.startswith(prefix):
                continue
            value = line.split(":", 1)[1].strip()
            if _looks_like_candidate_run_dir(value):
                return value
    return None


def _looks_like_candidate_run_dir(value: str) -> bool:
    if not value:
        return False
    path = env._resolve_path(value)
    if not path.exists() or not path.is_dir():
        return False
    if not any((path / name).exists() for name in ("candidate.json", "llm_request.json")):
        return False
    status_path = path / "status.json"
    if not status_path.exists():
        return True
    try:
        status = env._read_json_object(status_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    scenario = status.get("scenario")
    if scenario is not None and scenario != "llm_candidate":
        return False
    return True


def _combine_closed_loop_context(
    additional_context: str | None,
    history_context: str | None,
) -> str | None:
    parts: list[str] = []
    if additional_context is not None:
        parts.append(additional_context)
    if history_context is not None:
        parts.append(history_context)
    if not parts:
        return None
    return "\n\n".join(parts)


def _closed_loop_history_context_log_path(
    experiment_dir: Path,
    iteration: int,
) -> Path:
    return experiment_dir / "logs" / f"iteration_{iteration:03d}_closed_loop_history_context.txt"


def _write_closed_loop_history_context_file(
    experiment_dir: Path,
    iteration: int,
    history_context: str | None,
) -> Path:
    log_path = _closed_loop_history_context_log_path(experiment_dir, iteration)
    content = history_context if history_context is not None else "No meaningful closed-loop history yet."
    log_path.write_text(content + "\n", encoding="utf-8")
    return log_path


def _candidate_field_summary(candidate_path: Path) -> dict[str, Any]:
    candidate = env._read_json_object(candidate_path)
    edits = candidate.get("edits")
    edit_count = len(edits) if isinstance(edits, list) else None
    return {
        "candidate_summary": candidate.get("summary"),
        "risk_level": candidate.get("risk_level"),
        "expected_effect": candidate.get("expected_effect"),
        "target_files": candidate.get("target_files"),
        "requires_manual_review": candidate.get("requires_manual_review"),
        "edit_count": edit_count,
        "is_noop": candidate.get("expected_effect") == "none" and edit_count == 0,
    }


def _empty_generation_fields() -> dict[str, Any]:
    return {
        "candidate_summary": None,
        "risk_level": None,
        "expected_effect": None,
        "target_files": None,
        "requires_manual_review": None,
        "edit_count": None,
        "is_noop": None,
    }


def _read_generation_artifacts(candidate_run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    status = env._read_json_object(candidate_run_dir / "status.json")
    candidate_fields = _empty_generation_fields()
    candidate_path = candidate_run_dir / "candidate.json"
    if candidate_path.exists():
        candidate_fields = _candidate_field_summary(candidate_path)
    return status, candidate_fields


def _generation_stage_record(stage_result: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    exit_code = stage_result["exit_code"]
    duration_seconds = stage_result["duration_seconds"]
    candidate_run_dir_text = _parse_candidate_run_dir(stage_result["stdout"])

    base_record = {
        "status": "failed",
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
        "failed_step": None,
        "error_message": None,
        **_empty_generation_fields(),
    }

    if candidate_run_dir_text is None:
        base_record["failed_step"] = "parse_candidate_run_dir"
        base_record["error_message"] = (
            "generate_candidate stdout did not contain CANDIDATE_RUN_DIR=..."
        )
        return base_record, None

    candidate_run_dir = env._resolve_path(candidate_run_dir_text)
    candidate_run_dir_display = env._display_path(candidate_run_dir)
    if not candidate_run_dir.exists() or not candidate_run_dir.is_dir():
        base_record["failed_step"] = "read_candidate_run"
        base_record["error_message"] = f"Candidate run directory not found: {candidate_run_dir}"
        return base_record, candidate_run_dir_display

    try:
        status, candidate_fields = _read_generation_artifacts(candidate_run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        base_record["failed_step"] = "read_candidate_status"
        base_record["error_message"] = str(exc)
        return base_record, candidate_run_dir_display

    generation_success = exit_code == 0 and status.get("overall_status") == "success"
    base_record.update(candidate_fields)
    base_record["status"] = "success" if generation_success else "failed"
    base_record["failed_step"] = None if generation_success else (
        status.get("failed_step") or "generate_candidate"
    )
    base_record["error_message"] = None if generation_success else (
        status.get("error_message") or f"generate_candidate exited with code {exit_code}"
    )
    return base_record, candidate_run_dir_display


def _materialization_stage_record(
    stage_result: dict[str, Any],
    candidate_run_dir: str,
) -> dict[str, Any]:
    exit_code = stage_result["exit_code"]
    duration_seconds = stage_result["duration_seconds"]
    record = {
        "status": "failed",
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
        "failed_step": None,
        "error_message": None,
        "target_files": None,
        "edit_files": None,
        "changed_files": None,
    }
    try:
        materialization = env._read_json_object(
            env._resolve_path(candidate_run_dir) / "materialization.json"
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        record["failed_step"] = "read_materialization"
        record["error_message"] = str(exc)
        return record

    materialization_status = materialization.get("overall_status")
    if exit_code == 0 and materialization_status == "success":
        record["status"] = "success"
    elif exit_code == 0 and materialization_status == "skipped":
        record["status"] = "skipped"
        record["reason"] = "materialization_skipped"
    else:
        record["status"] = "failed"
        record["failed_step"] = (
            materialization.get("failed_step") or "materialize_candidate"
        )
        record["error_message"] = (
            materialization.get("error_message")
            or f"materialize_candidate exited with code {exit_code}"
        )
    record["target_files"] = materialization.get("target_files")
    record["edit_files"] = materialization.get("edit_files")
    record["changed_files"] = materialization.get("changed_files")
    record["materialization_match_summary"] = _materialization_match_summary(materialization)
    return record


def _materialization_match_summary(materialization: dict[str, Any]) -> dict[str, Any] | None:
    if materialization.get("line_range_edit_count") is None:
        return None
    edit_results = materialization.get("line_range_edit_results")
    edit_results = edit_results if isinstance(edit_results, list) else []
    return {
        "line_range_exact_matches": materialization.get("line_range_exact_matches", 0),
        "line_range_trailing_whitespace_tolerant_matches": materialization.get("line_range_trailing_whitespace_tolerant_matches", 0),
        "line_range_surrounding_whitespace_tolerant_matches": materialization.get("line_range_surrounding_whitespace_tolerant_matches", 0),
        "line_range_fallback_matches": materialization.get("line_range_fallback_matches", 0),
        "line_range_fallback_used": bool(materialization.get("line_range_fallback_used")),
        "invalid_line_range_fallback_used": any(
            isinstance(result, dict)
            and result.get("match_mode") == "invalid_line_range_exact_search_fallback"
            for result in edit_results
        ),
        "line_range_edit_count": materialization.get("line_range_edit_count", 0),
    }


def _verification_stage_record(
    stage_result: dict[str, Any],
    candidate_run_dir: str,
) -> dict[str, Any]:
    exit_code = stage_result["exit_code"]
    duration_seconds = stage_result["duration_seconds"]
    record = {
        "status": "failed",
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
        "failed_step": None,
        "error_message": None,
        "steps": None,
    }
    try:
        verification = env._read_json_object(env._resolve_path(candidate_run_dir) / "verification.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        record["failed_step"] = "read_verification"
        record["error_message"] = str(exc)
        return record

    verification_status = verification.get("overall_status")
    if exit_code == 0 and verification_status == "success":
        record["status"] = "success"
    elif exit_code == 0 and verification_status == "skipped":
        record["status"] = "skipped"
        record["reason"] = "verification_skipped"
    else:
        record["status"] = "failed"
        record["failed_step"] = verification.get("failed_step") or "verify_candidate"
        record["error_message"] = (
            verification.get("error_message")
            or f"verify_candidate exited with code {exit_code}"
        )
    record["steps"] = verification.get("steps")
    record["adapter_validation"] = verification.get("adapter_validation")
    record["benchmark"] = verification.get("benchmark")
    return record


def _read_candidate_json(candidate_run_dir: Path) -> dict[str, Any]:
    return env._read_json_object(candidate_run_dir / "candidate.json")


def _candidate_summary_for_record(candidate: dict[str, Any] | None) -> str | None:
    if candidate is None:
        return None
    summary = candidate.get("summary")
    return summary if isinstance(summary, str) else None


def is_noop_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("expected_effect") != "none":
        return False
    edits = candidate.get("edits")
    return isinstance(edits, list) and len(edits) == 0


def _resolve_materialized_workspace(candidate_run_dir: Path) -> Path:
    materialization = env._read_json_object(candidate_run_dir / "materialization.json")
    workspace_path = materialization.get("workspace_path")
    if not isinstance(workspace_path, str) or not workspace_path.strip():
        raise ValueError("materialization.json is missing non-empty workspace_path")
    return env._resolve_path(workspace_path)


def _compact_decision_summary(decision: dict[str, Any] | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    comparison = decision.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}
    return {
        "status": decision.get("status"),
        "reference_kind": decision.get("reference_kind"),
        "speedup": comparison.get("speedup"),
        "runtime_reduction_percent": comparison.get("runtime_reduction_percent"),
        "comparison": comparison,
        "thresholds": decision.get("thresholds"),
        "rejection_reasons": decision.get("rejection_reasons"),
        "non_acceptance_reasons": decision.get("non_acceptance_reasons"),
        "audit_issues": decision.get("audit_issues"),
    }


def _decision_speedup(decision: dict[str, Any] | None) -> float | None:
    if decision is None:
        return None
    comparison = decision.get("comparison")
    if not isinstance(comparison, dict):
        return None
    speedup = comparison.get("speedup")
    return float(speedup) if isinstance(speedup, (int, float)) and not isinstance(speedup, bool) else None


def _closed_loop_phase_timings(
    iteration_started: float,
    generation_result: dict[str, Any] | None = None,
    materialization_result: dict[str, Any] | None = None,
    verification_result: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    return {
        "generation_seconds": _stage_duration_or_none(generation_result),
        "materialization_seconds": _stage_duration_or_none(materialization_result),
        "verification_seconds": _stage_duration_or_none(verification_result),
        "benchmark_seconds": None,
        "total_iteration_seconds": round(time.perf_counter() - iteration_started, 3),
    }


def _stage_duration_or_none(stage_result: dict[str, Any] | None) -> float | None:
    if not isinstance(stage_result, dict):
        return None
    duration = stage_result.get("duration_seconds")
    return float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None


def _candidate_source_artifacts(candidate_run_dir: Path | None) -> dict[str, str | None]:
    if candidate_run_dir is None:
        return {}
    return {
        "status": env._display_path(candidate_run_dir / "status.json"),
        "candidate": env._display_path(candidate_run_dir / "candidate.json"),
        "materialization": env._display_path(candidate_run_dir / "materialization.json"),
        "verification": env._display_path(candidate_run_dir / "verification.json"),
        "decision_vs_current_best": env._display_path(candidate_run_dir / "decision_vs_current_best.json"),
        "decision_vs_original_baseline": env._display_path(candidate_run_dir / "decision_vs_original_baseline.json"),
    }


def _read_optional_candidate_artifact(candidate_run_dir: Path | None, name: str) -> dict[str, Any] | None:
    if candidate_run_dir is None:
        return None
    try:
        return env._read_json_object(candidate_run_dir / name)
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _closed_loop_outcome_reason(
    *,
    status: IterationStatus,
    record_fields: dict[str, Any] | None = None,
    candidate_run_dir: Path | None = None,
    candidate: dict[str, Any] | None = None,
    generation: dict[str, Any] | None = None,
    materialization: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    decision_vs_current_best: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if materialization is None:
        materialization = _read_optional_candidate_artifact(candidate_run_dir, "materialization.json")
    if verification is None:
        verification = _read_optional_candidate_artifact(candidate_run_dir, "verification.json")
    if decision_vs_current_best is None:
        decision_vs_current_best = _read_optional_candidate_artifact(candidate_run_dir, "decision_vs_current_best.json")
    reason = build_outcome_reason(
        status=status.value,
        record=record_fields,
        candidate_run_dir=candidate_run_dir,
        candidate=candidate,
        generation=generation,
        materialization=materialization,
        verification=verification,
        decision_vs_current_best=decision_vs_current_best,
        source_artifacts=_candidate_source_artifacts(candidate_run_dir),
    )
    return outcome_reason_to_dict(reason) or {}


def _build_closed_loop_iteration_record(
    *,
    experiment_id: str,
    iteration: int,
    status: IterationStatus,
    base_source_kind: str,
    reference_best_iteration_before: int,
    reference_best_run_dir: Path | None,
    candidate_run_dir: Path | None,
    candidate: dict[str, Any] | None,
    decision_vs_current_best: dict[str, Any] | None,
    decision_vs_original_baseline: dict[str, Any] | None,
    current_best_updated: bool,
    current_best_iteration_after: int,
    failure_stage: str | None = None,
    failure_reason: str | None = None,
    materialization_match_summary: dict[str, Any] | None = None,
    phase_timings: dict[str, float | None] | None = None,
    outcome_reason: dict[str, Any] | None = None,
) -> ClosedLoopIterationRecord:
    record = ClosedLoopIterationRecord(
        experiment_id=experiment_id,
        iteration=iteration,
        status=status,
        base_source_kind=base_source_kind,
        reference_best_iteration_before=reference_best_iteration_before,
        reference_best_run_dir=reference_best_run_dir,
        candidate_run_dir=candidate_run_dir,
        candidate_summary=_candidate_summary_for_record(candidate),
        candidate_rationale=(candidate or {}).get("rationale") if isinstance((candidate or {}).get("rationale"), str) else None,
        candidate_expected_effect=(candidate or {}).get("expected_effect") if isinstance((candidate or {}).get("expected_effect"), str) else None,
        candidate_risk_level=(candidate or {}).get("risk_level") if isinstance((candidate or {}).get("risk_level"), str) else None,
        decision_vs_current_best=_compact_decision_summary(decision_vs_current_best),
        decision_vs_original_baseline=_compact_decision_summary(decision_vs_original_baseline),
        speedup_vs_current_best=_decision_speedup(decision_vs_current_best),
        speedup_vs_original_baseline=_decision_speedup(decision_vs_original_baseline),
        current_best_updated=current_best_updated,
        current_best_iteration_after=current_best_iteration_after,
        failure_stage=failure_stage,
        failure_reason=failure_reason,
        materialization_match_summary=materialization_match_summary,
        phase_timings=phase_timings,
        outcome_reason=outcome_reason,
        history_included=False,
        history_guidance=None,
        created_at=env._now_iso(),
    )
    plain_record = to_plain_dict(record)
    if should_include_in_closed_loop_history(plain_record):
        record.history_included = True
        record.history_guidance = build_history_guidance(plain_record)
    return record


def _append_closed_loop_record_and_state(
    paths: ClosedLoopPaths,
    state: CurrentBestState,
    record: ClosedLoopIterationRecord,
) -> None:
    paths.closed_loop_iterations_path.parent.mkdir(parents=True, exist_ok=True)
    with paths.closed_loop_iterations_path.open("a", encoding="utf-8") as output_file:
        output_file.write(
            json.dumps(env._portable_plain_dict(record), ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
    env._write_current_best_state(paths, state)


def run_closed_loop_iterations(
    config: ExperimentConfig,
    experiment_id: str,
    experiment_dir: Path,
    llm_metadata_by_variant: dict[str, dict[str, Any]],
) -> tuple[ClosedLoopPaths, CurrentBestState, list[ClosedLoopIterationRecord], str]:
    variant = config.variants[0]
    llm_metadata = llm_metadata_by_variant[variant.variant_id]
    baseline_run_dir = env._resolve_path(config.baseline_run_dir)

    closed_loop_paths = ClosedLoopPaths.from_roots(env.WORKSPACE_ROOT, env.RESULTS_ROOT, experiment_id)
    env.initialize_current_best_source(closed_loop_paths, config)
    state = env._initialize_current_best_state(closed_loop_paths, experiment_id, config, baseline_run_dir)
    env._write_current_best_state(closed_loop_paths, state)

    records: list[ClosedLoopIterationRecord] = []
    print("Closed-loop mode: enabled")
    print(f"Current best source: {env._display_path(closed_loop_paths.current_best_source_dir)}")

    for iteration in range(1, variant.iterations + 1):
        iteration_started = time.perf_counter()
        print(f"\nClosed-loop iteration {iteration}/{variant.iterations}")
        reference_best_iteration_before = state.current_best_iteration
        reference_run_dir_before = state.current_best_run_dir
        reference_kind = "baseline" if state.current_best_is_baseline else "verified_candidate"
        base_source_kind = "baseline" if state.current_best_is_baseline else "current_best"
        candidate: dict[str, Any] | None = None
        candidate_run_dir: Path | None = None

        iteration_dir_name = format_iteration_dir(iteration)
        candidate_run_dir_path = env.RESULTS_ROOT / "runs" / experiment_id / iteration_dir_name
        candidate_workspace_dir_path = env.WORKSPACE_ROOT / "candidates" / experiment_id / iteration_dir_name

        closed_loop_history_context = build_closed_loop_history_context(
            [to_plain_dict(record) for record in records]
        )
        _write_closed_loop_history_context_file(
            experiment_dir,
            iteration,
            closed_loop_history_context,
        )
        generation_context = _combine_closed_loop_context(
            variant.additional_context,
            closed_loop_history_context,
        )

        generation_result = _run_stage(
            experiment_dir,
            iteration,
            variant.variant_id,
            iteration,
            "generate_candidate",
            _build_generation_command(
                config,
                llm_metadata["resolved_config"],
                generation_context,
                source_root=str(closed_loop_paths.current_best_source_dir),
                candidate_run_dir=str(candidate_run_dir_path),
            ),
        )
        generation_record, candidate_run_dir_text = _generation_stage_record(generation_result)
        if candidate_run_dir_text is not None:
            candidate_run_dir = env._resolve_path(candidate_run_dir_text)
        if generation_record["status"] != "success" or candidate_run_dir is None:
            record = _build_closed_loop_iteration_record(
                experiment_id=experiment_id,
                iteration=iteration,
                status=IterationStatus.GENERATION_FAILED,
                base_source_kind=base_source_kind,
                reference_best_iteration_before=reference_best_iteration_before,
                reference_best_run_dir=reference_run_dir_before,
                candidate_run_dir=candidate_run_dir,
                candidate=None,
                decision_vs_current_best=None,
                decision_vs_original_baseline=None,
                current_best_updated=False,
                current_best_iteration_after=state.current_best_iteration,
                failure_stage="generation",
                failure_reason=generation_record.get("error_message") or generation_record.get("failed_step"),
                phase_timings=_closed_loop_phase_timings(iteration_started, generation_result),
                outcome_reason=_closed_loop_outcome_reason(
                    status=IterationStatus.GENERATION_FAILED,
                    record_fields=generation_record,
                    candidate_run_dir=candidate_run_dir,
                    generation=generation_record,
                ),
            )
            records.append(record)
            _append_closed_loop_record_and_state(closed_loop_paths, state, record)
            print("- iteration: generation_failed")
            continue

        try:
            candidate = _read_candidate_json(candidate_run_dir)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            record = _build_closed_loop_iteration_record(
                experiment_id=experiment_id,
                iteration=iteration,
                status=IterationStatus.GENERATION_FAILED,
                base_source_kind=base_source_kind,
                reference_best_iteration_before=reference_best_iteration_before,
                reference_best_run_dir=reference_run_dir_before,
                candidate_run_dir=candidate_run_dir,
                candidate=None,
                decision_vs_current_best=None,
                decision_vs_original_baseline=None,
                current_best_updated=False,
                current_best_iteration_after=state.current_best_iteration,
                failure_stage="generation",
                failure_reason=f"Could not read usable candidate.json: {exc}",
                phase_timings=_closed_loop_phase_timings(iteration_started, generation_result),
                outcome_reason=_closed_loop_outcome_reason(
                    status=IterationStatus.GENERATION_FAILED,
                    record_fields={"failed_step": "read_candidate_json", "failure_reason": str(exc)},
                    candidate_run_dir=candidate_run_dir,
                    generation={"failed_step": "candidate_json_invalid", "error_message": str(exc)},
                ),
            )
            records.append(record)
            _append_closed_loop_record_and_state(closed_loop_paths, state, record)
            print("- iteration: generation_failed")
            continue

        if is_noop_candidate(candidate):
            record = _build_closed_loop_iteration_record(
                experiment_id=experiment_id,
                iteration=iteration,
                status=IterationStatus.NO_OP,
                base_source_kind=base_source_kind,
                reference_best_iteration_before=reference_best_iteration_before,
                reference_best_run_dir=reference_run_dir_before,
                candidate_run_dir=candidate_run_dir,
                candidate=candidate,
                decision_vs_current_best=None,
                decision_vs_original_baseline=None,
                current_best_updated=False,
                current_best_iteration_after=state.current_best_iteration,
                phase_timings=_closed_loop_phase_timings(iteration_started, generation_result),
                outcome_reason=_closed_loop_outcome_reason(
                    status=IterationStatus.NO_OP,
                    candidate_run_dir=candidate_run_dir,
                    candidate=candidate,
                ),
            )
            records.append(record)
            _append_closed_loop_record_and_state(closed_loop_paths, state, record)
            print("- iteration: no_op")
            continue

        materialization_result = _run_stage(
            experiment_dir,
            iteration,
            variant.variant_id,
            iteration,
            "materialize_candidate",
            _build_materialization_command(
                str(candidate_run_dir),
                config,
                base_source_root=str(closed_loop_paths.current_best_source_dir),
                candidate_workspace_dir=str(candidate_workspace_dir_path),
            ),
        )
        materialization_record = _materialization_stage_record(materialization_result, str(candidate_run_dir))
        if materialization_record["status"] != "success":
            record = _build_closed_loop_iteration_record(
                experiment_id=experiment_id,
                iteration=iteration,
                status=IterationStatus.MATERIALIZATION_FAILED,
                base_source_kind=base_source_kind,
                reference_best_iteration_before=reference_best_iteration_before,
                reference_best_run_dir=reference_run_dir_before,
                candidate_run_dir=candidate_run_dir,
                candidate=candidate,
                decision_vs_current_best=None,
                decision_vs_original_baseline=None,
                current_best_updated=False,
                current_best_iteration_after=state.current_best_iteration,
                failure_stage="materialization",
                failure_reason=materialization_record.get("error_message") or materialization_record.get("failed_step"),
                materialization_match_summary=materialization_record.get("materialization_match_summary"),
                phase_timings=_closed_loop_phase_timings(
                    iteration_started,
                    generation_result,
                    materialization_result,
                ),
                outcome_reason=_closed_loop_outcome_reason(
                    status=IterationStatus.MATERIALIZATION_FAILED,
                    record_fields=materialization_record,
                    candidate_run_dir=candidate_run_dir,
                    candidate=candidate,
                ),
            )
            records.append(record)
            _append_closed_loop_record_and_state(closed_loop_paths, state, record)
            print("- iteration: materialization_failed")
            continue

        verification_result = _run_stage(
            experiment_dir,
            iteration,
            variant.variant_id,
            iteration,
            "verify_candidate",
            _build_verification_command(str(candidate_run_dir)),
        )
        verification_record = _verification_stage_record(verification_result, str(candidate_run_dir))
        if verification_record["status"] != "success":
            record = _build_closed_loop_iteration_record(
                experiment_id=experiment_id,
                iteration=iteration,
                status=IterationStatus.VERIFICATION_FAILED,
                base_source_kind=base_source_kind,
                reference_best_iteration_before=reference_best_iteration_before,
                reference_best_run_dir=reference_run_dir_before,
                candidate_run_dir=candidate_run_dir,
                candidate=candidate,
                decision_vs_current_best=None,
                decision_vs_original_baseline=None,
                current_best_updated=False,
                current_best_iteration_after=state.current_best_iteration,
                failure_stage="verification",
                failure_reason=verification_record.get("error_message") or verification_record.get("failed_step"),
                materialization_match_summary=materialization_record.get("materialization_match_summary"),
                phase_timings=_closed_loop_phase_timings(
                    iteration_started,
                    generation_result,
                    materialization_result,
                    verification_result,
                ),
                outcome_reason=_closed_loop_outcome_reason(
                    status=IterationStatus.VERIFICATION_FAILED,
                    record_fields=verification_record,
                    candidate_run_dir=candidate_run_dir,
                    candidate=candidate,
                ),
            )
            records.append(record)
            _append_closed_loop_record_and_state(closed_loop_paths, state, record)
            print("- iteration: verification_failed")
            continue

        decision_vs_current_best = evaluate_candidate_against_reference(
            reference_run_dir=state.current_best_run_dir,
            reference_kind=reference_kind,
            candidate_run_dir=candidate_run_dir,
        )
        decision_vs_original_baseline = evaluate_candidate_against_reference(
            reference_run_dir=baseline_run_dir,
            reference_kind="baseline",
            candidate_run_dir=candidate_run_dir,
        )
        write_candidate_decision(candidate_run_dir, decision_vs_current_best, "decision_vs_current_best.json")
        write_candidate_decision(candidate_run_dir, decision_vs_original_baseline, "decision_vs_original_baseline.json")

        decision_status = decision_vs_current_best.get("status")
        current_best_updated = False
        if decision_status == "accepted_improvement":
            workspace_path = _resolve_materialized_workspace(candidate_run_dir)
            env.update_current_best_source_from_workspace(closed_loop_paths, workspace_path, config)
            state.current_best_iteration = iteration
            state.current_best_is_baseline = False
            state.current_best_run_dir = candidate_run_dir
            state.current_best_metrics_path = candidate_run_dir / "verification.json"
            state.accepted_improvements += 1
            iteration_status = IterationStatus.ACCEPTED_IMPROVEMENT
            current_best_updated = True
        elif decision_status == "valid_not_improved":
            iteration_status = IterationStatus.VALID_NOT_IMPROVED
        else:
            iteration_status = IterationStatus.REJECTED

        record = _build_closed_loop_iteration_record(
            experiment_id=experiment_id,
            iteration=iteration,
            status=iteration_status,
            base_source_kind=base_source_kind,
            reference_best_iteration_before=reference_best_iteration_before,
            reference_best_run_dir=reference_run_dir_before,
            candidate_run_dir=candidate_run_dir,
            candidate=candidate,
            decision_vs_current_best=decision_vs_current_best,
            decision_vs_original_baseline=decision_vs_original_baseline,
            current_best_updated=current_best_updated,
            current_best_iteration_after=state.current_best_iteration,
            materialization_match_summary=materialization_record.get("materialization_match_summary"),
            phase_timings=_closed_loop_phase_timings(
                iteration_started,
                generation_result,
                materialization_result,
                verification_result,
            ),
            outcome_reason=_closed_loop_outcome_reason(
                status=iteration_status,
                candidate_run_dir=candidate_run_dir,
                candidate=candidate,
                decision_vs_current_best=decision_vs_current_best,
            ),
        )
        records.append(record)
        _append_closed_loop_record_and_state(closed_loop_paths, state, record)
        print(f"- iteration: {iteration_status.value}")

    return closed_loop_paths, state, records, env._now_iso()
