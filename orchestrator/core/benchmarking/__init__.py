"""Benchmark parsing, artifact, runner, and solver registry helpers."""

from .benchmark_artifact_audit import (
    audit_comparable_benchmark_artifacts,
    audit_comparable_benchmark_pair,
    audit_single_benchmark_artifact,
    load_baseline_benchmark_artifact,
    load_candidate_benchmark_artifact,
    load_reference_benchmark_artifact,
    load_verified_candidate_benchmark_artifact,
)
from .benchmark_artifacts import (
    benchmark_artifact_from_parse,
    benchmark_artifact_from_repeated_samples,
    benchmark_required_fields,
    build_benchmark_correctness_error_message,
    empty_benchmark_artifact,
)
from .repeated_benchmark import (
    DEFAULT_REPEATED_BENCHMARK_RUN_COUNT,
    DECISION_METRIC,
    merge_repeated_benchmark_artifacts,
    run_repeated_benchmark,
)
from .benchmark_runner import (
    build_benchmark_run_command,
    build_cmake_build_command,
    configure_cmake_command,
    find_executable,
    format_command,
    run_command,
    write_step_log,
)
from .candidate_decision import (
    CandidateDecisionThresholds,
    evaluate_candidate_against_baseline,
    evaluate_candidate_against_reference,
    write_candidate_decision,
)
from .family_benchmark_parser import parse_poselib_native_benchmark_output
from .solver_registry import (
    SolverBenchmarkDescriptor,
    default_solver_descriptor,
    get_solver_descriptor,
    list_solver_descriptors,
)

__all__ = [
    "audit_comparable_benchmark_pair",
    "audit_comparable_benchmark_artifacts",
    "audit_single_benchmark_artifact",
    "benchmark_artifact_from_parse",
    "benchmark_artifact_from_repeated_samples",
    "benchmark_required_fields",
    "build_benchmark_correctness_error_message",
    "build_benchmark_run_command",
    "build_cmake_build_command",
    "CandidateDecisionThresholds",
    "configure_cmake_command",
    "DECISION_METRIC",
    "DEFAULT_REPEATED_BENCHMARK_RUN_COUNT",
    "default_solver_descriptor",
    "empty_benchmark_artifact",
    "evaluate_candidate_against_baseline",
    "evaluate_candidate_against_reference",
    "find_executable",
    "format_command",
    "get_solver_descriptor",
    "list_solver_descriptors",
    "load_baseline_benchmark_artifact",
    "load_candidate_benchmark_artifact",
    "load_reference_benchmark_artifact",
    "load_verified_candidate_benchmark_artifact",
    "merge_repeated_benchmark_artifacts",
    "parse_poselib_native_benchmark_output",
    "run_command",
    "run_repeated_benchmark",
    "SolverBenchmarkDescriptor",
    "write_candidate_decision",
    "write_step_log",
]
