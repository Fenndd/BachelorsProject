# Best Result Selection Policy

## 1. Purpose

This policy defines how candidate optimization results are **filtered**,
**compared**, **ranked**, and **selected** against a reference run.

This document defines the implemented pairwise decision policy used by the
closed-loop optimization pipeline.

Implementation status update:

- Pairwise reference-vs-candidate decision is implemented in
  `orchestrator/core/benchmarking/candidate_decision.py`.
- The original baseline-vs-candidate API remains available as a compatibility
  wrapper for direct pairwise comparisons.
- Closed-loop experiments use reference-vs-candidate decisions inside each
  iteration.
- Experiment-local current-best promotion is implemented through
  `decision_vs_current_best.json`.
- Promotion into the main `cpp/` source tree is still not implemented and remains
  out of scope for selection/reporting.

## 2. Scope

This policy applies to the current Lambda Twist P3P case study evaluated through
the absolute-pose family benchmark.

The policy is intentionally written so it can be reused by future
absolute-pose solvers that expose the same benchmark metrics schema and
artifact layout.

## 3. Inputs

The pairwise comparator supports an explicit generic reference:

- `reference_kind = "baseline"`: load the reference benchmark from
  `<reference_run_dir>/metrics.json`
- `reference_kind = "verified_candidate"`: load the reference benchmark from
  `<reference_run_dir>/verification.json`
- candidate benchmark metrics are still loaded from
  `<candidate_run_dir>/verification.json`

Data source rules:

- Baseline benchmark metrics are loaded from `metrics.json`.
- Candidate benchmark verification metrics are loaded from `verification.json`.
- Verified-candidate reference metrics are loaded from `verification.json`.
- Selection consumes verified benchmark artifacts and is independent of raw LLM candidate format.
- It works for generated candidates as long as `verification.json` exists.

## 4. Required benchmark fields

The following benchmark fields are required for comparison:

- `family`
- `solver`
- `parse_success`
- `parsed_num_problems`
- `parsed_total_solutions`
- `parsed_solutions_per_problem`
- `parsed_valid_solutions`
- `parsed_valid_solutions_percent`
- `parsed_gt_found`
- `parsed_gt_found_percent`
- `parsed_runtime_ns_total_median`
- `parsed_runtime_ns_per_problem_median`
- `parsed_correctness_passed`
- `runtime_unit`
- `build_type`
- `benchmark_options`

## 5. Hard rejection gates

A candidate must be rejected (`rejected`) if any of the following is true:

1. Artifact audit says reference/candidate artifacts are not comparable.
2. Benchmark artifact is missing.
3. Benchmark `parse_success` is not `true`.
4. `parsed_correctness_passed` is not `true`.
5. Runtime is missing, zero, negative, non-finite, or otherwise invalid.
6. `runtime_unit` is not `ns`.
7. Any of the following differ from the reference:
   - `family`
   - `solver`
   - `parsed_num_problems`
   - `benchmark_options`
   - `build_type`

If any hard gate fails, runtime ranking is not allowed for that candidate.

## 6. Correctness-first rule

A candidate can never be selected as better only because it is faster.

Correctness and comparability are mandatory gates before runtime comparison.

## 7. Runtime comparison metric

Primary runtime metric:

- `parsed_runtime_ns_per_problem_median`

Lower values are better.

## 8. Correctness policy

Correctness is defined by the benchmark artifact itself. The decision layer does
not compare `gt_found_percent` or `valid_solutions_percent` against the
reference; it only requires `parsed_correctness_passed == true` for both
reference and candidate artifacts before runtime comparison.

## 9. Candidate decision statuses

Pairwise candidate statuses:

- `rejected`
  - Candidate failed at least one hard rejection gate.
- `valid_not_improved`
  - Candidate passed all hard gates but does not improve runtime versus
    the reference by the minimum required amount.
  - This includes candidates that are faster but below the minimum runtime
    reduction threshold.
  - Non-rejected candidates can include `non_acceptance_reasons` explaining why
    they were not accepted.
