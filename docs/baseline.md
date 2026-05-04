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

## Baseline CLI Flow

The standard baseline CLI now configures CMake, builds the smoke test, runner, adapter validator, and family benchmark, then runs them in this order:

1. `baseline_smoke_test`
2. `baseline_runner`
3. `absolute_pose_lambdatwist_adapter_validator`
4. `absolute_pose_lambdatwist_benchmark`

The adapter validator runs before the family benchmark. If validation fails, the family benchmark is skipped.

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

## Not Implemented Yet

- Candidate benchmark execution and comparison against the baseline
- Best candidate selection and promotion into the main source tree
- Full reporting and experiment analysis