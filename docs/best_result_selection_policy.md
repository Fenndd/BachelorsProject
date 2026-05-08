# Best Result Selection Policy

## 1. Purpose

This policy defines how candidate optimization results are **filtered**,
**compared**, **ranked**, and **selected** against a baseline run.

This document defines the implemented pairwise decision and multi-candidate
selection policy.

Implementation status update (Step 11 / substep 3):

- Pairwise baseline-vs-candidate decision is now implemented in
  `orchestrator/benchmarking/candidate_decision.py`.
- Multi-candidate best selection is now implemented in
  `orchestrator/experiments/best_candidate_selector.py`.
- Candidate promotion is still not implemented and remains out of scope.
- Closed-loop optimization is still not implemented and remains out of scope.

## 2. Scope

This policy applies to the current Lambda Twist P3P case study evaluated through
the absolute-pose family benchmark.

The policy is intentionally written so it can be reused by future
absolute-pose solvers that expose the same benchmark metrics schema and
artifact layout.

## 3. Inputs

The selector consumes:

- a baseline run directory containing `metrics.json`
- one or more candidate run directories containing `verification.json`
- the existing benchmark artifact audit logic through the pairwise decision
  helper

Data source rules:

- Baseline benchmark metrics are loaded from `metrics.json`.
- Candidate benchmark verification metrics are loaded from `verification.json`.
- Selection consumes verified benchmark artifacts and is independent of raw LLM candidate format.
- It works for both `unified_diff` and `line_range_edits` candidates as long as `verification.json` exists.

## 4. Required benchmark fields

The following benchmark fields are required for comparison:

- `family`
- `solver`
- `parse_success`
- `parsed_num_cases`
- `parsed_success_rate`
- `parsed_mean_best_reprojection_error`
- `parsed_max_best_reprojection_error`
- `parsed_runtime_ns_per_case_median`
- `parsed_correctness_passed`
- `runtime_unit`
- `build_type`
- `benchmark_options`

## 5. Hard rejection gates

A candidate must be rejected (`rejected`) if any of the following is true:

1. Artifact audit says baseline/candidate artifacts are not comparable.
2. Benchmark artifact is missing.
3. Benchmark `parse_success` is not `true`.
4. `parsed_correctness_passed` is not `true`.
5. Runtime is missing, zero, negative, non-finite, or otherwise invalid.
6. `runtime_unit` is not `ns`.
7. Any of the following differ from baseline:
   - `family`
   - `solver`
   - `parsed_num_cases`
   - `benchmark_options`
   - `build_type`
8. Candidate success rate is below the allowed threshold.
9. Reprojection error violates the configured tolerance.

If any hard gate fails, runtime ranking is not allowed for that candidate.

## 6. Correctness-first rule

A candidate can never be selected as better only because it is faster.

Correctness and comparability are mandatory gates before runtime comparison.

## 7. Runtime comparison metric

Primary runtime metric:

- `parsed_runtime_ns_per_case_median`

Lower values are better.

## 8. Accuracy tolerance policy

Conservative default thresholds for first implementation:

- `allowed_success_rate_drop = 0.0`
- `max_mean_reprojection_error_ratio = 1.05`
- `max_max_reprojection_error_ratio = 1.05`

Interpretation:

- Candidate success rate must be at least
  `baseline_success_rate - allowed_success_rate_drop`.
- Candidate mean reprojection error ratio
  (`candidate_mean / baseline_mean`) must be
  `<= max_mean_reprojection_error_ratio`.
- Candidate max reprojection error ratio
  (`candidate_max / baseline_max`) must be
  `<= max_max_reprojection_error_ratio`.

These defaults may become configurable later, but the first selector
implementation should use these conservative defaults.

## 9. Candidate decision statuses

Pairwise candidate statuses:

- `rejected`
  - Candidate failed at least one hard rejection gate.
- `valid_not_improved`
  - Candidate passed all hard gates but does not improve runtime versus
    baseline.
- `accepted_improvement`
  - Candidate passed all hard gates and improves runtime versus baseline.

