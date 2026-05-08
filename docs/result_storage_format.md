# Result Storage Format

## Purpose

The `results/` directory stores persistent outputs produced by baseline, candidate, and experiment runs. Each baseline CLI run writes one detailed run directory under `results/runs/<run_id>/` and appends one compact record to `results/index.jsonl`.

## Baseline Run

For the current baseline phase, a run configures CMake, builds the baseline smoke test, baseline runner, Lambda Twist P3P adapter validator, and absolute-pose family benchmark, runs them, then parses the family benchmark output as an explicit internal step.

1. `baseline_smoke_test`
2. `baseline_runner`
3. `absolute_pose_lambdatwist_adapter_validator`
4. `absolute_pose_lambdatwist_benchmark`
5. parse `absolute_pose_lambdatwist_benchmark` stdout into structured metrics
6. check the parsed `correctness_passed` metric

The old `baseline_benchmark` target remains in CMake for compatibility, but the main baseline CLI now uses the family benchmark flow. If adapter validation fails, the family benchmark run step is skipped. If family benchmark execution succeeds but stdout parsing fails, the baseline run fails at `parse_absolute_pose_lambdatwist_benchmark`; benchmark execution success alone is not sufficient for a valid baseline artifact because future comparison needs structured metrics. If parsing succeeds but `correctness_passed=false`, the baseline run fails at `benchmark_correctness_check` while keeping all parsed benchmark metrics in `metrics.json`, `summary.txt`, and `index.jsonl`.

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
      │  ├─ run_absolute_pose_lambdatwist_benchmark.log
      │  ├─ parse_absolute_pose_lambdatwist_benchmark.log
      │  └─ benchmark_correctness_check.log
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
- `parse_absolute_pose_lambdatwist_benchmark`
- `benchmark_correctness_check`

## `metrics.json`

Baseline metrics contain success flags and parsed family benchmark values. The parser reads stable snake_case key-value lines from the family benchmark stdout. A benchmark execution failure fails the baseline run and skips parsing. If benchmark execution succeeds but parsing fails, the baseline run also fails, with `failed_step: "parse_absolute_pose_lambdatwist_benchmark"`. `metrics.json` still records `parse_success: false`, missing fields, parse errors, and any partially parsed values so the artifact remains diagnosable. If parsing succeeds but `parsed_correctness_passed` is `false`, the run fails at `benchmark_correctness_check`; `metrics.json` still records `parse_success: true` and all parsed benchmark values.

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
    "parsed_correctness_passed": true,
    "parsed_valid_cases": 1000,
    "parsed_total_solutions": 3000,
    "benchmark_options": {
      "num_cases": 1000,
      "points_per_case": 3,
      "warmup_iterations": 3,
      "timed_iterations": 10,
      "random_seed": 42,
      "reprojection_error_threshold": 1e-6,
      "min_success_rate": 0.99,
      "require_all_cases_valid": false,
      "use_max_reprojection_error_as_hard_gate": false,
      "runtime_unit": "ns",
      "build_type": "Release"
    }
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

Each command step writes one log whose filename matches the stable step name. Logs include step name, command, working directory, exit code, stdout, and stderr. The internal parse step may also write `logs/parse_absolute_pose_lambdatwist_benchmark.log` with the input benchmark log path, parse status, missing fields, and parse errors.

## Candidate Verification Artifacts

Materialized candidate runs write `verification.json`, `verification_summary.txt`, and command logs under `verification_logs/`. Verification runs only inside the isolated workspace from `materialization.json`; it configures CMake, runs `baseline_smoke_test`, runs the Lambda Twist P3P adapter validator, runs the absolute-pose family benchmark, and parses benchmark stdout into structured verification metrics.

If benchmark parsing fails, candidate verification fails because later comparison cannot use unstructured benchmark output. If parsing succeeds but `parsed_correctness_passed=false`, candidate verification fails at `benchmark_correctness_check` while preserving parsed benchmark metrics in `verification.json`. This matches the baseline policy.

Verification itself does not compare against baseline. Pairwise candidate decision and multi-candidate selection are separate stages that consume verified artifacts.

