# Baseline State

## What Is Treated as Baseline

The current baseline is the imported Lambda Twist P3P solver wired into project-owned smoke, runner, adapter validation, and absolute-pose family benchmark entry points.

## Code Ownership and Locations

- External third-party baseline code: `cpp/external/lambdatwist/`
- Project-owned runnable baseline entry point: `cpp/src/baseline_runner.cpp`
- Project-owned minimal smoke test: `cpp/tests/baseline_smoke_test.cpp`
- Old compatibility benchmark: `cpp/bench/baseline_benchmark.cpp`
- New absolute-pose family benchmark: `cpp/bench/families/geometric_pose_solvers/absolute_pose_solvers/`
- Project-owned shared fixed input case: `cpp/include/baseline_sample_data.h` and `cpp/src/baseline_sample_data.cpp`

The external Lambda Twist code remains third-party source and is kept separate from project-owned code.

## Established Targets

- `lambdatwist_baseline` (static library target)
- `baseline_runner` (project-owned executable target linked against `lambdatwist_baseline`)
- `baseline_smoke_test` (project-owned smoke test executable linked against `lambdatwist_baseline`)
- `baseline_benchmark` (old minimal benchmark target; kept building for compatibility)
- `absolute_pose_lambdatwist_adapter_validator` (adapter validation gate for Lambda Twist P3P)
- `absolute_pose_lambdatwist_benchmark` (new absolute-pose family benchmark executable)
- `absolute_pose_correctness_policy_test` (unit test for `correctness_policy_passed` helper)

## Baseline CLI Flow

The standard baseline CLI now configures CMake, builds the smoke test, runner, adapter validator, and family benchmark, runs them, then parses the family benchmark output as an explicit internal step:

1. `baseline_smoke_test`
2. `baseline_runner`
3. `absolute_pose_lambdatwist_adapter_validator`
4. `absolute_pose_lambdatwist_benchmark`
5. `parse_absolute_pose_lambdatwist_benchmark`
6. `benchmark_correctness_check`

The adapter validator runs before the family benchmark. If validation fails, the family benchmark run and parse steps are skipped. If the family benchmark build fails, `failed_step` remains `build_absolute_pose_lambdatwist_benchmark`. If the family benchmark run fails, `failed_step` remains `run_absolute_pose_lambdatwist_benchmark`. The parse step fails only when benchmark execution completed successfully but stdout could not be parsed into the required structured metrics.

Benchmark execution success alone is not sufficient for a valid baseline run. Parsed structured metrics are required for future baseline-vs-candidate comparison, so a parse failure makes the baseline CLI exit with code `1` and records `failed_step: "parse_absolute_pose_lambdatwist_benchmark"` in `status.json` and `index.jsonl`. `metrics.json` still preserves `parse_success`, `missing_fields`, `parse_errors`, and any partially parsed values for diagnosis. If parsing succeeds but `correctness_passed=false`, the baseline CLI exits with code `1`, records `failed_step: "benchmark_correctness_check"`, and still preserves all parsed benchmark metrics in `metrics.json`, `summary.txt`, and `index.jsonl`.

## Correctness Policy

The `correctness_passed` field in `run_absolute_pose_lambdatwist_benchmark` output is determined by the shared `correctness_policy_passed()` function in `absolute_pose_types.hpp` / `absolute_pose_benchmark.cpp`. The benchmark executable returns `0` when it successfully produces metrics; it does not encode `correctness_passed` in the process exit code. The policy function enforces:

- `success_rate >= options.min_success_rate` (default: 0.99)
- `mean_best_reprojection_error <= options.reprojection_error_threshold` (default: 1e-6)
- Optionally: `valid_cases == num_cases` (when `require_all_cases_valid` is true)
- Optionally: `max_best_reprojection_error <= options.reprojection_error_threshold` (when `use_max_reprojection_error_as_hard_gate` is true)

The `absolute_pose_lambdatwist_adapter_validator` uses the same shared function for its `reprojection_check_passed` gate, ensuring consistent correctness semantics between adapter validation and family benchmark evaluation.

Policy-diagnostic lines (`min_success_rate`, `require_all_cases_valid`, `use_max_reprojection_error_as_hard_gate`, `reprojection_error_threshold`, `correctness_passed`) and additional metadata (`warmup_iterations`, `timed_iterations`, `random_seed`, `points_per_case`, `runtime_unit`, `valid_cases`, `total_solutions`) are printed by the benchmark runner for traceability. The Python parser reads all of these as optional fields, stores them in parsed metrics, and collects them into the `benchmark_options` block for artifact reproducibility.

## Build Configuration

Baseline benchmarks and smoke tests default to **Release** builds for accurate runtime metrics. Debug builds are not suitable for performance comparisons.

The build type is controlled by the `CMAKE_BUILD_TYPE` environment variable:
- Default: `Release` (optimized)
- Override: set `CMAKE_BUILD_TYPE=Debug` for debugging

On Windows PowerShell:
```powershell
$env:CMAKE_BUILD_TYPE="Debug"
py -m orchestrator.cli.main
```

On Unix:
```bash
export CMAKE_BUILD_TYPE=Debug
python -m orchestrator.cli.main
```

The selected build type:
- Is passed to CMake configure as `-DCMAKE_BUILD_TYPE=<value>`
- Is passed to cmake --build as `--config <value>`
- Is recorded in `metadata.json` (environment section) and `metrics.json` (benchmark section)
- Appears in `summary.txt` for traceability

Baseline and candidate benchmarks should only be compared when built with the same build type. The benchmark artifact audit enforces this check.

## Relation to Candidate Pipeline

Baseline `metrics.json` is the reference artifact used by `benchmark_artifact_audit`, pairwise candidate decision, and best-candidate selection.

Candidate verification produces `verification.json` using the same absolute-pose benchmark family. Selection compares verified candidates against an explicit `selection.baseline_run_dir` from experiment config. The baseline itself remains clean and separate from candidate workspaces.

## Not Implemented Yet

- Candidate promotion into the main source tree
- Full reporting and experiment analysis
- Additional baseline solver adapters