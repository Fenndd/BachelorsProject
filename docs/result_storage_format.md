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

Verification itself does not compare against baseline. Pairwise candidate
decision and multi-candidate selection are separate stages that consume verified
artifacts.

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

Candidate generation records both the logical target path and the physical source
location used to read the prompt source. `target_file` remains the stable
repo-relative path shown to the LLM and used in candidate `target_files` and
`allowed_files`. `source_root` defaults to the repository root. In closed-loop
runs it points at the experiment-local current-best source tree.

Example fields in `metadata.json`:

```json
{
  "target_file": "cpp/external/lambdatwist/p3p.cc",
  "source_root": "workspace/experiments/<experiment_id>/current_best_source",
  "physical_source_path": "workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc",
  "candidate_format": {
    "type": "line_range_edits",
    "source_presentation": "line_numbered"
  }
}
```

`llm_request.json` also records `target_file`, `source_root`,
`physical_source_path`, `allowed_files`, prompts, additional context, and
candidate format. The prompt schema and candidate JSON schema are unchanged; the
LLM still sees the logical repo-relative target file, not the temporary
workspace path.

`llm_response.json` includes a structured `llm_usage` block for reporting and
auditability. Fields are nullable when a provider or mock response does not
report them:

```json
{
  "llm_usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567,
    "total_tokens": 1801,
    "api_latency_seconds": 2.345,
    "finish_reason": "stop",
    "model": "deepseek-chat",
    "model_version": null
  }
}
```

The response artifact records usage metadata and raw provider response data, but
does not include API keys or environment secrets.

Generation and materialization both have configurable physical source roots for
closed-loop runs. Generation uses `--source-root` to read the source shown to the
LLM while keeping candidate paths logical and repo-relative. Materialization uses
`--base-source-root` to copy the same source version into an isolated candidate
workspace before applying the candidate. The candidate JSON schema is unchanged.

## Closed-loop Experiment Artifacts

When an experiment config sets:

```json
{
  "closed_loop": {"enabled": true}
}
```

Closed-loop mode runs an iterative current-best optimization flow with compact
benchmark-aware LLM history and final result artifacts. It currently supports
exactly one variant and requires `selection.baseline_run_dir` as the original
baseline reference. The baseline run directory must contain `metrics.json`.

The current best source and mutable state are stored under `workspace/`, not in
the main `cpp/` tree:

```text
workspace/experiments/<experiment_id>/current_best_source/
workspace/experiments/<experiment_id>/current_best_state.json
```

At initialization, `current_best_source/` is populated from the clean repository
`cpp/` tree while preserving repo-relative paths such as:

```text
workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc
```

Per-iteration records are appended compactly to:

```text
results/experiments/<experiment_id>/closed_loop_iterations.jsonl
```

The JSONL file is not rewritten at finalization; each line remains one compact
iteration record.

Each closed-loop iteration generates from `current_best_source` using
`--source-root`, materializes against the same source version using
`--base-source-root`, verifies the materialized candidate, compares it against
the current best, and also compares it against the original baseline. Before
generation, the runner builds compact plain-text history from all previous
meaningful closed-loop iterations and passes it to `generate_candidate` through
`--context` together with any configured additional context. The runner does not
early-stop; all planned iterations are attempted.

Candidate promotion is controlled only by:

```text
results/runs/<candidate_run_id>/decision_vs_current_best.json
```

If that decision has `status: "accepted_improvement"`, the materialized
workspace recorded in `materialization.json` as `workspace_path` replaces
`current_best_source/`, and `current_best_state.json` is updated. The companion
artifact:

```text
results/runs/<candidate_run_id>/decision_vs_original_baseline.json
```

is written for reporting/control and does not control promotion.

No-op candidates are recorded with status `no_op` when `expected_effect` is
`"none"` and the edit payload is empty (`edits` for `line_range_edits`, or
`unified_diff` for `unified_diff`). They do not run materialization or
verification.

After all planned iterations have been attempted, the runner writes final
closed-loop artifacts under the experiment result directory:

