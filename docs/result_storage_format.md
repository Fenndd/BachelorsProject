# Result Storage Format

## Purpose

The `results/` directory stores persistent outputs produced by baseline, candidate, and experiment runs. Each baseline CLI run writes one detailed run directory under `results/runs/<run_id>/` and appends one compact record to `results/index.jsonl`.

## Baseline Run

For the current baseline phase, a run configures CMake, builds the baseline smoke test, baseline runner, Lambda Twist P3P adapter validator, and absolute-pose family benchmark, then runs them in this order:

1. `baseline_smoke_test`
2. `baseline_runner`
3. `absolute_pose_lambdatwist_adapter_validator`
4. `absolute_pose_lambdatwist_benchmark`

The old `baseline_benchmark` target remains in CMake for compatibility, but the main baseline CLI now uses the family benchmark flow. If adapter validation fails, the family benchmark run step is skipped.

## Directory Layout

```text
results/
├─ index.jsonl
└─ runs/
   └─ <run_id>/
      ├─ metadata.json
      ├─ status.json
      ├─ metrics.json
      ├─ logs/
      │  ├─ configure_cmake.log
      │  ├─ build_baseline_smoke_test.log
      │  ├─ build_baseline_runner.log
      │  ├─ build_absolute_pose_lambdatwist_adapter_validator.log
      │  ├─ build_absolute_pose_lambdatwist_benchmark.log
      │  ├─ run_baseline_smoke_test.log
      │  ├─ run_baseline_runner.log
      │  ├─ run_absolute_pose_lambdatwist_adapter_validator.log
      │  └─ run_absolute_pose_lambdatwist_benchmark.log
      └─ summary.txt
```

## `status.json`

`status.json` records overall success, failed step, error message, and all expected steps. Step statuses are `success`, `failed`, or `skipped`; if one step fails, later unexecuted steps are marked `skipped`.

Expected baseline steps are:

- `configure_cmake`
- `build_baseline_smoke_test`
- `build_baseline_runner`
- `build_absolute_pose_lambdatwist_adapter_validator`
- `build_absolute_pose_lambdatwist_benchmark`
- `run_baseline_smoke_test`
- `run_baseline_runner`
- `run_absolute_pose_lambdatwist_adapter_validator`
- `run_absolute_pose_lambdatwist_benchmark`

## `metrics.json`

Baseline metrics contain success flags and parsed family benchmark values. The parser reads stable snake_case key-value lines from the family benchmark stdout log. A benchmark execution failure still fails the baseline run; a parse failure is recorded with `parse_success: false`, missing fields, and parse errors so it is visible without introducing Step 11 comparison gates yet.

```json
{
  "build_success": true,
  "smoke_test_success": true,
  "runner_success": true,
  "adapter_validation_success": true,
  "family_benchmark_success": true,
  "benchmark_success": true,
  "benchmark": {
    "family": "absolute_pose_solvers",
    "solver": "lambdatwist_p3p",
    "runtime_unit": "ns",
    "build_type": "Release",
    "raw_output_available": true,
    "parse_success": true,
    "missing_fields": [],
    "parse_errors": [],
    "parsed_solver_name": "lambdatwist_p3p",
    "parsed_num_cases": 1000,
    "parsed_success_rate": 1.0,
    "parsed_mean_best_reprojection_error": 7.63e-14,
    "parsed_max_best_reprojection_error": 1.1e-12,
    "parsed_runtime_ns_total_median": 32928700.0,
    "parsed_runtime_ns_per_case_median": 32928.7,
    "parsed_correctness_passed": true
  },
  "correctness": {
    "basic_smoke_test_passed": true,
    "adapter_validation_passed": true
  }
}
```

## `index.jsonl`

`results/index.jsonl` is a compact append-only JSON Lines index. Baseline records include run identity, repository state, success flags, and compact parsed family benchmark values:

```json
{"run_id":"2026-05-01_23-40-12_baseline","scenario":"baseline","case_study":"p3p_solver","baseline":"lambda_twist","overall_status":"success","failed_step":null,"started_at":"2026-05-01T23:40:12+02:00","finished_at":"2026-05-01T23:41:03+02:00","git_commit":"abc1234","git_branch":"main","dirty_worktree":false,"build_success":true,"smoke_test_success":true,"runner_success":true,"benchmark_success":true,"adapter_validation_success":true,"family_benchmark_success":true,"benchmark_raw_output_available":true,"benchmark_runtime_ms":null,"family_benchmark_raw_output_available":true,"family_benchmark_parse_success":true,"family_benchmark_solver":"lambdatwist_p3p","family_benchmark_num_cases":1000,"family_benchmark_success_rate":1.0,"family_benchmark_mean_best_reprojection_error":7.63e-14,"family_benchmark_max_best_reprojection_error":1.1e-12,"family_benchmark_runtime_ns_total_median":32928700.0,"family_benchmark_runtime_ns_per_case_median":32928.7,"family_benchmark_correctness_passed":true,"run_dir":"results/runs/2026-05-01_23-40-12_baseline"}
```

## `logs/`

Each command step writes one log whose filename matches the stable step name. Logs include step name, command, working directory, exit code, stdout, and stderr.

## Candidate Verification Artifacts

Materialized candidate runs write `verification.json`, `verification_summary.txt`, and command logs under `verification_logs/`. Verification runs only inside the isolated workspace from `materialization.json`; it configures CMake, runs `baseline_smoke_test`, runs the Lambda Twist P3P adapter validator, runs the absolute-pose family benchmark, and parses benchmark stdout into structured verification metrics.

If benchmark parsing fails, candidate verification fails because later comparison cannot use unstructured benchmark output. This still does not perform baseline-vs-candidate comparison or best-candidate selection.

## Benchmark Artifact Audit

`py -m orchestrator.benchmarking.audit_benchmark_pair --baseline-run <baseline_run_dir> --candidate-run <candidate_run_dir>` writes `<candidate_run_dir>/benchmark_artifact_audit.json`.

The audit loads baseline benchmark metrics from `metrics.json` and candidate benchmark metrics from `verification.json`. It checks artifact presence, parse success, required structured fields, matching family/solver/case count, runtime availability, correctness availability, and nanosecond runtime units. If benchmark options are not recorded yet, the audit emits `benchmark_options_not_recorded` as a warning instead of failing.

If build type is recorded in both baseline and candidate artifacts, the audit checks they match (`same_build_type`). A mismatch produces `build_type_mismatch`. If one or both artifacts do not include build type, the audit warns with `build_type_not_recorded` for backward compatibility with older artifacts.

The audit result records whether artifacts are comparable, but it does not rank candidates or choose a better version.

## Build Type Recording

Baseline `metrics.json` and candidate `verification.json` record the CMake build type in their benchmark sections:

```json
"benchmark": {
  ...
  "build_type": "Release",
  ...
}
```

Baseline `metadata.json` records `cmake_build_type` in its environment section:

```json
"environment": {
  ...
  "cmake_build_type": "Release"
}
```

The build type defaults to `Release` and is controlled by the `CMAKE_BUILD_TYPE` environment variable. Candidate verification also accepts `--cmake-build-type` as a CLI argument.

## `summary.txt`

`summary.txt` is a human-readable overview. It lists step statuses, adapter validation status, family benchmark status, the family benchmark raw output log, and parsed family benchmark values. If parsing fails, `summary.txt` lists missing fields or parse errors.

## Not Implemented Yet

- Baseline-vs-candidate comparison
- Best candidate selection
- Candidate promotion into the main source tree
