"""Final repeated benchmark validation for closed-loop experiments.

This module is final-evaluation only. It creates isolated candidate-like run
directories and reuses the existing verifier entry point without changing
promotion decisions, current_best_source, or the main cpp/ tree.
"""

from __future__ import annotations

import fnmatch
import json
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence


SOURCE_TREE_IGNORE_NAMES = {
    "build",
    "build-codex",
    "build-pre-step-11-cleanup",
    "cmake-build-debug",
    "cmake-build-release",
    "CMakeFiles",
    "Testing",
}
SOURCE_TREE_IGNORE_PATTERNS = {
    "CMakeCache.txt",
    "build.ninja",
    ".ninja_*",
    "*.exe",
    "*.dll",
    "*.lib",
    "*.a",
    "*.obj",
    "*.o",
    "*.pdb",
    "*.ilk",
}


CommandRunner = Callable[[Sequence[str], Path], dict[str, Any]]


def run_final_validation(
    *,
    experiment_dir: Path,
    experiment_id: str,
    repo_root: Path,
    baseline_source_dir: Path,
    final_source_dir: Path,
    enabled: bool = True,
    benchmark_repetitions: int = 5,
    command_runner: CommandRunner | None = None,
) -> Path:
    """Run repeated final validation and write final_validation_report.json."""

    if benchmark_repetitions <= 0:
        raise ValueError("benchmark_repetitions must be a positive integer")

    validation_dir = experiment_dir / "final_validation"
    report_path = validation_dir / "final_validation_report.json"
    validation_dir.mkdir(parents=True, exist_ok=True)
    started_at = _now_iso()

    if not enabled:
        payload = {
            "schema_version": "final_validation.v1",
            "enabled": False,
            "status": "skipped",
            "benchmark_repetitions": benchmark_repetitions,
            "started_at": started_at,
            "finished_at": _now_iso(),
            "baseline": _empty_group(baseline_source_dir),
            "final": _empty_group(final_source_dir),
            "comparison": _empty_comparison(),
            "safety": _safety_block(),
        }
        _write_json(report_path, payload)
        return report_path

    runner = command_runner or _run_verifier_command
    baseline_runs = _run_group(
        validation_dir=validation_dir,
        group_name="baseline",
        source_dir=baseline_source_dir,
        repetitions=benchmark_repetitions,
        repo_root=repo_root,
        runner=runner,
    )
    final_runs = _run_group(
        validation_dir=validation_dir,
        group_name="final",
        source_dir=final_source_dir,
        repetitions=benchmark_repetitions,
        repo_root=repo_root,
        runner=runner,
    )

    baseline_summary = _summarize_runs(baseline_runs)
    final_summary = _summarize_runs(final_runs)
    comparison = _comparison(baseline_summary, final_summary)
    payload = {
        "schema_version": "final_validation.v1",
        "enabled": True,
        "status": _validation_status(
            baseline_summary,
            final_summary,
            comparison,
            benchmark_repetitions,
        ),
        "benchmark_repetitions": benchmark_repetitions,
        "started_at": started_at,
        "finished_at": _now_iso(),
        "baseline": {
            "source_dir": _display_path(baseline_source_dir, repo_root),
            "runs": baseline_runs,
            "summary": baseline_summary,
        },
        "final": {
            "source_dir": _display_path(final_source_dir, repo_root),
            "runs": final_runs,
            "summary": final_summary,
        },
        "comparison": comparison,
        "safety": _safety_block(),
        "statistics_note": "Runtime standard deviation uses population std (statistics.pstdev).",
    }
    _write_json(report_path, payload)
    return report_path