```text
results/experiments/<experiment_id>/final_optimized_source/
results/experiments/<experiment_id>/final_optimized_source.diff
results/experiments/<experiment_id>/final_diff_stats.json
results/experiments/<experiment_id>/closed_loop_summary.json
results/experiments/<experiment_id>/closed_loop_selection_report.json
results/experiments/<experiment_id>/val/
results/experiments/<experiment_id>/val/final_validation_report.json
results/experiments/<experiment_id>/experiment_metadata.json
results/experiments/<experiment_id>/current_best_state.json
```

`final_optimized_source/` is a copy of the final workspace
`current_best_source/` tree and preserves repo-relative structure, for example:

```text
results/experiments/<experiment_id>/final_optimized_source/cpp/external/lambdatwist/p3p.cc
```

It is written even when no improvement was accepted, in which case it is
baseline-equivalent. The copy does not modify the workspace current-best source
and never modifies `REPO_ROOT/cpp`.

`final_optimized_source.diff` is a unified diff from the original clean baseline
source to the final optimized source. It is generated for at least the
experiment `target_file`, with headers such as:

```text
--- a/cpp/external/lambdatwist/p3p.cc
+++ b/cpp/external/lambdatwist/p3p.cc
```

If the final source matches the original baseline, the diff file exists and may
be empty. This final diff is distinct from per-iteration
`candidate.generated.diff`, which compares that iteration's current best source
to the candidate workspace.

`closed_loop_summary.json` is human-readable JSON with:

- `experiment_id`
- `target_file`
- `total_iterations`
- `completed_iterations`
- `original_baseline_run_dir`
- `original_baseline_metrics_path`
- `final_best_iteration`
- `final_best_candidate_run_dir`
- `final_optimized_source_dir`
- `final_optimized_source_diff_path`
- `iterations_after_final_best`
- `status_counts` for every closed-loop iteration status, including zero counts
- `created_at`
- `finished_at`
- `final_diff_stats`
- `final_validation_report_path`
- `final_validation_median_speedup`
- `final_validation_median_runtime_reduction_percent`

`closed_loop_summary.json` no longer stores single-run final speedup or runtime
reduction fields. Those values are retained only as iteration and selection
analytics. Final performance metrics come from final repeated validation only.

The results-side `current_best_state.json` is a final metadata copy of the
workspace current-best state. The workspace state file is kept.

`experiment_status.json` includes a `closed_loop` block when closed-loop mode is
enabled. The block contains final best iteration, accepted improvement count,
final artifact paths, status counts, and the final validation report path/median
comparison metrics when final validation has run. It does not expose single-run
final speedup/runtime-reduction fields.

## Final Repeated Benchmark Validation

Final repeated benchmark validation runs automatically after closed-loop
completion and final artifact creation, and before report generation. It compares
the original baseline source against `final_optimized_source/`. It does not rerun
the LLM, does not rerun every candidate, does not affect candidate promotion, and
does not change `current_best_source`.

The optional config block is:

```json
{
  "final_validation": {
    "enabled": true,
    "benchmark_repetitions": 5
  }
}
```

If `final_validation` is missing, validation defaults to enabled. If
`final_validation.benchmark_repetitions` is missing, default 5 is used. The value
must be a positive integer.

The validation directory layout is shortened for Windows path-length safety:

```text
results/experiments/<experiment_id>/val/
├── final_validation_report.json
├── b/
│   ├── cpp/
│   ├── build/
│   ├── runs/
│   └── logs/
└── f/
│   ├── cpp/
│   ├── build/
│   ├── runs/
│   └── logs/
```

`b` means baseline and `f` means final. Each group contains one minimal shortened
`cpp/` source tree, one build directory, and a
first-class `setup` block recording configure/build status, durations, log paths,
failed step, and error message. The runner configures/builds once per group, then
writes repeated benchmark run JSON and logs under that group. Failed benchmark
repetitions are recorded and remaining repetitions continue when possible. If
source preparation, path-length preflight, configure, build, or executable lookup
fails, `runs` is empty, `benchmark_runs_attempted` is `0`, and no fake
`run_01.json` ... records are created.