## Candidate Generation Artifacts

All candidate runs write:

- `metadata.json`
- `status.json`
- `summary.txt`
- `llm_request.json`
- `llm_response.json`
- `candidate.json`

For `unified_diff`:

- `candidate.diff`

For `line_range_edits`:

- `candidate.edits.json`
- `candidate.diff` is not required

## Candidate Materialization Artifacts

`materialization.json` records scope traceability for successful, skipped, and failed materializations. Common fields include:

- `overall_status`
- `candidate_type`
- `workspace_path`
- `target_files`
- `patched_files`
- `changed_files`
- `scope_enforcement`
- `allowed_files`
- `patch_apply_strategy`

Scope fields example:

```json
{
  "scope_enforcement": "external_allowed_files",
  "external_allowed_files_used": true,
  "allowed_files": ["cpp/external/lambdatwist/p3p.cc"]
}
```

When `--allowed-file` is supplied, `scope_enforcement` is `"external_allowed_files"` and `allowed_files` contains the normalized external allowlist. When materialization is run manually without `--allowed-file`, `scope_enforcement` is `"legacy_candidate_declared_target_files"`, `external_allowed_files_used` is `false`, and `allowed_files` records the normalized candidate `target_files` used as the legacy effective allowlist.

### `unified_diff` materialization fields

`patch_apply_strategy` can be:

- `git_apply`
- `git_apply_recount`
- `git_apply_recount_failed`
- `not_run`

Additional unified-diff fields include:

- `git_apply_recount_used`
- `git_apply_initial_check_failed`
- `git_apply_initial_check_error`
- `git_apply_recount_check_error`

### `line_range_edits` materialization fields

`patch_apply_strategy` can be:

- `line_range_edits`
- `line_range_edits_failed`
- `not_run`

Additional line-range fields include:

- `line_range_edit_count`
- `line_range_exact_matches`
- `line_range_fallback_matches`
- `line_range_fallback_used`
- `line_range_edit_results`
- `generated_diff_path`
- `candidate.generated.diff`

Example:

```json
{
  "candidate_type": "line_range_edits",
  "patch_apply_strategy": "line_range_edits",
  "line_range_edit_count": 2,
  "line_range_exact_matches": 2,
  "line_range_fallback_matches": 0,
  "line_range_fallback_used": false,
  "generated_diff_path": "results/runs/<candidate_run_id>/candidate.generated.diff"
}
```

## Benchmark Artifact Audit

`py -m orchestrator.benchmarking.audit_benchmark_pair --baseline-run <baseline_run_dir> --candidate-run <candidate_run_dir>` writes `<candidate_run_dir>/benchmark_artifact_audit.json`.

The audit loads baseline benchmark metrics from `metrics.json` and candidate benchmark metrics from `verification.json`. It checks artifact presence, parse success, required structured fields, matching family/solver/case count, runtime availability, correctness availability, and nanosecond runtime units. If benchmark options are not recorded yet, the audit emits `benchmark_options_not_recorded` as a warning instead of failing.

If build type is recorded in both baseline and candidate artifacts, the audit checks they match (`same_build_type`). A mismatch produces `build_type_mismatch`. If one or both artifacts do not include build type, the audit warns with `build_type_not_recorded` for backward compatibility with older artifacts.

The audit checks comparability. `candidate_decision` consumes audit output to make pairwise baseline-vs-candidate decisions. `best_candidate_selector` consumes pairwise decisions to select the best candidate among verified candidates.

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

`summary.txt` is a human-readable overview. It lists step statuses, adapter validation status, family benchmark execution status, benchmark parse status, the family benchmark raw output log, the optional parse log, and parsed family benchmark values. If parsing fails, `summary.txt` lists the failed parse step, missing fields, and parse errors. If correctness checking fails, it lists `failed_step: benchmark_correctness_check` and still shows the parsed benchmark values.

## Not Implemented Yet

- Candidate promotion into the main source tree
- Advanced reporting/plots
- JSON metrics output directly from C++ benchmarks
- Additional solver families/adapters
