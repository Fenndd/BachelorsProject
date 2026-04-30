# Baseline State

## What Is Treated as Baseline

The current baseline is the imported Lambda Twist P3P solver wired into the project build with a minimal project-owned runnable entry point.

## Baseline Code Ownership and Locations

- External third-party baseline code: `cpp/external/lambdatwist/`
- Project-owned runnable baseline entry point: `cpp/src/baseline_runner.cpp`
- Project-owned minimal smoke test: `cpp/tests/baseline_smoke_test.cpp`
- Project-owned minimal benchmark: `cpp/bench/baseline_benchmark.cpp`
- Project-owned shared fixed input case: `cpp/include/baseline_sample_data.h` and `cpp/src/baseline_sample_data.cpp`

The external Lambda Twist code remains third-party source and is kept separate from project-owned code.

## Established Baseline Targets

- `lambdatwist_baseline` (static library target)
- `baseline_runner` (project-owned executable target linked against `lambdatwist_baseline`)
- `baseline_smoke_test` (project-owned smoke test executable linked against `lambdatwist_baseline`)
- `baseline_benchmark` (project-owned benchmark executable linked against `lambdatwist_baseline`)

## Verified in Current Baseline Step

- CMake integration of the imported baseline target
- Successful build of the baseline targets
- Shared fixed input case used by the runner, smoke test, and benchmark
- Minimal smoke test that checks Lambda Twist returns at least one solution for a fixed input
- Successful basic run of `baseline_runner`
- Minimal benchmark that measures repeated Lambda Twist calls on a fixed input

## Not Implemented Yet

- Full validation tests
- Advanced benchmark framework
- Result storage and reporting
- Full experiment orchestration runtime behavior
- LLM-driven optimization logic

## Role of This State

This baseline state is the reference point for future optimization comparisons.