The validation `cpp/` tree is not a full copy of the repository `cpp/` tree. It
contains only `CMakeLists.txt`, `external/lambdatwist/`, `bench/core/`,
`bench/adapters/lambdatwist_p3p/`, and
`bench/runners/lambdatwist_p3p_benchmark.cpp`. It excludes project `src/`,
`include/`, `tests/`, `bench/baseline_benchmark.cpp`, the adapter validator,
smoke tests, and unrelated benchmark/test targets. The original repository
`cpp/` layout is unchanged.

`final_validation_report.json` uses `schema_version: "final_validation.v1"` and
contains setup records, per-run benchmark-only records, aggregate
median/mean/min/max/population-std runtime statistics, correctness summaries,
comparison speedups, and safety flags stating that validation does not update
current-best state, promotion decisions, or the main `cpp/` tree. Run records use
`validation_mode: "benchmark_only"` and `benchmark_run_status`; they do not use or
write `verification_status`. Runtime aggregates use only runs with
`benchmark_run_status: "success"`, `correctness_passed: true`, and numeric runtime
values. Final validation runtime plots use the same criteria. If baseline or final
has no successful correct run, comparison metrics are `null`.

Diagnostics include setup/group fields: `baseline_setup_failed`,
`final_setup_failed`, `baseline_group_status`, and `final_group_status`. Group
status is `setup_failed`, `benchmark_failed`, `completed`, or `not_run`.

The report includes `source_layout` metadata with the original `cpp/` root, the
validation `cpp/` root, the original absolute-pose solver root, the shortened
validation root, copied components, and excluded components. Group blocks also
include `source_dir`, `build_dir`, `runs_dir`, and `logs_dir` paths.

The final validation `status` field is one of:

- `skipped`: validation was disabled.
- `completed`: comparison metrics are available and every baseline/final repetition was successful and correctness-passing.
- `completed_partial`: comparison metrics are available but at least one repetition failed or failed correctness.
- `incomplete`: validation ran but comparison metrics are unavailable.

`experiment_metadata.json` records process metadata for experiment runs. For
closed-loop runs, `finished_at` and `total_duration_seconds` cover the full
experiment cycle: closed-loop iterations, final artifact creation, final
validation, report generation or recorded reporting failure, and final
status/summary output. This is distinct from `closed_loop_summary.finished_at`,
which marks closed-loop optimization completion before final validation.

```json
{
  "schema_version": "experiment_metadata.v1",
  "started_at": "...",
  "finished_at": "...",
  "total_duration_seconds": 60.0,
  "repository": {
    "git_commit": "...",
    "git_branch": "...",
    "dirty_worktree": false
  },
  "environment": {
    "os": "...",
    "platform": "...",
    "python_version": "...",
    "cmake_build_type": "Release",
    "cmake_exe": "...",
    "cmake_generator": "...",
    "cxx_compiler": "..."
  }
}
```

Only selected safe environment fields are persisted; API keys and other secrets
are not written.

`closed_loop_selection_report.json` is reporting-only. It records a
`control_decision` section describing the promotion policy and final best run,
and a separate `single_run_selection_analytics` section describing final
source/diff paths, single-run speedup/runtime-reduction analytics, and status
counts. That analytics section includes
`metric_source: "single_run_closed_loop_selection_analytics"`; these metrics are
not final validated headline metrics. Its safety flags state that the report does
not promote candidates, update `current_best_source`, update
`final_optimized_source`, or modify the main `cpp/` tree.

`summary.txt` includes a concise closed-loop section listing the experiment id,
target file, total/completed iterations, final best iteration, accepted
improvements, status counts, paths to the final optimized source, final diff,
summary JSON, iteration JSONL, final current-best metadata, and final repeated
benchmark validation status/path/median metrics. If final validation metrics are
unavailable, it explicitly says final repeated validation metrics are unavailable
and that single-run selection metrics are iteration analytics only, not final
headline metrics.

