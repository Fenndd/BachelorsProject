"""Closed-loop experiment runner.

This runner executes one closed-loop optimization experiment. It never promotes
candidates into the main ``cpp/`` source tree. Accepted candidates are promoted
only into the experiment-local ``current_best_source`` workspace.

Build type for candidate verification:
  The candidate verification stage defaults to Release builds (optimized) so
  that runtime metrics collected during verification reflect production
  performance.  To override, set the CMAKE_BUILD_TYPE environment variable
  before launching the experiment runner:
    set CMAKE_BUILD_TYPE=Debug   (Windows cmd)
    $env:CMAKE_BUILD_TYPE="Debug"  (PowerShell)
    export CMAKE_BUILD_TYPE=Debug  (Unix)
  The experiment runner does not pass an explicit --cmake-build-type flag to
  verify_candidate; it relies on the environment-variable default defined in
  the verification module.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import fnmatch
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .experiment_config import (
    ExperimentConfig,
    ExperimentConfigError,
    ExperimentVariantConfig,
    load_experiment_config,
)
from .closed_loop_state import (
    ClosedLoopIterationRecord,
    ClosedLoopPaths,
    ClosedLoopSummary,
    CurrentBestState,
    IterationStatus,
    count_iteration_statuses,
    to_plain_dict,
    write_closed_loop_summary,
    write_current_best_state,
)
from .closed_loop_history import (
    build_closed_loop_history_context,
    build_history_guidance,
    should_include_in_closed_loop_history,
)
from .final_selection_report import (
    FINAL_SELECTION_REPORT_FILENAME,
    run_final_selection_report,
)
from .outcome_reason import build_outcome_reason, outcome_reason_to_dict
from orchestrator.benchmarking.candidate_decision import (
    evaluate_candidate_against_reference,
    write_candidate_decision,
)
from orchestrator.patching.diff_stats import parse_unified_diff_stats
from orchestrator.reporting.generate_report import generate_basic_report, refresh_report_artifact_map
from orchestrator.storage.experiment_registry import allocate_next_experiment_run


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "results"
EXPERIMENTS_ROOT = RESULTS_ROOT / "experiments"
WORKSPACE_ROOT = REPO_ROOT / "workspace"


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


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _display_path(path: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        pass
    try:
        return (Path("workspace") / path.resolve().relative_to(WORKSPACE_ROOT)).as_posix()
    except ValueError:
        return str(path)


def _format_command(command: Sequence[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in: {path}")
    return payload


def _run_git_command(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _experiment_repository_info() -> dict[str, Any]:
    git_commit = _run_git_command(["rev-parse", "HEAD"])
    git_branch = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    git_status = _run_git_command(["status", "--porcelain"])
    return {
        "git_commit": git_commit or "unknown",
        "git_branch": git_branch or "unknown",
        "dirty_worktree": None if git_status is None else bool(git_status),
    }


def _experiment_environment_info() -> dict[str, Any]:
    return {
        "os": os.name,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cmake_build_type": os.environ.get("BENCHMARK_CMAKE_BUILD_TYPE") or os.environ.get("CMAKE_BUILD_TYPE") or "Release",
        "cmake_exe": os.environ.get("CMAKE_EXE"),
        "cmake_generator": os.environ.get("CMAKE_GENERATOR"),
        "cxx_compiler": os.environ.get("CMAKE_CXX_COMPILER"),
    }


def _write_experiment_metadata(
    experiment_dir: Path,
    started_at: datetime,
    finished_at: str | None = None,
) -> Path:
    total_duration: float | None = None
    if finished_at is not None:
        try:
            finished_dt = datetime.fromisoformat(finished_at)
            total_duration = round((finished_dt - started_at).total_seconds(), 3)
        except ValueError:
            total_duration = None
    payload = {
        "schema_version": "experiment_metadata.v1",
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at,
        "total_duration_seconds": total_duration,
        "repository": _experiment_repository_info(),
        "environment": _experiment_environment_info(),
    }
    path = experiment_dir / "experiment_metadata.json"
    _write_json(path, _portable_plain_dict(payload))
    return path


def _read_json_file_object(path: Path, label: str) -> dict[str, Any]:
    try:
        return _read_json_object(path)
    except json.JSONDecodeError as exc:
        raise ExperimentConfigError(f"{label} is not valid JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise ExperimentConfigError(f"Could not read {label}: {path}: {exc}") from exc
    except ValueError as exc:
        raise ExperimentConfigError(str(exc)) from exc


def _safe_artifact_name(value: str) -> str:
    lowered = value.lower()
    separated = re.sub(r"[\s/\\]+", "_", lowered)
    safe = re.sub(r"[^a-z0-9_-]+", "_", separated)
    compacted = re.sub(r"_+", "_", safe).strip("_-")
    return compacted or "experiment"


def _total_iterations(config: ExperimentConfig) -> int:
    return sum(variant.iterations for variant in config.variants)


def _apply_llm_overrides(
    base_config: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    resolved = copy.deepcopy(base_config)
    if overrides is None:
        return resolved

    for key, value in overrides.items():
        if key == "thinking":
            current = resolved.get("thinking")
            resolved_thinking = copy.deepcopy(current) if isinstance(current, dict) else {}
            resolved_thinking.update(copy.deepcopy(value))
            resolved["thinking"] = resolved_thinking
        elif value is None:
            resolved.pop(key, None)
        else:
            resolved[key] = copy.deepcopy(value)
    return resolved


def _resolve_variant_llm_config(variant: ExperimentVariantConfig) -> dict[str, Any]:
    base_config_path = _resolve_path(variant.llm_config)
    base_config = _read_json_file_object(base_config_path, "LLM config")
    return _apply_llm_overrides(base_config, variant.llm_overrides)


def _llm_metadata(
    variant: ExperimentVariantConfig,
    resolved_config: dict[str, Any],
    resolved_config_path: Path | None,
) -> dict[str, Any]:
    thinking = resolved_config.get("thinking")
    thinking = thinking if isinstance(thinking, dict) else {}
    return {
        "base_config": variant.llm_config,
        "resolved_config": (
            _display_path(resolved_config_path) if resolved_config_path is not None else None
        ),
        "provider": resolved_config.get("provider"),
        "model": resolved_config.get("model"),
        "thinking_enabled": thinking.get("enabled"),
        "reasoning_effort": thinking.get("effort"),
        "max_tokens": resolved_config.get("max_tokens"),
    }


def _variant_llm_config_path(experiment_dir: Path, variant_id: str) -> Path:
    return (
        experiment_dir
        / "variant_configs"
        / f"{_safe_artifact_name(variant_id)}_llm_config.json"
    )


def _write_resolved_variant_llm_configs(
    experiment_dir: Path,
    config: ExperimentConfig,
) -> dict[str, dict[str, Any]]:
    variant_configs_dir = experiment_dir / "variant_configs"
    variant_configs_dir.mkdir(parents=True, exist_ok=True)
    metadata_by_variant: dict[str, dict[str, Any]] = {}
    for variant in config.variants:
        resolved_config = _resolve_variant_llm_config(variant)
        resolved_config_path = _variant_llm_config_path(experiment_dir, variant.variant_id)
        _write_json(resolved_config_path, resolved_config)
        metadata_by_variant[variant.variant_id] = _llm_metadata(
            variant,
            resolved_config,
            resolved_config_path,
        )
    return metadata_by_variant


def _print_plan(config: ExperimentConfig, dry_run: bool) -> None:
    candidate_generation = config.candidate_generation
    candidate_format = config.candidate_format

    print("Experiment dry run" if dry_run else "Experiment plan")
    print(f"Experiment name: {config.experiment_name}")
    print(f"Description: {config.description or 'none'}")
    print(f"Target file: {config.target_file}")
    print("Mode: closed-loop optimization")
    print(f"Baseline run dir: {config.baseline_run_dir}")
    print(f"Max source chars: {candidate_generation.max_source_chars}")
    print("Candidate format:")
    print(f"- type: {candidate_format.type}")
    print(f"- source_presentation: {candidate_format.source_presentation}")
    print(
        f"- require_original_verification: "
        f"{candidate_format.require_original_verification}"
    )
    print(
        f"- allow_exact_search_fallback: "
        f"{candidate_format.allow_exact_search_fallback}"
    )
    print(
        f"Optimization scope allowed files: "
        f"{config.optimization_scope.allowed_files}"
    )
    print(f"Variants: {len(config.variants)}")
    for variant in config.variants:
        resolved_llm_config = _resolve_variant_llm_config(variant)
        llm_metadata = _llm_metadata(variant, resolved_llm_config, None)
        print("")
        print(f"Variant: {variant.variant_id}")
        print(f"- description: {variant.description or 'none'}")
        print(f"- base llm_config: {variant.llm_config}")
        print(
            "- llm_overrides: "
            + (
                json.dumps(variant.llm_overrides, ensure_ascii=False, sort_keys=True)
                if variant.llm_overrides is not None
                else "none"
            )
        )
        print(f"- effective provider: {llm_metadata['provider']}")
        print(f"- effective model: {llm_metadata['model']}")
        print(f"- effective thinking.enabled: {llm_metadata['thinking_enabled']}")
        print(f"- effective thinking.effort: {llm_metadata['reasoning_effort']}")
        print(f"- effective max_tokens: {llm_metadata['max_tokens']}")
        print(f"- iterations: {variant.iterations}")
        print(f"- additional_context: {variant.additional_context or 'none'}")
    print("")
    print(f"Total planned iterations: {_total_iterations(config)}")
    if dry_run:
        print("")
        print("Dry run only: no LLM requests, candidates, materialization, or verification were run.")


def _build_generation_command(
    config: ExperimentConfig,
    llm_config_path: str,
    context_text: str | None,
    source_root: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "orchestrator.llm.generate_candidate",
        "--config",
        llm_config_path,
        "--source",
        config.target_file,
        "--max-source-chars",
        str(config.candidate_generation.max_source_chars),
        "--candidate-type",
        config.candidate_format.type,
        "--source-presentation",
        config.candidate_format.source_presentation,
    ]
    if source_root is not None:
        command.extend(["--source-root", source_root])
    if context_text is not None:
        command.extend(["--context", context_text])
    # Pass each allowed file as a separate --allowed-file argument
    for allowed_file in config.optimization_scope.allowed_files:
        command.extend(["--allowed-file", allowed_file])
    return command


def _build_materialization_command(
    candidate_run_dir: str,
    config: ExperimentConfig,
    base_source_root: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "orchestrator.patching.materialize_candidate",
        "--candidate-run",
        candidate_run_dir,
        "--overwrite",
    ]
    if base_source_root is not None:
        command.extend(["--base-source-root", base_source_root])
    if config.candidate_format.allow_exact_search_fallback:
        command.append("--allow-exact-search-fallback")
    else:
        command.append("--no-allow-exact-search-fallback")
    # Pass each allowed file as a separate --allowed-file argument
    for allowed_file in config.optimization_scope.allowed_files:
        command.extend(["--allowed-file", allowed_file])
    return command


def _build_verification_command(candidate_run_dir: str) -> list[str]:
    # CMAKE_BUILD_TYPE is not passed explicitly here; the verification module
    # reads it from the environment (defaulting to "Release").  Set the env
    # variable before launching the experiment to control the build type.
    return [
        sys.executable,
        "-m",
        "orchestrator.execution.verify_candidate",
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
        f"COMMAND: {_format_command(command)}",
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
    started = time.perf_counter()
    try:
        result = subprocess.run(
            list(command),
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        duration_seconds = round(time.perf_counter() - started, 3)
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except OSError as exc:
        duration_seconds = round(time.perf_counter() - started, 3)
        exit_code = None
        stdout = ""
        stderr = f"Could not start {stage_name} subprocess: {exc}"

    _write_stage_log(
        log_path,
        global_iteration,
        variant_id,
        variant_iteration,
        stage_name,
        command,
        REPO_ROOT,
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
    path = _resolve_path(value)
    if not path.exists() or not path.is_dir():
        return False
    if not any((path / name).exists() for name in ("candidate.json", "llm_request.json")):
        return False
    status_path = path / "status.json"
    if not status_path.exists():
        return True
    try:
        status = _read_json_object(status_path)
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
    candidate = _read_json_object(candidate_path)
    candidate_type = candidate.get("candidate_type", "unified_diff")
    edits = candidate.get("edits")
    structured_edit_count = (
        len(edits)
        if candidate_type == "line_range_edits" and isinstance(edits, list)
        else None
    )
    return {
        "candidate_summary": candidate.get("summary"),
        "risk_level": candidate.get("risk_level"),
        "expected_effect": candidate.get("expected_effect"),
        "target_files": candidate.get("target_files"),
        "requires_manual_review": candidate.get("requires_manual_review"),
        "candidate_type": candidate_type,
        "structured_edit_count": structured_edit_count,
        "candidate_edits_present": bool(structured_edit_count),
        "unified_diff_present": bool(candidate.get("unified_diff")),
    }


def _empty_generation_fields() -> dict[str, Any]:
    return {
        "candidate_summary": None,
        "risk_level": None,
        "expected_effect": None,
        "target_files": None,
        "requires_manual_review": None,
        "candidate_type": None,
        "structured_edit_count": None,
        "candidate_edits_present": None,
        "unified_diff_present": None,
    }


def _read_generation_artifacts(candidate_run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    status = _read_json_object(candidate_run_dir / "status.json")
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

    candidate_run_dir = _resolve_path(candidate_run_dir_text)
    candidate_run_dir_display = _display_path(candidate_run_dir)
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
        "patched_files": None,
        "changed_files": None,
    }
    try:
        materialization = _read_json_object(
            _resolve_path(candidate_run_dir) / "materialization.json"
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
    record["patched_files"] = materialization.get("patched_files")
    record["changed_files"] = materialization.get("changed_files")
    record["materialization_match_summary"] = _materialization_match_summary(materialization)
    return record


def _materialization_match_summary(materialization: dict[str, Any]) -> dict[str, Any] | None:
    if materialization.get("candidate_type") != "line_range_edits" and materialization.get("line_range_edit_count") is None:
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
        verification = _read_json_object(_resolve_path(candidate_run_dir) / "verification.json")
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


def _write_early_failure_artifacts(
    experiment_dir: Path,
    experiment_id: str,
    config: ExperimentConfig,
    started_at: datetime,
    failed_step: str,
    error_message: str,
) -> None:
    variant = config.variants[0]
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
        "candidate_format": asdict(config.candidate_format),
        "variants": [
            {
                "variant_id": variant.variant_id,
                "planned_iterations": variant.iterations,
                "base_llm_config": variant.llm_config,
                "resolved_llm_config": None,
                "provider": None,
                "model": None,
                "thinking_enabled": None,
                "reasoning_effort": None,
                "max_tokens": None,
            }
        ],
    }
    status_finished_at = status.get("finished_at")
    _write_experiment_metadata(
        experiment_dir,
        started_at,
        status_finished_at if isinstance(status_finished_at, str) else None,
    )
    _write_json(experiment_dir / "experiment_status.json", status)
    lines = [
        f"Experiment id: {experiment_id}",
        f"Experiment name: {config.experiment_name}",
        f"Description: {config.description or 'none'}",
        f"Target file: {config.target_file}",
        f"Baseline run dir: {config.baseline_run_dir}",
        "Candidate format:",
        f"- type: {config.candidate_format.type}",
        f"- source_presentation: {config.candidate_format.source_presentation}",
        (
            f"- require_original_verification: "
            f"{config.candidate_format.require_original_verification}"
        ),
        (
            f"- allow_exact_search_fallback: "
            f"{config.candidate_format.allow_exact_search_fallback}"
        ),
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


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


SOURCE_TREE_IGNORE_NAMES = {"build", "CMakeFiles", "Testing", "CMakeCache.txt", "build.ninja"}
SOURCE_TREE_IGNORE_PATTERNS = {
    "build-*",
    "cmake-build-*",
    ".ninja_*",
    "*.exe",
    "*.obj",
    "*.o",
    "*.pdb",
    "*.ilk",
    "*.dll",
    "*.lib",
    "*.a",
}


def _source_tree_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in SOURCE_TREE_IGNORE_NAMES:
            ignored.add(name)
        elif any(fnmatch.fnmatch(name, pattern) for pattern in SOURCE_TREE_IGNORE_PATTERNS):
            ignored.add(name)
    return ignored


def _copy_source_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=_source_tree_ignore)


def _portable_plain_dict(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _portable_plain_dict(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Path):
        return _display_path(value)
    if isinstance(value, str):
        return _portable_path_string(value)
    if isinstance(value, list):
        return [_portable_plain_dict(item) for item in value]
    if isinstance(value, tuple):
        return [_portable_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _portable_plain_dict(item) for key, item in value.items()}
    return to_plain_dict(value)


def _portable_path_string(value: str) -> str:
    if not value:
        return value
    try:
        path = Path(value)
    except (TypeError, ValueError):
        return value
    if not path.is_absolute():
        return value.replace("\\", "/")
    return _display_path(path)


def _ensure_path_inside(path: Path, root: Path, label: str) -> None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise ValueError(f"Refusing unsafe {label} path outside {resolved_root}: {resolved_path}")


def initialize_current_best_source(paths: ClosedLoopPaths, config: ExperimentConfig) -> None:
    """Create current_best_source from the clean repository cpp tree."""

    current_best_source_dir = paths.current_best_source_dir
    _ensure_path_inside(current_best_source_dir, WORKSPACE_ROOT / "experiments", "current best source")
    if current_best_source_dir.exists():
        shutil.rmtree(current_best_source_dir)
    current_best_source_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        REPO_ROOT / "cpp",
        current_best_source_dir / "cpp",
        ignore=_source_tree_ignore,
    )
    target_path = current_best_source_dir / config.target_file
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"Current best source missing target file: {target_path}")


def _initialize_current_best_state(
    paths: ClosedLoopPaths,
    experiment_id: str,
    config: ExperimentConfig,
    baseline_run_dir: Path,
) -> CurrentBestState:
    baseline_metrics_path = baseline_run_dir / "metrics.json"
    return CurrentBestState(
        experiment_id=experiment_id,
        target_file=config.target_file,
        original_baseline_run_dir=baseline_run_dir,
        original_baseline_metrics_path=baseline_metrics_path,
        current_best_iteration=0,
        current_best_is_baseline=True,
        current_best_source_dir=paths.current_best_source_dir,
        current_best_run_dir=baseline_run_dir,
        current_best_metrics_path=baseline_metrics_path,
        accepted_improvements=0,
        updated_at=_now_iso(),
    )


def _write_current_best_state(paths: ClosedLoopPaths, state: CurrentBestState) -> None:
    state.updated_at = _now_iso()
    write_current_best_state(paths.current_best_state_path, state)


def _read_candidate_json(candidate_run_dir: Path) -> dict[str, Any]:
    return _read_json_object(candidate_run_dir / "candidate.json")


def _candidate_summary_for_record(candidate: dict[str, Any] | None) -> str | None:
    if candidate is None:
        return None
    summary = candidate.get("summary")
    return summary if isinstance(summary, str) else None


def is_noop_candidate(candidate: dict[str, Any]) -> bool:
    if candidate.get("expected_effect") != "none":
        return False
    candidate_type = candidate.get("candidate_type", "unified_diff")
    if candidate_type == "line_range_edits":
        edits = candidate.get("edits")
        return not isinstance(edits, list) or len(edits) == 0
    if candidate_type == "unified_diff":
        unified_diff = candidate.get("unified_diff")
        return not isinstance(unified_diff, str) or not unified_diff.strip()
    return False


def _resolve_materialized_workspace(candidate_run_dir: Path) -> Path:
    materialization = _read_json_object(candidate_run_dir / "materialization.json")
    workspace_path = materialization.get("workspace_path")
    if not isinstance(workspace_path, str) or not workspace_path.strip():
        raise ValueError("materialization.json is missing non-empty workspace_path")
    return _resolve_path(workspace_path)


def update_current_best_source_from_workspace(
    paths: ClosedLoopPaths,
    workspace_path: Path,
    config: ExperimentConfig,
) -> None:
    workspace = workspace_path.resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise FileNotFoundError(f"Materialized workspace not found: {workspace}")
    current_best_source_dir = paths.current_best_source_dir
    _ensure_path_inside(current_best_source_dir, WORKSPACE_ROOT / "experiments", "current best source")
    if current_best_source_dir.exists():
        shutil.rmtree(current_best_source_dir)
    _copy_source_tree(workspace, current_best_source_dir)
    target_path = current_best_source_dir / config.target_file
    if not target_path.exists() or not target_path.is_file():
        raise FileNotFoundError(f"Promoted current best source missing target file: {target_path}")


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
        "status": _display_path(candidate_run_dir / "status.json"),
        "candidate": _display_path(candidate_run_dir / "candidate.json"),
        "materialization": _display_path(candidate_run_dir / "materialization.json"),
        "verification": _display_path(candidate_run_dir / "verification.json"),
        "decision_vs_current_best": _display_path(candidate_run_dir / "decision_vs_current_best.json"),
        "decision_vs_original_baseline": _display_path(candidate_run_dir / "decision_vs_original_baseline.json"),
    }


def _read_optional_candidate_artifact(candidate_run_dir: Path | None, name: str) -> dict[str, Any] | None:
    if candidate_run_dir is None:
        return None
    try:
        return _read_json_object(candidate_run_dir / name)
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
        created_at=_now_iso(),
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
            json.dumps(_portable_plain_dict(record), ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
    _write_current_best_state(paths, state)


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
    _ensure_path_inside(final_dir, paths.results_root / "experiments", "final optimized source")
    if final_dir.exists():
        shutil.rmtree(final_dir)
    _copy_source_tree(source_dir, final_dir)
    final_target = final_dir / config.target_file
    if not final_target.exists() or not final_target.is_file():
        raise FileNotFoundError(f"Final optimized source missing target file: {final_target}")
    return final_dir


def write_final_optimized_source_diff(paths: ClosedLoopPaths, config: ExperimentConfig) -> Path:
    """Write unified diff from clean baseline source to final optimized source."""

    baseline_file = REPO_ROOT / config.target_file
    final_file = paths.final_optimized_source_dir / config.target_file
    if not baseline_file.exists() or not baseline_file.is_file():
        raise FileNotFoundError(f"Baseline source missing target file: {baseline_file}")
    if not final_file.exists() or not final_file.is_file():
        raise FileNotFoundError(f"Final optimized source missing target file: {final_file}")

    baseline_lines = baseline_file.read_text(encoding="utf-8").splitlines(keepends=True)
    final_lines = final_file.read_text(encoding="utf-8").splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
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
    stats = parse_unified_diff_stats(diff_text)
    output_path = paths.final_optimized_source_diff_path.parent / "final_diff_stats.json"
    _write_json(output_path, stats)
    return stats


def copy_results_current_best_state(paths: ClosedLoopPaths) -> Path:
    """Copy workspace current-best metadata into the experiment results directory."""

    if not paths.current_best_state_path.exists():
        raise FileNotFoundError(f"Current best state not found: {paths.current_best_state_path}")
    results_state_path = _results_current_best_state_path(paths)
    results_state_path.parent.mkdir(parents=True, exist_ok=True)
    state = _read_json_object(paths.current_best_state_path)
    _write_json(results_state_path, _portable_plain_dict(state))
    return results_state_path


def _final_speedup_vs_original_baseline(
    state: CurrentBestState,
) -> tuple[float | None, float | None]:
    if state.current_best_is_baseline:
        return 1.0, 0.0

    decision_path = state.current_best_run_dir / "decision_vs_original_baseline.json"
    try:
        decision = _read_json_object(decision_path)
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
    _write_json(paths.closed_loop_summary_path, _portable_plain_dict(summary))
    return summary, results_state_path


def _update_closed_loop_summary_with_final_selection(
    paths: ClosedLoopPaths,
    summary: ClosedLoopSummary,
    report_path: Path,
) -> dict[str, Any]:
    report = _read_json_object(report_path)
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
    _write_json(paths.closed_loop_summary_path, _portable_plain_dict(summary))
    return {
        "status": status,
        "final_best_is_baseline": report.get("final_best_is_baseline"),
        "report_path": _display_path(report_path),
        "speedup_vs_original_baseline": speedup,
        "runtime_reduction_percent": runtime_reduction,
        "baseline_runtime_ns_per_problem_median": baseline_runtime,
        "final_runtime_ns_per_problem_median": final_runtime,
        "final_correctness_passed": final_correctness,
    }


def _write_effective_experiment_config(experiment_dir: Path, config: ExperimentConfig) -> Path:
    path = experiment_dir / "experiment_config_effective.json"
    _write_json(path, _portable_plain_dict(asdict(config)))
    return path


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
    """Write reporting-only final closed-loop selection analysis.

    This artifact documents the already-completed control decision. It never
    promotes candidates or copies source trees; promotion is performed only
    during iterations with decision_vs_current_best=accepted_improvement.
    """

    report_path = experiment_dir / "closed_loop_selection_report.json"
    candidate_attempts = [_compact_candidate_attempt(record) for record in (records or [])]
    final_current_best_run_dir = _display_path(state.current_best_run_dir)
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
            "source_dir": _display_path(state.current_best_source_dir),
            "metrics_path": _display_path(state.current_best_metrics_path),
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
            "final_optimized_source_dir": _display_path(summary.final_optimized_source_dir),
            "final_optimized_source_diff_path": _display_path(summary.final_optimized_source_diff_path),
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
    _write_json(report_path, payload)
    return report_path


def _compact_candidate_attempt(record: ClosedLoopIterationRecord) -> dict[str, Any]:
    return {
        "iteration": record.iteration,
        "status": record.status.value if isinstance(record.status, IterationStatus) else record.status,
        "candidate_run_dir": _display_path(record.candidate_run_dir) if record.candidate_run_dir is not None else None,
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
        "final_optimized_source_dir": _display_path(summary.final_optimized_source_dir),
        "final_optimized_source_diff_path": _display_path(summary.final_optimized_source_diff_path),
        "closed_loop_summary_path": _display_path(paths.closed_loop_summary_path),
        "closed_loop_iterations_path": _display_path(paths.closed_loop_iterations_path),
        "current_best_state_path": _display_path(results_state_path),
        "workspace_current_best_source_dir": _display_path(paths.current_best_source_dir),
        "workspace_current_best_state_path": _display_path(paths.current_best_state_path),
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
        "report_data_path": _display_path(artifacts["report_data"]),
        "report_html_path": _display_path(artifacts["html"]),
        "report_pdf_path": (
            _display_path(artifacts["pdf"]) if "pdf" in artifacts else None
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
            f"- final optimized source: {_display_path(summary.final_optimized_source_dir)}",
            f"- final diff: {_display_path(summary.final_optimized_source_diff_path)}",
            f"- closed-loop summary: {_display_path(summary.final_optimized_source_diff_path.parent / 'closed_loop_summary.json')}",
            f"- closed-loop iterations: {_display_path(summary.final_optimized_source_diff_path.parent / 'closed_loop_iterations.jsonl')}",
            f"- current best state: {_display_path(results_state_path)}",
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


def _run_closed_loop_experiment(
    config: ExperimentConfig,
    experiment_id: str,
    experiment_dir: Path,
    llm_metadata_by_variant: dict[str, dict[str, Any]],
    started_at: datetime,
) -> dict[str, Any]:
    variant = config.variants[0]
    llm_metadata = llm_metadata_by_variant[variant.variant_id]
    baseline_run_dir = _resolve_path(config.baseline_run_dir)
    baseline_metrics_path = baseline_run_dir / "metrics.json"
    if not baseline_metrics_path.exists():
        raise ExperimentConfigError(f"Closed-loop baseline metrics not found: {baseline_metrics_path}")

    closed_loop_paths = ClosedLoopPaths.from_roots(WORKSPACE_ROOT, RESULTS_ROOT, experiment_id)
    initialize_current_best_source(closed_loop_paths, config)
    state = _initialize_current_best_state(closed_loop_paths, experiment_id, config, baseline_run_dir)
    _write_current_best_state(closed_loop_paths, state)

    records: list[ClosedLoopIterationRecord] = []
    print("Closed-loop mode: enabled")
    print(f"Current best source: {_display_path(closed_loop_paths.current_best_source_dir)}")

    for iteration in range(1, variant.iterations + 1):
        iteration_started = time.perf_counter()
        print(f"\nClosed-loop iteration {iteration}/{variant.iterations}")
        reference_best_iteration_before = state.current_best_iteration
        reference_run_dir_before = state.current_best_run_dir
        reference_kind = "baseline" if state.current_best_is_baseline else "verified_candidate"
        base_source_kind = "baseline" if state.current_best_is_baseline else "current_best"
        candidate: dict[str, Any] | None = None
        candidate_run_dir: Path | None = None

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
            ),
        )
        generation_record, candidate_run_dir_text = _generation_stage_record(generation_result)
        if candidate_run_dir_text is not None:
            candidate_run_dir = _resolve_path(candidate_run_dir_text)
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
            update_current_best_source_from_workspace(closed_loop_paths, workspace_path, config)
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

    closed_loop_finished_at = _now_iso()
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
        repo_root=REPO_ROOT,
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
    finished_at = _now_iso()
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
        "candidate_format": asdict(config.candidate_format),
        "closed_loop_selection_report_path": _display_path(selection_report_path),
        "final_selection_report_path": _display_path(final_selection_report_path),
        "reporting": reporting_status,
    }
    _write_json(experiment_dir / "experiment_status.json", final_status)
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
    started_at = datetime.now().astimezone()
    try:
        allocation = allocate_next_experiment_run(EXPERIMENTS_ROOT)
    except OSError as exc:
        print(f"ERROR: Could not create experiment directory: {exc}", file=sys.stderr)
        return 1
    experiment_id = allocation.experiment_id
    experiment_dir = allocation.experiment_dir

    _write_json(experiment_dir / "experiment_config_snapshot.json", config_snapshot)
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
        print(f"Artifacts saved to: {_display_path(experiment_dir)}")
        return 1

    print("Experiment execution")
    print(f"Experiment: {config.experiment_name}")
    print(f"Experiment id: {experiment_id}")
    print(f"Experiment directory: {_display_path(experiment_dir)}")
    print("Mode: closed-loop optimization")
    print(f"Variant: {config.variants[0].variant_id}")
    print(f"Baseline run dir: {config.baseline_run_dir}")
    print(f"Planned iterations: {_total_iterations(config)}")

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
        print(f"Artifacts saved to: {_display_path(experiment_dir)}")
        return 1

    print("")
    print(f"Final experiment status: {status['overall_status']}")
    print(f"Completed iterations: {status['completed_iterations']}")
    print(f"Artifacts saved to: {_display_path(experiment_dir)}")
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


if __name__ == "__main__":
    raise SystemExit(main())
