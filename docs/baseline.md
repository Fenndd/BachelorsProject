# Baseline State

## What Is Treated as Baseline

The current baseline is the imported Lambda Twist P3P solver wired into project-owned runner, adapter validation, and absolute-pose family benchmark entry points.

## Code Ownership and Locations

- External third-party baseline code: `cpp/external/lambdatwist/`
- New absolute-pose family benchmark: `cpp/bench/absolute_pose/`

The external Lambda Twist code remains third-party source and is kept separate from project-owned code.

## Established Targets

- `lambdatwist_baseline` (static library target)
- `absolute_pose_lambdatwist_adapter_validator` (adapter validation gate for Lambda Twist P3P)
- `absolute_pose_lambdatwist_benchmark` (new absolute-pose family benchmark executable)

## Baseline CLI Flow

The standard baseline CLI now configures CMake, builds the adapter validator and family benchmark, runs them, then parses the family benchmark output as an explicit internal step:

1. `absolute_pose_lambdatwist_adapter_validator`
2. `absolute_pose_lambdatwist_benchmark`
3. `parse_absolute_pose_lambdatwist_benchmark`
4. `benchmark_correctness_check`

The adapter validator runs before the family benchmark. If validation fails, the family benchmark run and parse steps are skipped. If the family benchmark build fails, `failed_step` remains `build_absolute_pose_lambdatwist_benchmark`. If the family benchmark run fails, `failed_step` remains `run_absolute_pose_lambdatwist_benchmark`. The parse step fails only when benchmark execution completed successfully but stdout could not be parsed into the required structured metrics.

Benchmark execution success alone is not sufficient for a valid baseline run. Parsed structured metrics are required for future baseline-vs-candidate comparison, so a parse failure makes the baseline CLI exit with code `1` and records `failed_step: "parse_absolute_pose_lambdatwist_benchmark"` in `status.json` and `index.jsonl`. `metrics.json` still preserves `parse_success`, `missing_fields`, `parse_errors`, and any partially parsed values for diagnosis. If parsing succeeds but `correctness_passed=false`, the baseline CLI exits with code `1`, records `failed_step: "benchmark_correctness_check"`, and still preserves all parsed benchmark metrics in `metrics.json`, `summary.txt`, and `index.jsonl`.

## Correctness Policy

The `correctness_passed` field in `run_absolute_pose_lambdatwist_benchmark` output is determined by the shared `correctness_policy_passed()` function in `absolute_pose_benchmark.cpp`. The benchmark executable returns `0` when it successfully produces metrics; it does not encode `correctness_passed` in the process exit code. The policy function enforces:

- `num_problems > 0`
- `gt_found_percent >= 99.0`
- `valid_solutions_percent > 0.0`
- `runtime_ns_per_problem_median > 0.0`

The `absolute_pose_lambdatwist_adapter_validator` runs the same PoseLib-style generated problem protocol on a smaller problem set, validates finite calibrated-pose solutions, and applies a validator-local correctness check that does not fake or require runtime.

The benchmark runner prints PoseLib-style solution counts, GT-found counts, calibrated-valid-solution counts, runtime medians, and options such as `num_problems`, `tolerance`, `camera_fov`, `n_point_point`, `n_point_line`, `timed_iterations`, and `runtime_unit`.

## Build Configuration

Baseline benchmarks default to **Release** builds for accurate runtime metrics. Debug builds are not suitable for performance comparisons.

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