Closed-loop history is deliberately separate from the non-closed-loop
`history_policy` variant-local sliding-window history. It includes all
meaningful previous records compactly; it does not use
`max_previous_iterations`. History can include `accepted_improvement`,
`valid_not_improved`, `rejected`, `materialization_failed`, and
`verification_failed` records. Materialization and verification failures are
included only when they have usable candidate information such as
`candidate_run_dir` or `candidate_summary`. No-op iterations and generation
failures without usable candidates are excluded. The current deterministic
policy also excludes generation failures even if a candidate summary exists,
because they are not reliable optimization patterns.

The exact context used for each closed-loop generation step is written under the
experiment logs directory:

```text
results/experiments/<experiment_id>/logs/iteration_003_closed_loop_history_context.txt
```

If no meaningful history exists yet, the file contains:

```text
No meaningful closed-loop history yet.
```

The history context contains summaries, benchmark-aware result text, compact
failure/rejection reasons, and deterministic guidance. It does not contain full
source code, diffs, full `candidate.json`, full `verification.json`, benchmark
logs, audit objects, stack traces, or no-op entries.

Each `closed_loop_iterations.jsonl` record contains:

- `history_included`: whether this iteration will be included in future
  closed-loop history
- `history_guidance`: deterministic future guidance for included records, or
  `null` for excluded records
- `phase_timings`: optional per-phase durations with `generation_seconds`,
  `materialization_seconds`, `verification_seconds`, `benchmark_seconds`, and
  `total_iteration_seconds`. `benchmark_seconds` may be `null` until a separate
  benchmark duration is available. Verification time includes benchmark
  execution; `benchmark_seconds` is not separately shown in the main report.
- `outcome_reason`: optional normalized reason object explaining why the status
  occurred. New closed-loop runs write it directly; report collection
  reconstructs a best-effort value for older artifacts.

Example `outcome_reason`:

```json
{
  "category": "verification",
  "code": "benchmark_correctness_failed",
  "severity": "error",
  "message": "Candidate failed benchmark correctness check.",
  "source_artifact": "results/runs/<candidate_run_id>/verification.json"
}
```

Stable categories are `generation`, `no_op`, `materialization`, `verification`,
`decision`, and `unknown`. Stable severities are `info`, `warning`, and `error`.
Reason codes are compact and intentionally do not encode raw exception text.
Common codes include:

- Generation: `generation_failed`, `llm_request_failed`,
  `llm_response_parse_failed`, `candidate_json_invalid`,
  `candidate_artifacts_missing`, `candidate_run_dir_parse_failed`
- No-op: `no_op_candidate`, `empty_edit_payload`
- Materialization: `materialization_failed`, `scope_violation`,
  `diff_apply_failed`, `line_range_mismatch`,
  `line_range_fallback_ambiguous`, `target_file_missing`, `no_files_changed`
- Verification: `verification_failed`, `configure_failed`, `build_failed`,
  `smoke_test_failed`, `adapter_validation_failed`,
  `benchmark_execution_failed`, `benchmark_parse_failed`,
  `benchmark_correctness_failed`, `metrics_missing`
- Decision: `accepted_improvement`, `valid_not_improved`,
  `rejected_correctness`, `rejected_not_comparable`, `rejected_no_speedup`,
  `rejected_benchmark_audit_failed`, `decision_artifact_missing`
- Fallback: `unknown_reason`

The main `cpp/` source tree is never modified automatically.

The final selector/reporting step never promotes candidates. The only automatic
current-best promotion path is an iteration whose
`decision_vs_current_best.json` has `status: "accepted_improvement"`.

Deterministic tests validate these storage and safety contracts with fixtures and
monkeypatched closed-loop runners. They include a controlled mock scenario where
one accepted candidate is promoted, a later slower candidate is not promoted, and
a no-op is recorded but excluded from future compact history.

The report is a single unified current report, not separate v1/v2 modes.
`report/report_data.json` uses `schema_version: "report.v2"` and includes each
iteration's normalized `outcome_reason` and a top-level `reason_code_counts`
array grouped by `category` and `code`. This complements the older
human-readable `reason_summary`, which remains available for backward
compatibility with incomplete artifacts.