- `accepted_improvement`
  - Candidate passed all hard gates and improves runtime versus the reference by
    at least the minimum runtime reduction threshold.

Closed-loop final analysis does not introduce additional pairwise statuses in
`candidate_decision.py`.

## 10. Improvement calculations

Runtime improvement formulas:

- `speedup = reference_runtime_ns_per_problem_median / candidate_runtime_ns_per_problem_median`
- `runtime_reduction_percent = ((reference_runtime - candidate_runtime) / reference_runtime) * 100`

Default acceptance threshold:

- `min_runtime_reduction_percent = 0.5`

For `accepted_improvement`, the candidate must pass correctness/comparability
gates, have lower runtime than the reference, and have
`runtime_reduction_percent >= min_runtime_reduction_percent`. A faster candidate
below this threshold is recorded as `valid_not_improved` with comparison metrics
still present and `non_acceptance_reasons` containing
`runtime_improvement_below_minimum_threshold`. Its `rejection_reasons` remain
empty because it passed hard rejection gates.

Where:

- `reference_runtime = reference parsed_runtime_ns_per_problem_median`
- `candidate_runtime = candidate parsed_runtime_ns_per_problem_median`

## 11. Best candidate selection rule

Among all candidates with status `accepted_improvement`, select the candidate
with the lowest `parsed_runtime_ns_per_problem_median`.

Tie-break order (deterministic):

1. Earlier candidate/run order

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
| `runtime_ns_per_problem_median` | number\|null | Median runtime of the best candidate in nanoseconds per problem |
| `speedup` | number\|null | Speedup vs baseline |
| `runtime_reduction_percent` | number\|null | Runtime reduction percent vs baseline |
| `valid_solutions_percent` | number\|null | Valid-solution percentage reported by the benchmark |
| `gt_found_percent` | number\|null | GT-found percentage reported by the benchmark |

Each entry in `decisions`:

| Field | Type | Description |
|---|---|---|
| `candidate_run_dir` | string | Path to the candidate run directory |
| `status` | string | One of `rejected`, `valid_not_improved`, `accepted_improvement` |
| `candidate_decision_path` | string\|null | Path to `candidate_decision.json` if written, or null |
| `runtime_ns_per_problem_median` | number\|null | Median runtime in nanoseconds per problem |
| `speedup` | number\|null | Speedup vs baseline |
| `runtime_reduction_percent` | number\|null | Runtime reduction percent vs baseline |
| `valid_solutions_percent` | number\|null | Valid-solution percentage reported by the benchmark |
| `gt_found_percent` | number\|null | GT-found percentage reported by the benchmark |
| `rejection_reasons` | string[] | List of rejection reasons (empty for non-rejected) |
| `non_acceptance_reasons` | string[] | Reasons a valid non-rejected candidate was not accepted, when present |

## 13. Non-goals

Selection and reporting do **not** implement:

- promotion into the main `cpp/` source tree
- benchmark modification
- benchmark threshold modification
- candidate generation prompt format or materialization format
- source-tree mutation from final selector/reporting artifacts

## 14. Closed-loop comparison in the runner

The comparator can compare a new verified candidate against either:

1. the original baseline run (`reference_kind="baseline"`), or
2. a previously accepted verified candidate run used as the current best
   (`reference_kind="verified_candidate"`).

The closed-loop runner writes two decision artifacts for each verified candidate:

- `decision_vs_current_best.json`
- `decision_vs_original_baseline.json`

Only `decision_vs_current_best.json` decides whether the candidate becomes the
new experiment-local current best. If it reports `accepted_improvement`, the
closed-loop runner promotes the materialized candidate workspace into
`workspace/experiments/<experiment_id>/current_best_source/` and updates
`current_best_state.json`.

`decision_vs_original_baseline.json` is for reporting/control and traceability.
It does not control promotion.

Final selector/reporting artifacts, including `closed_loop_selection_report.json`,
are analysis-only. They never promote candidates, update `current_best_source`,
rewrite `final_optimized_source`, or modify the main `cpp/` source tree.