Experiment-level selection status is reported separately by the multi-candidate
selector and does not introduce an additional pairwise status in
`candidate_decision.py`.

## 10. Improvement calculations

Runtime improvement formulas:

- `speedup = baseline_runtime_ns_per_case_median / candidate_runtime_ns_per_case_median`
- `runtime_reduction_percent = ((baseline_runtime - candidate_runtime) / baseline_runtime) * 100`

Where:

- `baseline_runtime = baseline parsed_runtime_ns_per_case_median`
- `candidate_runtime = candidate parsed_runtime_ns_per_case_median`

## 11. Best candidate selection rule

Among all candidates with status `accepted_improvement`, select the candidate
with the lowest `parsed_runtime_ns_per_case_median`.

Tie-break order (deterministic):

1. Higher `parsed_success_rate`
2. Lower `parsed_mean_best_reprojection_error`
3. Lower `parsed_max_best_reprojection_error`
4. Earlier candidate/run order

## 12. Output of selector

The selector emits a structured JSON summary with the following fields:

Top-level:

| Field | Type | Description |
|---|---|---|
| `baseline_run_dir` | string | Path to the baseline run directory |
| `candidate_run_dirs` | string[] | Paths to all candidate run directories |
| `overall_status` | string | One of `best_candidate_found`, `no_improvement_found`, `all_candidates_rejected`, `no_candidates` |
| `best_candidate_run_dir` | string\|null | Path of the selected best candidate, or null |
| `best_candidate_decision_path` | string\|null | Path to the best candidate's `candidate_decision.json`, or null |
| `counts` | object | Counts summary (see below) |
| `best_metrics` | object | Metrics of the selected best candidate, or all-null if none (see below) |
| `decisions` | object[] | Per-candidate decision summaries (see below) |

`counts`:

| Field | Type | Description |
|---|---|---|
| `total` | int | Total number of candidates |
| `rejected` | int | Candidates with status `rejected` |
| `valid_not_improved` | int | Candidates with status `valid_not_improved` |
| `accepted_improvement` | int | Candidates with status `accepted_improvement` |

`best_metrics`:

| Field | Type | Description |
|---|---|---|
| `runtime_ns_per_case_median` | number\|null | Median runtime of the best candidate in nanoseconds per case |
| `speedup` | number\|null | Speedup vs baseline |
| `runtime_reduction_percent` | number\|null | Runtime reduction percent vs baseline |
| `success_rate` | number\|null | Success rate of the best candidate |
| `mean_best_reprojection_error` | number\|null | Mean reprojection error of the best candidate |
| `max_best_reprojection_error` | number\|null | Max reprojection error of the best candidate |

Each entry in `decisions`:

| Field | Type | Description |
|---|---|---|
| `candidate_run_dir` | string | Path to the candidate run directory |
| `status` | string | One of `rejected`, `valid_not_improved`, `accepted_improvement` |
| `candidate_decision_path` | string\|null | Path to `candidate_decision.json` if written, or null |
| `runtime_ns_per_case_median` | number\|null | Median runtime in nanoseconds per case |
| `speedup` | number\|null | Speedup vs baseline |
| `runtime_reduction_percent` | number\|null | Runtime reduction percent vs baseline |
| `success_rate` | number\|null | Candidate success rate |
| `mean_best_reprojection_error` | number\|null | Mean reprojection error |
| `max_best_reprojection_error` | number\|null | Max reprojection error |
| `rejection_reasons` | string[] | List of rejection reasons (empty for non-rejected) |

## 13. Non-goals

This step does **not** implement:

- candidate promotion
- benchmark modification
- benchmark threshold modification
- candidate generation prompt format or materialization format
- automatic closed-loop optimization

## 14. Experiment runner integration

The experiment runner can optionally execute selection after candidate
generation/materialization/verification. When enabled, it writes
`best_candidate_selection.json` under the experiment artifact directory and adds
a compact selection summary to experiment status/summary artifacts.

Selection does not promote, merge, copy, or commit candidate source code.