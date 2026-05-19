"""Single-run final benchmark comparison against original baseline for closed-loop experiments.

After all closed-loop iterations finish, this module runs the benchmark once on the
final optimized source and compares it against the original baseline metrics. It uses the
same benchmark protocol (absolute_pose_lambdatwist_benchmark) and the same
parser/audit/decision helpers as candidate verification, but runs only once with no
repetitions.

Build artifacts are written under workspace/ (mutable, git-ignored). The normalized
benchmark artifact (verification.json) and the final report are written under
results/experiments/<id>/final_selection/.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from orchestrator.benchmarking.candidate_decision import evaluate_candidate_against_baseline
from orchestrator.benchmarking.family_benchmark_parser import parse_absolute_pose_benchmark_output
from orchestrator.execution.candidate_benchmark_verification import (
    FAMILY_BENCHMARK_TARGET,
    _benchmark_from_parse,
    _build_command,
    _empty_benchmark,
    _find_executable,
    _run_command,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT / "workspace"

FINAL_SELECTION_DIR_NAME = "final_selection"
FINAL_BENCHMARK_RUN_DIR_NAME = "final_benchmark_run"
FINAL_SELECTION_REPORT_FILENAME = "final_selection_report.json"
_BUILD_DIR_NAME = "final_selection_build"


def run_final_selection_report(
    *,
    experiment_dir: Path,
    experiment_id: str,
    repo_root: Path,
    baseline_run_dir: Path,
    final_source_dir: Path,
    target_file: str,
    final_best_is_baseline: bool,
    build_type: str = "Release",
) -> Path:
    """Run a single final benchmark on the optimized source and compare against baseline.

    Returns the path to the written final_selection_report.json.
    """
    output_dir = experiment_dir / FINAL_SELECTION_DIR_NAME
    final_benchmark_run_dir = output_dir / FINAL_BENCHMARK_RUN_DIR_NAME
    logs_dir = output_dir / "logs"
    report_path = experiment_dir / FINAL_SELECTION_REPORT_FILENAME

    baseline_benchmark = _load_baseline_benchmark(baseline_run_dir)
    baseline_runtime = _runtime_ns(baseline_benchmark)

    if final_best_is_baseline:
        comparison = {
            "speedup": 1.0,
            "runtime_reduction_percent": 0.0,
            "baseline_runtime_ns_per_problem_median": baseline_runtime,
            "final_runtime_ns_per_problem_median": baseline_runtime,
            "candidate_runtime_lower": False,
        }
        report = _build_report(
            experiment_id=experiment_id,
            target_file=target_file,
            baseline_run_dir=baseline_run_dir,
            final_source_dir=final_source_dir,
            final_best_run_dir=None,
            final_best_is_baseline=True,
            baseline_benchmark=baseline_benchmark,
            final_benchmark=baseline_benchmark,
            decision_vs_original_baseline=None,
            comparison=comparison,
            status="skipped",
            failed_step=None,
            error_message=None,
            artifacts={
                "final_benchmark_run_dir": None,
                "final_benchmark_log": None,
                "final_benchmark_verification": None,
            },
            repo_root=repo_root,
        )
        _write_json(report_path, report)
        return report_path

    cmake_exe = os.environ.get("CMAKE_EXE", "cmake")
    cmake_generator = os.environ.get("CMAKE_GENERATOR")
    cmake_cxx_compiler = os.environ.get("CMAKE_CXX_COMPILER")
    cmake_make_program = os.environ.get("CMAKE_MAKE_PROGRAM")
    eigen_include_dir = os.environ.get("EIGEN3_INCLUDE_DIR")
    effective_build_type = os.environ.get(
        "BENCHMARK_CMAKE_BUILD_TYPE",
        os.environ.get("CMAKE_BUILD_TYPE", build_type),
    )

    if not eigen_include_dir:
        report = _build_report(
            experiment_id=experiment_id,
            target_file=target_file,
            baseline_run_dir=baseline_run_dir,
            final_source_dir=final_source_dir,
            final_best_run_dir=None,
            final_best_is_baseline=False,
            baseline_benchmark=baseline_benchmark,
            final_benchmark=_empty_benchmark(build_type=effective_build_type),
            decision_vs_original_baseline=None,
            comparison=_null_comparison(baseline_runtime),
            status="failed",
            failed_step="environment",
            error_message="EIGEN3_INCLUDE_DIR is not set.",
            artifacts={
                "final_benchmark_run_dir": None,
                "final_benchmark_log": None,
                "final_benchmark_verification": None,
            },
            repo_root=repo_root,
        )
        _write_json(report_path, report)
        return report_path

    source_cpp = final_source_dir / "cpp"
    build_dir = WORKSPACE_ROOT / "experiments" / experiment_id / _BUILD_DIR_NAME
    logs_dir.mkdir(parents=True, exist_ok=True)
    final_benchmark_run_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    configure_command: list[str] = [
        cmake_exe,
        "-S", str(source_cpp),
        "-B", str(build_dir),
        f"-DEIGEN3_INCLUDE_DIR={eigen_include_dir}",
    ]
    if cmake_generator:
        configure_command.extend(["-G", cmake_generator])
    if cmake_cxx_compiler:
        configure_command.append(f"-DCMAKE_CXX_COMPILER={cmake_cxx_compiler}")
    if cmake_make_program:
        configure_command.append(f"-DCMAKE_MAKE_PROGRAM={cmake_make_program}")
    configure_command.append(f"-DCMAKE_BUILD_TYPE={effective_build_type}")

    configure_log = logs_dir / "configure_cmake.log"
    _, configure_error, _ = _run_command(
        "configure_cmake",
        "Configure final source CMake project",
        configure_command,
        final_source_dir,
        configure_log,
    )
    if configure_error:
        report = _build_report(
            experiment_id=experiment_id,
            target_file=target_file,
            baseline_run_dir=baseline_run_dir,
            final_source_dir=final_source_dir,
            final_best_run_dir=None,
            final_best_is_baseline=False,
            baseline_benchmark=baseline_benchmark,
            final_benchmark=_empty_benchmark(build_type=effective_build_type),
            decision_vs_original_baseline=None,
            comparison=_null_comparison(baseline_runtime),
            status="failed",
            failed_step="configure_cmake",
            error_message=configure_error,
            artifacts={
                "final_benchmark_run_dir": _display_path(final_benchmark_run_dir, repo_root),
                "final_benchmark_log": None,
                "final_benchmark_verification": None,
            },
            repo_root=repo_root,
        )
        _write_json(report_path, report)
        return report_path

    build_log = logs_dir / "build_absolute_pose_lambdatwist_benchmark.log"
    build_cmd = _build_command(cmake_exe, build_dir, FAMILY_BENCHMARK_TARGET, effective_build_type)
    _, build_error, _ = _run_command(
        "build_absolute_pose_lambdatwist_benchmark",
        f"Build {FAMILY_BENCHMARK_TARGET}",
        build_cmd,
        build_dir.parent,
        build_log,
    )
    if build_error:
        report = _build_report(
            experiment_id=experiment_id,
            target_file=target_file,
            baseline_run_dir=baseline_run_dir,
            final_source_dir=final_source_dir,
            final_best_run_dir=None,
            final_best_is_baseline=False,
            baseline_benchmark=baseline_benchmark,
            final_benchmark=_empty_benchmark(build_type=effective_build_type),
            decision_vs_original_baseline=None,
            comparison=_null_comparison(baseline_runtime),
            status="failed",
            failed_step="build_absolute_pose_lambdatwist_benchmark",
            error_message=build_error,
            artifacts={
                "final_benchmark_run_dir": _display_path(final_benchmark_run_dir, repo_root),
                "final_benchmark_log": None,
                "final_benchmark_verification": None,
            },
            repo_root=repo_root,
        )
        _write_json(report_path, report)
        return report_path

    try:
        benchmark_exe = _find_executable(build_dir, FAMILY_BENCHMARK_TARGET)
    except FileNotFoundError as exc:
        report = _build_report(
            experiment_id=experiment_id,
            target_file=target_file,
            baseline_run_dir=baseline_run_dir,
            final_source_dir=final_source_dir,
            final_best_run_dir=None,
            final_best_is_baseline=False,
            baseline_benchmark=baseline_benchmark,
            final_benchmark=_empty_benchmark(build_type=effective_build_type),
            decision_vs_original_baseline=None,
            comparison=_null_comparison(baseline_runtime),
            status="failed",
            failed_step="find_executable",
            error_message=str(exc),
            artifacts={
                "final_benchmark_run_dir": _display_path(final_benchmark_run_dir, repo_root),
                "final_benchmark_log": None,
                "final_benchmark_verification": None,
            },
            repo_root=repo_root,
        )
        _write_json(report_path, report)
        return report_path

    benchmark_log_path = output_dir / "final_benchmark.log"
    run_log = logs_dir / "run_absolute_pose_lambdatwist_benchmark.log"
    _, run_error, stdout = _run_command(
        "run_absolute_pose_lambdatwist_benchmark",
        f"Run {FAMILY_BENCHMARK_TARGET}",
        [str(benchmark_exe)],
        build_dir,
        run_log,
    )
    benchmark_log_path.write_text(stdout or "", encoding="utf-8")

    if run_error:
        report = _build_report(
            experiment_id=experiment_id,
            target_file=target_file,
            baseline_run_dir=baseline_run_dir,
            final_source_dir=final_source_dir,
            final_best_run_dir=None,
            final_best_is_baseline=False,
            baseline_benchmark=baseline_benchmark,
            final_benchmark=_empty_benchmark(raw_output_available=False, build_type=effective_build_type),
            decision_vs_original_baseline=None,
            comparison=_null_comparison(baseline_runtime),
            status="failed",
            failed_step="run_absolute_pose_lambdatwist_benchmark",
            error_message=run_error,
            artifacts={
                "final_benchmark_run_dir": _display_path(final_benchmark_run_dir, repo_root),
                "final_benchmark_log": _display_path(benchmark_log_path, repo_root),
                "final_benchmark_verification": None,
            },
            repo_root=repo_root,
        )
        _write_json(report_path, report)
        return report_path

    parse_result = parse_absolute_pose_benchmark_output(stdout)
    final_benchmark = _benchmark_from_parse(stdout, parse_result, effective_build_type)

    verification = {
        "overall_status": "success" if parse_result["parse_success"] else "failed",
        "failed_step": None if parse_result["parse_success"] else "parse_benchmark_output",
        "error_message": (
            None if parse_result["parse_success"]
            else f"Benchmark output parse failed: missing={parse_result['missing_fields']}"
        ),
        "candidate_run_id": f"final_selection_{experiment_id}",
        "source_dir": _display_path(source_cpp, repo_root),
        "build_dir": _display_path(build_dir, repo_root),
        "benchmark": final_benchmark,
    }
    verification_path = final_benchmark_run_dir / "verification.json"
    _write_json(verification_path, verification)

    decision: dict[str, Any] | None = None
    failed_step: str | None = None
    error_message: str | None = None
    status = "completed"

    if not parse_result["parse_success"]:
        failed_step = "parse_benchmark_output"
        error_message = f"Benchmark output parse failed: missing={parse_result['missing_fields']}"
        status = "failed"
    else:
        try:
            decision = evaluate_candidate_against_baseline(baseline_run_dir, final_benchmark_run_dir)
        except Exception as exc:
            failed_step = "decision_vs_original_baseline"
            error_message = str(exc)
            status = "failed"

    comp = (decision or {}).get("comparison", {})
    final_runtime = _runtime_ns(final_benchmark)
    comparison = {
        "speedup": comp.get("speedup"),
        "runtime_reduction_percent": comp.get("runtime_reduction_percent"),
        "baseline_runtime_ns_per_problem_median": baseline_runtime,
        "final_runtime_ns_per_problem_median": final_runtime,
        "candidate_runtime_lower": comp.get("candidate_runtime_lower", False),
    }

    report = _build_report(
        experiment_id=experiment_id,
        target_file=target_file,
        baseline_run_dir=baseline_run_dir,
        final_source_dir=final_source_dir,
        final_best_run_dir=final_benchmark_run_dir,
        final_best_is_baseline=False,
        baseline_benchmark=baseline_benchmark,
        final_benchmark=final_benchmark,
        decision_vs_original_baseline=decision,
        comparison=comparison,
        status=status,
        failed_step=failed_step,
        error_message=error_message,
        artifacts={
            "final_benchmark_run_dir": _display_path(final_benchmark_run_dir, repo_root),
            "final_benchmark_log": _display_path(benchmark_log_path, repo_root),
            "final_benchmark_verification": _display_path(verification_path, repo_root),
        },
        repo_root=repo_root,
    )
    _write_json(report_path, report)
    return report_path


def _load_baseline_benchmark(baseline_run_dir: Path) -> dict[str, Any]:
    metrics_path = baseline_run_dir / "metrics.json"
    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return _empty_benchmark()
    if not isinstance(payload, dict):
        return _empty_benchmark()
    benchmark = payload.get("benchmark")
    return benchmark if isinstance(benchmark, dict) else _empty_benchmark()


def _runtime_ns(benchmark: dict[str, Any]) -> float | None:
    value = benchmark.get("parsed_runtime_ns_per_problem_median")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _null_comparison(baseline_runtime: float | None) -> dict[str, Any]:
    return {
        "speedup": None,
        "runtime_reduction_percent": None,
        "baseline_runtime_ns_per_problem_median": baseline_runtime,
        "final_runtime_ns_per_problem_median": None,
        "candidate_runtime_lower": False,
    }


def _build_report(
    *,
    experiment_id: str,
    target_file: str,
    baseline_run_dir: Path,
    final_source_dir: Path,
    final_best_run_dir: Path | None,
    final_best_is_baseline: bool,
    baseline_benchmark: dict[str, Any],
    final_benchmark: dict[str, Any],
    decision_vs_original_baseline: dict[str, Any] | None,
    comparison: dict[str, Any],
    status: str,
    failed_step: str | None,
    error_message: str | None,
    artifacts: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "report_type": "single_run_final_selection_report",
        "experiment_id": experiment_id,
        "target_file": target_file,
        "mode": "closed_loop",
        "metric_source": "single_run_final_best_vs_original_baseline",
        "baseline_run_dir": _display_path(baseline_run_dir, repo_root),
        "final_source_dir": _display_path(final_source_dir, repo_root),
        "final_best_run_dir": _display_path(final_best_run_dir, repo_root) if final_best_run_dir else None,
        "final_best_is_baseline": final_best_is_baseline,
        "baseline_benchmark": baseline_benchmark,
        "final_benchmark": final_benchmark,
        "decision_vs_original_baseline": decision_vs_original_baseline,
        "comparison": comparison,
        "status": status,
        "failed_step": failed_step,
        "error_message": error_message,
        "artifacts": artifacts,
    }


def _display_path(path: Path, repo_root: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        pass
    try:
        return (Path("workspace") / path.resolve().relative_to(WORKSPACE_ROOT.resolve())).as_posix()
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