The generated `report/report.html` and optional `report/report.pdf` use these
enriched fields in the unified single-experiment report:

- Outcome and Failure Analysis, backed by `reason_code_counts`
- Phase Timings, backed by per-iteration `phase_timings`
- LLM Usage, backed by per-iteration `llm_usage`
- Reproducibility and Environment, backed by `experiment_metadata`
- Diff Statistics, backed by per-iteration `diff_stats` and final
  `final_best_candidate.diff_stats`
- Iteration Appendix, a compact per-iteration summary combining status,
  candidate metadata, outcome reason, runtime, correctness, timings, LLM usage,
  diff stats, and candidate run directory

For HTML-only output, report data, plots, and final completed HTML are written.
For HTML+PDF output, final completed HTML is rendered once with the expected
`report/report.pdf` path and the PDF is exported from that final HTML. If PDF
export fails, reporting status is updated to `failed`, HTML is re-rendered with
that failed status when possible, and the exception is propagated to the runner's
existing reporting error policy.

When final repeated validation metrics are available, the Executive Summary
headline baseline runtime and final runtime use the same repeated-validation
comparison basis. The separate Baseline Metrics section may still show the
original single-run baseline artifact.

The user-facing report focuses on closed-loop mode. Legacy `selection_enabled`
and `history_policy` fields are not shown as main report concepts. Closed-loop
promotion policy is `decision_vs_current_best.accepted_improvement_only`.
Build type is reproducibility metadata; `Release` is the default benchmark build
type.

These sections are presentation-only. They do not promote candidates, rerun
benchmarks, recompute verification, materialize source, or modify `cpp/`. Older
or incomplete report data is handled through graceful degradation where possible:
if enriched metadata is missing, report generation still succeeds and the
corresponding tables or SVG plots state that the data is unavailable.

`orchestrator.reporting.report_inspector` can inspect an existing report directory
without regenerating anything:

```powershell
python -m orchestrator.reporting.report_inspector --experiment-dir results/experiments/<experiment_id>
```

It validates the presence and object shape of `report_data.json`, `report.html`,
optional `report.pdf`, expected plot files, and important HTML section ids.
Missing PDF is valid for HTML-only reports. If PDF was requested and missing, the
inspector reports a warning. Invalid or missing `report_data.json` and missing
`report.html` are failures. The manual checklist for real-cycle current-report review is
`docs/report_v2_checklist.md`.

Final repeated benchmark validation is a final evaluation step, not
per-candidate repeated benchmarking. It compares N repeated baseline runs against
N repeated final optimized source runs, reports median/mean/std/min/max for
successful correctness-passing repetitions, writes `final_validation_report.json`,
and displays a Final Validation section.

## Candidate Materialization Artifacts

`materialization.json` records scope traceability for successful, skipped, and failed materializations. Common fields include:

- `overall_status`
- `candidate_type`
- `workspace_path`
- `source_root`
- `base_source_root`
- `source_root_mode`
- `target_files`
- `patched_files`
- `changed_files`
- `scope_enforcement`
- `allowed_files`
- `patch_apply_strategy`
- `diff_stats`

`diff_stats` summarizes the candidate unified diff source used by the
materializer. For `unified_diff`, this is `candidate.diff`; for
`line_range_edits`, this is the generated `candidate.generated.diff` when it is
available. The object contains:

```json
{
  "files_changed": 1,
  "lines_added": 2,
  "lines_removed": 1,
  "changed_blocks": 1,
  "edit_count": 1,
  "fallback_used": false
}
```

`edit_count` is populated for `line_range_edits` from
`line_range_edit_count`; it is `null` for legacy unified diffs unless a clear
structured count exists. `fallback_used` maps to `line_range_fallback_used` for
line-range candidates and to `git_apply_recount_used` for unified diffs.

`source_root` remains for backward compatibility. `base_source_root` is the
explicit field for the source tree copied from. `source_root_mode` describes how
that source tree was selected:

