# Best Result Selection Policy

## 1. Purpose

This policy defines how candidate optimization results are **filtered**,
**compared**, **ranked**, and **selected** against a reference run.

This document defines the pairwise decision policy used by the
closed-loop optimization pipeline.

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

- Baseline benchmark metrics are loaded from `metrics.json` after 100 sequential benchmark executions.
- Candidate benchmark verification metrics are loaded from `verification.json` after 100 sequential benchmark executions.
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
- `benchmark_run_count`
- `decision_metric = "median_runtime_ns_per_problem_median"`
- `repeated_benchmark_samples`
- `repeated_benchmark_aggregate`

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

This field is the median of the repeated `runtime_ns_per_problem_median` samples. Lower values are better. Mean and max are not decision metrics.

## 8. Correctness policy

Correctness is defined by the benchmark artifact itself. The decision layer
requires `parsed_correctness_passed == true` for both reference and
candidate artifacts before runtime comparison.

A separate optional gate (`gt_found_max_drop_points`) limits how much the
ground-truth found percentage can regress. See **§9: GT Found Regression
Policy** below.

## 9. GT Found Regression Policy

The optional `gt_found_max_drop_points` gate limits acceptable regression in
the ground-truth found percentage. It is configured in the experiment config:

```json
{
  "selection": {
    "gt_found_max_drop_points": null
  }
}
```

- **`null`** (default): the gate is disabled. The `gt_found_percent` delta
  is observed and recorded in comparison metadata, but it never causes
  rejection or blocks acceptance.
- **Number** (e.g. `2.0`): maximum allowed drop in **percentage points**
  compared to the reference.
  - Formula: `candidate_gt_found_percent >= reference_gt_found_percent - max_drop_points`
  - Example: reference achieves 100.0% and max_drop_points is 2.0. A
    candidate at 97.5% has a drop of 2.5 pp, which exceeds the limit and
    is rejected with reason `gt_found_drop_exceeds_max_drop_points`.
  - 100.0% → 97.5% is a drop of **2.5 percentage points** (not 2.5%).

This gate applies to aggregate repeated-median artifacts for:

- Current-best iteration decisions (`decision_vs_current_best`)
- Final selection comparison (`decision_vs_original_baseline`)

GT-found deltas are always recorded in the `comparison` block of decision
artifacts, even when the gate is disabled.

## 10. Candidate decision statuses

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
- `confirmation_required`
  - Candidate passed hard gates and initial repeated-median runtime reduction is at least 1.0% but below 2.0%.
  - The runner must run another 100 candidate-only benchmark executions, merge all candidate samples, and rerun the decision.
- `accepted_improvement`
  - Candidate passed all hard gates and improves runtime versus the reference by
    at least the minimum runtime reduction threshold.

After confirmation, the final merged 200-run artifact is decided as either `accepted_improvement` or `valid_not_improved`.

## 11. Improvement calculations

Runtime improvement formulas:

- `speedup = reference_runtime_ns_per_problem_median / candidate_runtime_ns_per_problem_median`
- `runtime_reduction_percent = ((reference_runtime - candidate_runtime) / reference_runtime) * 100`

Default thresholds:

- `min_runtime_reduction_percent = 1.0`
- `immediate_accept_runtime_reduction_percent = 2.0`

For `accepted_improvement`, the candidate must pass correctness/comparability
gates, have lower runtime than the reference, and have
`runtime_reduction_percent >= min_runtime_reduction_percent`. A candidate with
`runtime_reduction_percent >= 2.0` is accepted immediately after the first 100
candidate benchmark executions. A candidate with `1.0 <= runtime_reduction_percent < 2.0`
requires another 100 candidate-only executions and is decided from the merged
200-sample median. A faster candidate below 1.0% is recorded as
`valid_not_improved` with comparison metrics still present and
`non_acceptance_reasons` containing `runtime_improvement_below_minimum_threshold`.
Its `rejection_reasons` remain empty because it passed hard rejection gates.

Where:

- `reference_runtime = reference parsed_runtime_ns_per_problem_median` repeated median
- `candidate_runtime = candidate parsed_runtime_ns_per_problem_median` repeated median

## 12. Related Documents

- `experiment_workflow.md` — full pipeline overview including closed-loop promotion
  flow, iteration statuses, and final artifacts.
- `closed_loop_optimization.md` — detailed closed-loop reference including source
  roots, current-best state, history context, and safety invariants.
