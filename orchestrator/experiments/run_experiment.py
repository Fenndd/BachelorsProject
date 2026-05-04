"""Experiment runner for dry-runs and staged candidate iterations.

This Step 10 runner supports one or more variants. Each variant can run the
non-benchmark per-iteration pipeline: generate_candidate, optionally
materialize_candidate, and optionally verify_candidate. It still does not
benchmark, compare candidates, or select a best candidate.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from .experiment_config import (
    ExperimentConfig,
    ExperimentConfigError,
    ExperimentVariantConfig,
    load_experiment_config,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "results"
EXPERIMENTS_ROOT = RESULTS_ROOT / "experiments"


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
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _format_command(command: Sequence[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in: {path}")
    return payload


def _sanitize_name(value: str) -> str:
    lowered = value.lower()
    separated = re.sub(r"[\s/\\]+", "_", lowered)
    safe = re.sub(r"[^a-z0-9_-]+", "_", separated)
    compacted = re.sub(r"_+", "_", safe).strip("_-")
    return compacted or "experiment"


def _build_experiment_id(config: ExperimentConfig, started_at: datetime) -> str:
    timestamp = started_at.strftime("%Y-%m-%d_%H-%M-%S")
    return f"{timestamp}_{_sanitize_name(config.experiment_name)}"


def _create_experiment_dir(experiment_id: str) -> Path:
    EXPERIMENTS_ROOT.mkdir(parents=True, exist_ok=True)
    experiment_dir = EXPERIMENTS_ROOT / experiment_id
    if not experiment_dir.exists():
        (experiment_dir / "logs").mkdir(parents=True)
        return experiment_dir

    for suffix in range(1, 1000):
        candidate_dir = EXPERIMENTS_ROOT / f"{experiment_id}_{suffix:03d}"
        if not candidate_dir.exists():
            (candidate_dir / "logs").mkdir(parents=True)
            return candidate_dir

    raise OSError(f"Could not create unique experiment directory for {experiment_id}")


def _total_iterations(config: ExperimentConfig) -> int:
    return sum(variant.iterations for variant in config.variants)


def _print_plan(config: ExperimentConfig, dry_run: bool) -> None:
    pipeline = config.pipeline
    candidate_generation = config.candidate_generation

    print("Experiment dry run" if dry_run else "Experiment plan")
    print(f"Experiment name: {config.experiment_name}")
    print(f"Description: {config.description or 'none'}")
    print(f"Target file: {config.target_file}")
    print("Pipeline:")
    print(f"- generate_candidate: {pipeline.generate_candidate}")
    print(f"- materialize_candidate: {pipeline.materialize_candidate}")
    print(f"- verify_candidate: {pipeline.verify_candidate}")
    print(f"Max source chars: {candidate_generation.max_source_chars}")
    print(f"Variants: {len(config.variants)}")
    for variant in config.variants:
        print("")
        print(f"Variant: {variant.variant_id}")
        print(f"- description: {variant.description or 'none'}")
        print(f"- llm_config: {variant.llm_config}")
        print(f"- iterations: {variant.iterations}")
        print(f"- additional_context: {variant.additional_context or 'none'}")
    print("")
    print(f"Total planned iterations: {_total_iterations(config)}")
    if dry_run:
        print("")
        print("Dry run only: no LLM requests, candidates, materialization, or verification were run.")


def _validate_executable_pipeline(config: ExperimentConfig) -> str | None:
    pipeline = config.pipeline
    if not pipeline.generate_candidate:
        return "Experiment runner currently requires pipeline.generate_candidate=true."
    if pipeline.verify_candidate and not pipeline.materialize_candidate:
        return (
            "Experiment runner requires pipeline.materialize_candidate=true when "
            "pipeline.verify_candidate=true."
        )
    return None


def _build_generation_command(
    config: ExperimentConfig,
    variant: ExperimentVariantConfig,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "orchestrator.llm.generate_candidate",
        "--config",
        variant.llm_config,
        "--source",
        config.target_file,
        "--max-source-chars",
        str(config.candidate_generation.max_source_chars),
    ]
    if variant.additional_context is not None:
        command.extend(["--context", variant.additional_context])
    return command


def _build_materialization_command(candidate_run_dir: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "orchestrator.patching.materialize_candidate",
        "--candidate-run",
        candidate_run_dir,
        "--overwrite",
    ]


def _build_verification_command(candidate_run_dir: str) -> list[str]:
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
    return None


def _skipped_stage(reason: str) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": reason,
    }


def _candidate_field_summary(candidate_path: Path) -> dict[str, Any]:
    candidate = _read_json_object(candidate_path)
    return {
        "candidate_summary": candidate.get("summary"),
        "risk_level": candidate.get("risk_level"),
        "expected_effect": candidate.get("expected_effect"),
        "target_files": candidate.get("target_files"),
        "requires_manual_review": candidate.get("requires_manual_review"),
        "unified_diff_present": bool(candidate.get("unified_diff")),
    }


def _empty_generation_fields() -> dict[str, Any]:
    return {
        "candidate_summary": None,
        "risk_level": None,
        "expected_effect": None,
        "target_files": None,
        "requires_manual_review": None,
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
    return record


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
    return record


def _iteration_overall_status(record: dict[str, Any], config: ExperimentConfig) -> str:
    stages = [record["generation"]]
    if config.pipeline.materialize_candidate:
        stages.append(record["materialization"])
    if config.pipeline.verify_candidate:
        stages.append(record["verification"])

    if all(stage.get("status") == "success" for stage in stages):
        return "success"
    if any(stage.get("status") == "failed" for stage in stages):
        return "failed"
    return "failed"


def _append_iteration_record(iterations_path: Path, record: dict[str, Any]) -> None:
    with iterations_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def _run_iteration(
    config: ExperimentConfig,
    variant: ExperimentVariantConfig,
    experiment_dir: Path,
    global_iteration: int,
    variant_iteration: int,
) -> dict[str, Any]:
    print(f"\nVariant {variant.variant_id}, iteration {variant_iteration}/{variant.iterations}")

    generation_result = _run_stage(
        experiment_dir,
        global_iteration,
        variant.variant_id,
        variant_iteration,
        "generate_candidate",
        _build_generation_command(config, variant),
    )
    generation_record, candidate_run_dir = _generation_stage_record(generation_result)
    print(f"- generate_candidate: {generation_record['status']}")
    if candidate_run_dir:
        print(f"  candidate_run_dir: {candidate_run_dir}")

    if not config.pipeline.materialize_candidate:
        materialization_record = _skipped_stage("disabled_by_config")
    elif generation_record["status"] != "success" or candidate_run_dir is None:
        materialization_record = _skipped_stage("generation_failed")
    else:
        materialization_result = _run_stage(
            experiment_dir,
            global_iteration,
            variant.variant_id,
            variant_iteration,
            "materialize_candidate",
            _build_materialization_command(candidate_run_dir),
        )
        materialization_record = _materialization_stage_record(
            materialization_result,
            candidate_run_dir,
        )
    print(f"- materialize_candidate: {materialization_record['status']}")

    if not config.pipeline.verify_candidate:
        verification_record = _skipped_stage("disabled_by_config")
    elif generation_record["status"] != "success":
        verification_record = _skipped_stage("generation_failed")
    elif materialization_record["status"] != "success":
        reason = (
            "materialization_skipped"
            if materialization_record["status"] == "skipped"
            else "materialization_failed"
        )
        verification_record = _skipped_stage(reason)
    elif candidate_run_dir is None:
        verification_record = _skipped_stage("generation_failed")
    else:
        verification_result = _run_stage(
            experiment_dir,
            global_iteration,
            variant.variant_id,
            variant_iteration,
            "verify_candidate",
            _build_verification_command(candidate_run_dir),
        )
        verification_record = _verification_stage_record(
            verification_result,
            candidate_run_dir,
        )
    print(f"- verify_candidate: {verification_record['status']}")

    record = {
        "global_iteration": global_iteration,
        "variant_id": variant.variant_id,
        "variant_iteration": variant_iteration,
        "overall_status": "unknown",
        "candidate_run_dir": candidate_run_dir,
        "candidate_run_id": Path(candidate_run_dir).name if candidate_run_dir else None,
        "generation": generation_record,
        "materialization": materialization_record,
        "verification": verification_record,
    }
    record["overall_status"] = _iteration_overall_status(record, config)
    print(f"- iteration: {record['overall_status']}")
    return record


def _overall_status(records: list[dict[str, Any]]) -> str:
    successes = sum(1 for record in records if record["overall_status"] == "success")
    failures = sum(1 for record in records if record["overall_status"] == "failed")
    if successes and not failures:
        return "success"
    if successes and failures:
        return "partial_success"
    return "failed"


def _stage_success_count(records: list[dict[str, Any]], stage_name: str) -> int:
    return sum(
        1
        for record in records
        if record.get(stage_name, {}).get("status") == "success"
    )


def _failed_stage(record: dict[str, Any]) -> str | None:
    for stage_name in ["generation", "materialization", "verification"]:
        if record[stage_name].get("status") == "failed":
            return stage_name
    return None


def _failed_step(record: dict[str, Any]) -> str | None:
    stage_name = _failed_stage(record)
    if stage_name is None:
        return None
    return record[stage_name].get("failed_step")


def _error_message(record: dict[str, Any]) -> str | None:
    stage_name = _failed_stage(record)
    if stage_name is None:
        return None
    return record[stage_name].get("error_message")


def _variant_dir(experiment_dir: Path, variant_id: str) -> Path:
    return experiment_dir / "variants" / _sanitize_name(variant_id)


def _variant_history_path(experiment_dir: Path, variant_id: str) -> Path:
    return _variant_dir(experiment_dir, variant_id) / "variant_history.jsonl"


def _variant_summary_path(experiment_dir: Path, variant_id: str) -> Path:
    return _variant_dir(experiment_dir, variant_id) / "variant_summary.txt"


def _variant_record_history(record: dict[str, Any]) -> dict[str, Any]:
    generation = record["generation"]
    materialization = record["materialization"]
    verification = record["verification"]
    return {
        "variant_id": record["variant_id"],
        "variant_iteration": record["variant_iteration"],
        "global_iteration": record["global_iteration"],
        "overall_status": record["overall_status"],
        "candidate_run_id": record["candidate_run_id"],
        "candidate_run_dir": record["candidate_run_dir"],
        "candidate_summary": generation.get("candidate_summary"),
        "risk_level": generation.get("risk_level"),
        "expected_effect": generation.get("expected_effect"),
        "requires_manual_review": generation.get("requires_manual_review"),
        "unified_diff_present": generation.get("unified_diff_present"),
        "materialization_status": materialization.get("status"),
        "verification_status": verification.get("status"),
        "changed_files": materialization.get("changed_files"),
        "failed_stage": _failed_stage(record),
        "failed_step": _failed_step(record),
        "error_message": _error_message(record),
    }


def _variant_records(
    records: list[dict[str, Any]],
    variant: ExperimentVariantConfig,
) -> list[dict[str, Any]]:
    return [record for record in records if record["variant_id"] == variant.variant_id]


def _variant_stage_success_count(
    records: list[dict[str, Any]],
    stage_name: str,
) -> int:
    return sum(
        1
        for record in records
        if record.get(stage_name, {}).get("status") == "success"
    )


def _variant_summary(
    variant: ExperimentVariantConfig,
    records: list[dict[str, Any]],
    experiment_dir: Path,
) -> dict[str, Any]:
    variant_records = _variant_records(records, variant)
    successful_iterations = sum(
        1 for record in variant_records if record["overall_status"] == "success"
    )
    failed_iterations = sum(
        1 for record in variant_records if record["overall_status"] == "failed"
    )
    return {
        "variant_id": variant.variant_id,
        "planned_iterations": variant.iterations,
        "successful_iterations": successful_iterations,
        "failed_iterations": failed_iterations,
        "generation_successes": _variant_stage_success_count(
            variant_records, "generation"
        ),
        "materialization_successes": _variant_stage_success_count(
            variant_records, "materialization"
        ),
        "verification_successes": _variant_stage_success_count(
            variant_records, "verification"
        ),
        "history_file": _display_path(
            _variant_history_path(experiment_dir, variant.variant_id)
        ),
        "summary_file": _display_path(
            _variant_summary_path(experiment_dir, variant.variant_id)
        ),
    }


def _build_variant_summary_text(
    variant: ExperimentVariantConfig,
    records: list[dict[str, Any]],
    variant_summary: dict[str, Any],
) -> str:
    lines = [
        f"Variant id: {variant.variant_id}",
        f"Description: {variant.description or 'none'}",
        f"LLM config: {variant.llm_config}",
        f"Planned iterations: {variant_summary['planned_iterations']}",
        f"Successful iterations: {variant_summary['successful_iterations']}",
        f"Failed iterations: {variant_summary['failed_iterations']}",
        f"Generation successes: {variant_summary['generation_successes']}",
        f"Materialization successes: {variant_summary['materialization_successes']}",
        f"Verification successes: {variant_summary['verification_successes']}",
        "",
        "Iterations:",
    ]
    for record in records:
        generation = record["generation"]
        lines.extend(
            [
                (
                    f"- variant iteration {record['variant_iteration']} "
                    f"(global {record['global_iteration']}): "
                    f"{record['overall_status']}"
                ),
                f"  candidate summary: {generation.get('candidate_summary') or 'none'}",
                f"  risk level: {generation.get('risk_level') or 'none'}",
                f"  expected effect: {generation.get('expected_effect') or 'none'}",
                f"  materialization: {record['materialization'].get('status')}",
                f"  verification: {record['verification'].get('status')}",
                f"  failed stage: {_failed_stage(record) or 'none'}",
                f"  failed step: {_failed_step(record) or 'none'}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _write_variant_artifacts(
    experiment_dir: Path,
    config: ExperimentConfig,
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for variant in config.variants:
        variant_dir = _variant_dir(experiment_dir, variant.variant_id)
        variant_dir.mkdir(parents=True, exist_ok=True)
        records_for_variant = _variant_records(records, variant)
        history_path = _variant_history_path(experiment_dir, variant.variant_id)
        with history_path.open("w", encoding="utf-8") as file:
            for record in records_for_variant:
                file.write(
                    json.dumps(
                        _variant_record_history(record),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )

        summary = _variant_summary(variant, records, experiment_dir)
        _variant_summary_path(experiment_dir, variant.variant_id).write_text(
            _build_variant_summary_text(variant, records_for_variant, summary),
            encoding="utf-8",
        )
        summaries.append(summary)
    return summaries


def _build_experiment_status(
    experiment_id: str,
    config: ExperimentConfig,
    records: list[dict[str, Any]],
    variant_summaries: list[dict[str, Any]],
    started_at: datetime,
) -> dict[str, Any]:
    successful_iterations = sum(
        1 for record in records if record["overall_status"] == "success"
    )
    failed_iterations = sum(
        1 for record in records if record["overall_status"] == "failed"
    )
    return {
        "experiment_id": experiment_id,
        "experiment_name": config.experiment_name,
        "overall_status": _overall_status(records),
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "planned_iterations": _total_iterations(config),
        "successful_iterations": successful_iterations,
        "failed_iterations": failed_iterations,
        "generation_successes": _stage_success_count(records, "generation"),
        "materialization_successes": _stage_success_count(records, "materialization"),
        "verification_successes": _stage_success_count(records, "verification"),
        "llm_config": config.llm_config,
        "target_file": config.target_file,
        "pipeline": asdict(config.pipeline),
        "variants": variant_summaries,
    }


def _build_summary(
    experiment_id: str,
    config: ExperimentConfig,
    status: dict[str, Any],
    records: list[dict[str, Any]],
) -> str:
    lines = [
        f"Experiment id: {experiment_id}",
        f"Experiment name: {config.experiment_name}",
        f"Description: {config.description or 'none'}",
        f"Target file: {config.target_file}",
        "Pipeline flags:",
        f"- generate_candidate: {config.pipeline.generate_candidate}",
        f"- materialize_candidate: {config.pipeline.materialize_candidate}",
        f"- verify_candidate: {config.pipeline.verify_candidate}",
        f"Total planned iterations: {status['planned_iterations']}",
        f"Successful iterations: {status['successful_iterations']}",
        f"Failed iterations: {status['failed_iterations']}",
        f"Overall status: {status['overall_status']}",
        "",
        "Variants:",
    ]
    for variant_summary in status["variants"]:
        lines.extend(
            [
                f"- {variant_summary['variant_id']}:",
                f"  planned: {variant_summary['planned_iterations']}",
                f"  success: {variant_summary['successful_iterations']}",
                f"  failed: {variant_summary['failed_iterations']}",
            ]
        )
    lines.extend(["", "Variant history artifacts:"])
    for variant_summary in status["variants"]:
        lines.append(
            f"- {variant_summary['variant_id']}: {variant_summary['history_file']}"
        )
    lines.extend(["", "Iterations:"])
    for record in records:
        lines.extend(
            [
                (
                    f"- global {record['global_iteration']} "
                    f"variant {record['variant_id']} "
                    f"iteration {record['variant_iteration']}: "
                    f"{record['overall_status']}"
                ),
                f"  candidate_run_dir: {record.get('candidate_run_dir') or 'none'}",
                f"  generation: {record['generation']['status']}",
                f"  materialization: {record['materialization']['status']}",
                f"  verification: {record['verification']['status']}",
            ]
        )
    lines.extend(
        [
            "",
            "Benchmarking, comparison, and best candidate selection are not implemented yet.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_final_artifacts(
    experiment_dir: Path,
    experiment_id: str,
    config: ExperimentConfig,
    records: list[dict[str, Any]],
    started_at: datetime,
) -> dict[str, Any]:
    variant_summaries = _write_variant_artifacts(experiment_dir, config, records)
    status = _build_experiment_status(
        experiment_id,
        config,
        records,
        variant_summaries,
        started_at,
    )
    _write_json(experiment_dir / "experiment_status.json", status)
    (experiment_dir / "summary.txt").write_text(
        _build_summary(experiment_id, config, status, records),
        encoding="utf-8",
    )
    return status


def _run_experiment(config: ExperimentConfig) -> int:
    pipeline_error = _validate_executable_pipeline(config)
    if pipeline_error:
        print(f"ERROR: {pipeline_error}", file=sys.stderr)
        return 1

    started_at = datetime.now().astimezone()
    experiment_id = _build_experiment_id(config, started_at)
    try:
        experiment_dir = _create_experiment_dir(experiment_id)
    except OSError as exc:
        print(f"ERROR: Could not create experiment directory: {exc}", file=sys.stderr)
        return 1
    experiment_id = experiment_dir.name
    iterations_path = experiment_dir / "iterations.jsonl"

    _write_json(experiment_dir / "experiment_config_snapshot.json", asdict(config))

    print("Experiment execution")
    print(f"Experiment: {config.experiment_name}")
    print(f"Experiment id: {experiment_id}")
    print(f"Experiment directory: {_display_path(experiment_dir)}")
    print(f"Variants: {len(config.variants)}")
    print(f"Planned iterations: {_total_iterations(config)}")
    print(
        "Enabled stages: "
        f"generate={config.pipeline.generate_candidate}, "
        f"materialize={config.pipeline.materialize_candidate}, "
        f"verify={config.pipeline.verify_candidate}"
    )

    records: list[dict[str, Any]] = []
    global_iteration = 0
    for variant in config.variants:
        for variant_iteration in range(1, variant.iterations + 1):
            global_iteration += 1
            record = _run_iteration(
                config,
                variant,
                experiment_dir,
                global_iteration,
                variant_iteration,
            )
            records.append(record)
            _append_iteration_record(iterations_path, record)

    status = _write_final_artifacts(
        experiment_dir,
        experiment_id,
        config,
        records,
        started_at,
    )

    print("")
    print(f"Final experiment status: {status['overall_status']}")
    print(f"Successful iterations: {status['successful_iterations']}")
    print(f"Failed iterations: {status['failed_iterations']}")
    print(f"Artifacts saved to: {_display_path(experiment_dir)}")
    return 0 if status["overall_status"] in {"success", "partial_success"} else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config_path = _resolve_path(args.config)

    try:
        config = load_experiment_config(config_path)
    except ExperimentConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_plan(config, dry_run=True)
        return 0

    return _run_experiment(config)


if __name__ == "__main__":
    raise SystemExit(main())