- `repo_default`: no explicit source-root flags; legacy default `cpp` copy behavior
- `legacy_source_root`: explicit legacy `--source-root`
- `explicit_base_source_root`: explicit repo-like `--base-source-root`

The selected source tree is only copied from. Materialization applies changes
inside `workspace_path` and does not modify either `base_source_root` or the main
`cpp/` source tree directly.

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
- `generated_diff_base`
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
  "generated_diff_path": "results/runs/<candidate_run_id>/candidate.generated.diff",
  "generated_diff_base": "base_source_root"
}
```

For `line_range_edits`, `candidate.generated.diff` is generated by comparing the
copied base-source text before edits with the candidate workspace text after
edits. In closed-loop runs this is an iteration-local diff from
`current_best_source` to that candidate. It is distinct from
`final_optimized_source.diff`, which reports the final accepted source against
the original clean baseline.

## Benchmark Artifact Audit

`py -m orchestrator.benchmarking.audit_benchmark_pair --baseline-run <baseline_run_dir> --candidate-run <candidate_run_dir>` writes `<candidate_run_dir>/benchmark_artifact_audit.json`.

The baseline audit path loads baseline benchmark metrics from `metrics.json` and
candidate benchmark metrics from `verification.json`. The generic comparison
path can also load a reference verified candidate from `verification.json` by
using `reference_kind="verified_candidate"`. Candidate benchmark metrics are
always loaded from `verification.json`.

The audit checks artifact presence, parse success, required structured fields,
matching family/solver/case count, runtime availability, correctness
availability, and nanosecond runtime units. If benchmark options are not recorded
yet, the audit emits `benchmark_options_not_recorded` as a warning instead of
failing.

If build type is recorded in both baseline and candidate artifacts, the audit checks they match (`same_build_type`). A mismatch produces `build_type_mismatch`. If one or both artifacts do not include build type, the audit warns with `build_type_not_recorded` for backward compatibility with older artifacts.

The audit checks comparability. `candidate_decision` consumes audit output to
make pairwise reference-vs-candidate decisions. The old baseline-vs-candidate
API remains supported for compatibility. `best_candidate_selector` continues to
consume baseline-vs-candidate decisions to select the best candidate among
verified candidates.

Decision artifacts are human-readable JSON. The default writer still produces:

```text
results/runs/<candidate_run_id>/candidate_decision.json
```

For closed-loop runs, the same writer emits additional decision artifact names
inside the candidate run directory:

```text
results/runs/<candidate_run_id>/decision_vs_current_best.json
results/runs/<candidate_run_id>/decision_vs_original_baseline.json
```

Only `decision_vs_current_best.json` decides whether a verified candidate becomes
the new current best. `decision_vs_original_baseline.json` is for
reporting/control. Closed-loop promotion updates only the experiment-local
`current_best_source/`; it does not modify the main `cpp/` source tree.

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

Baseline and candidate run directories use `summary.txt` as a human-readable
overview of step statuses and benchmark results. These summaries list items such
as adapter validation status, family benchmark execution status, benchmark parse
status, benchmark log paths, parse errors when applicable, and parsed benchmark
values. If correctness checking fails, the run summary lists
`failed_step: benchmark_correctness_check` and still shows the parsed benchmark
values.

Experiment result directories use their own `summary.txt` for experiment-level
status. The experiment summary describes configured iterations/variants,
selection status when selection is enabled, and closed-loop final artifacts when
closed-loop mode is enabled. In closed-loop experiments, this includes final best
iteration, accepted improvements, status counts, final repeated validation metrics
when available, and paths to `final_optimized_source/`,
`final_optimized_source.diff`, `closed_loop_summary.json`,
`closed_loop_iterations.jsonl`, and results-side `current_best_state.json`.

## Not Implemented Yet

- Candidate promotion into the main source tree
- Advanced plots, broader statistical dashboards, and additional aggregate analyses
- JSON metrics output directly from C++ benchmarks
- Additional solver families/adapters
- Configurable minimum runtime-improvement thresholds or repeated-benchmark confidence policies
- Memory measurement; the current minimal P3P pipeline records runtime and correctness/reprojection metrics only