def _run_group(
    *,
    validation_dir: Path,
    group_name: str,
    source_dir: Path,
    repetitions: int,
    repo_root: Path,
    runner: CommandRunner,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    parent = validation_dir / f"{group_name}_runs"
    parent.mkdir(parents=True, exist_ok=True)
    for index in range(1, repetitions + 1):
        run_dir = parent / f"run_{index:02d}"
        candidate_run_id = f"final_validation_{group_name}_{index:02d}"
        workspace_path = run_dir / "workspace"
        try:
            _prepare_run_dir(run_dir, workspace_path, source_dir, candidate_run_id, repo_root)
            command = _verification_command(run_dir)
            stage = runner(command, repo_root)
        except Exception as exc:  # keep collecting repetitions if one setup/run fails
            stage = {
                "exit_code": None,
                "duration_seconds": None,
                "error_message": str(exc),
            }
        runs.append(_extract_run(index, candidate_run_id, run_dir, stage, repo_root))
    return runs


def _prepare_run_dir(
    run_dir: Path,
    workspace_path: Path,
    source_dir: Path,
    candidate_run_id: str,
    repo_root: Path,
) -> None:
    if run_dir.exists():
        shutil.rmtree(run_dir)
    workspace_cpp = workspace_path / "cpp"
    workspace_cpp.parent.mkdir(parents=True, exist_ok=True)
    _copy_source_tree(source_dir / "cpp", workspace_cpp)
    _write_json(
        run_dir / "materialization.json",
        {
            "overall_status": "success",
            "candidate_run_id": candidate_run_id,
            "workspace_path": _display_path(workspace_path, repo_root),
            "source_dir": _display_path(workspace_cpp, repo_root),
            "changed_files": [],
        },
    )


def _copy_source_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Source cpp directory not found: {source}")
    shutil.copytree(source, destination, ignore=_source_tree_ignore)


def _source_tree_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in SOURCE_TREE_IGNORE_NAMES:
            ignored.add(name)
        elif any(fnmatch.fnmatch(name, pattern) for pattern in SOURCE_TREE_IGNORE_PATTERNS):
            ignored.add(name)
    return ignored


def _verification_command(run_dir: Path) -> list[str]:
    return [sys.executable, "-m", "orchestrator.execution.verify_candidate", "--candidate-run", str(run_dir)]


def _run_verifier_command(command: Sequence[str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    except OSError as exc:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "error_message": str(exc),
        }


def _extract_run(
    run_index: int,
    candidate_run_id: str,
    run_dir: Path,
    stage: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    verification = _safe_read_json(run_dir / "verification.json") or {}
    benchmark_value = verification.get("benchmark")
    benchmark = benchmark_value if isinstance(benchmark_value, dict) else {}
    steps = verification.get("steps") if isinstance(verification.get("steps"), list) else []
    failed_step = _string_or_none(verification.get("failed_step"))
    error_message = _string_or_none(verification.get("error_message"))
    if error_message is None:
        error_message = _string_or_none(stage.get("error_message")) or _string_or_none(stage.get("stderr"))
    return {
        "run_index": run_index,
        "candidate_run_id": _string_or_none(verification.get("candidate_run_id")) or candidate_run_id,
        "validation_run_id": candidate_run_id,
        "run_dir": _display_path(run_dir, repo_root),
        "verification_status": _string_or_none(verification.get("overall_status")) or "failed",
        "correctness_passed": _bool_or_none(_first_value(benchmark, verification, "parsed_correctness_passed", "correctness_passed")),
        "runtime_ns_per_case_median": _number_or_none(_first_value(benchmark, verification, "parsed_runtime_ns_per_case_median", "runtime_ns_per_case_median")),
        "success_rate": _number_or_none(_first_value(benchmark, verification, "parsed_success_rate", "success_rate")),
        "mean_best_reprojection_error": _number_or_none(_first_value(benchmark, verification, "parsed_mean_best_reprojection_error", "mean_best_reprojection_error")),
        "max_best_reprojection_error": _number_or_none(_first_value(benchmark, verification, "parsed_max_best_reprojection_error", "max_best_reprojection_error")),
        "total_solutions": _int_or_none(_first_value(benchmark, verification, "parsed_total_solutions", "total_solutions")),
        "valid_cases": _int_or_none(_first_value(benchmark, verification, "parsed_valid_cases", "valid_cases")),
        "verification_duration_seconds": _verification_duration(steps, stage),
        "failed_step": failed_step,
        "error_message": error_message,
    }


def _summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    correct = [
        run for run in runs
        if run.get("verification_status") == "success"
        and run.get("correctness_passed") is True
        and isinstance(run.get("runtime_ns_per_case_median"), (int, float))
        and not isinstance(run.get("runtime_ns_per_case_median"), bool)
    ]
    runtimes = [float(run["runtime_ns_per_case_median"]) for run in correct]
    success_rates = [
        float(run["success_rate"])
        for run in correct
        if isinstance(run.get("success_rate"), (int, float)) and not isinstance(run.get("success_rate"), bool)
    ]
    return {
        "successful_runs": len(correct),
        "failed_runs": len(runs) - len(correct),
        "median_runtime_ns_per_case": statistics.median(runtimes) if runtimes else None,
        "mean_runtime_ns_per_case": statistics.fmean(runtimes) if runtimes else None,
        "min_runtime_ns_per_case": min(runtimes) if runtimes else None,
        "max_runtime_ns_per_case": max(runtimes) if runtimes else None,
        "std_runtime_ns_per_case": statistics.pstdev(runtimes) if len(runtimes) > 1 else (0.0 if runtimes else None),
        "all_correctness_passed": bool(runs) and all(run.get("correctness_passed") is True for run in runs),
        "success_rate_min": min(success_rates) if success_rates else None,
        "success_rate_mean": statistics.fmean(success_rates) if success_rates else None,
    }


def _comparison(baseline: dict[str, Any], final: dict[str, Any]) -> dict[str, Any]:
    baseline_median = _number_or_none(baseline.get("median_runtime_ns_per_case"))
    final_median = _number_or_none(final.get("median_runtime_ns_per_case"))
    baseline_mean = _number_or_none(baseline.get("mean_runtime_ns_per_case"))
    final_mean = _number_or_none(final.get("mean_runtime_ns_per_case"))
    return {
        "median_speedup": _speedup(baseline_median, final_median),
        "median_runtime_reduction_percent": _reduction_percent(baseline_median, final_median),
        "mean_speedup": _speedup(baseline_mean, final_mean),
        "mean_runtime_reduction_percent": _reduction_percent(baseline_mean, final_mean),
        "baseline_reference": "original_baseline",
        "final_reference": "final_optimized_source",
    }


def _validation_status(
    baseline_summary: dict[str, Any],
    final_summary: dict[str, Any],
    comparison: dict[str, Any],
    repetitions: int,
) -> str:
    baseline_successful = _int_or_zero(baseline_summary.get("successful_runs"))
    final_successful = _int_or_zero(final_summary.get("successful_runs"))
    baseline_failed = _int_or_zero(baseline_summary.get("failed_runs"))
    final_failed = _int_or_zero(final_summary.get("failed_runs"))
    if comparison.get("median_speedup") is None:
        return "incomplete"
    if (
        baseline_failed == 0
        and final_failed == 0
        and baseline_successful == repetitions
        and final_successful == repetitions
    ):
        return "completed"
    return "completed_partial"


def _empty_group(source_dir: Path) -> dict[str, Any]:
    return {"source_dir": str(source_dir), "runs": [], "summary": _summarize_runs([])}


def _empty_comparison() -> dict[str, Any]:
    return {
        "median_speedup": None,
        "median_runtime_reduction_percent": None,
        "mean_speedup": None,
        "mean_runtime_reduction_percent": None,
        "baseline_reference": "original_baseline",
        "final_reference": "final_optimized_source",
    }


def _safety_block() -> dict[str, bool]:
    return {
        "updates_current_best": False,
        "changes_promotion_decision": False,
        "modifies_main_cpp_tree": False,
    }


def _speedup(baseline: float | None, final: float | None) -> float | None:
    if baseline is None or final is None or final == 0:
        return None
    return baseline / final


def _reduction_percent(baseline: float | None, final: float | None) -> float | None:
    if baseline is None or final is None or baseline == 0:
        return None
    return ((baseline - final) / baseline) * 100.0


def _verification_duration(steps: Any, stage: dict[str, Any]) -> float | None:
    if isinstance(steps, list):
        durations = [
            float(step["duration_seconds"])
            for step in steps
            if isinstance(step, dict)
            and isinstance(step.get("duration_seconds"), (int, float))
            and not isinstance(step.get("duration_seconds"), bool)
        ]
        if durations:
            return sum(durations)
    return _number_or_none(stage.get("duration_seconds"))


def _first_value(first: dict[str, Any], second: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in first:
            return first.get(key)
        if key in second:
            return second.get(key)
    return None


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


__all__ = ["run_final_validation"]
