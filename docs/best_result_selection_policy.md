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
  the `decision_vs_current_best` outcome recorded on each iteration record.
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

This gate applies to:

- Current-best iteration decisions (`decision_vs_current_best`)
- Final selection comparison (`decision_vs_original_baseline`)

GT-found deltas are always recorded in the `comparison` block of decision
artifacts, even when the gate is disabled.

## 11. Candidate decision statuses

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

## 12. Improvement calculations

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

## 13. Closed-loop selection outcome

Closed-loop mode does not maintain a global candidate pool from which a single
best is picked by runtime ranking. Instead, each iteration is evaluated
independently against the current experiment-local best using the pairwise
decision policy defined in §5–§11. An `accepted_improvement` decision promotes
the candidate into the experiment-local `current_best_source` for the next
iteration.

At experiment completion, `orchestrator/experiments/final_selection_report.py`
produces `final_selection_report.json` under
`results/experiments/<experiment_id>/`. This artifact reports the final best
iteration selected after closed-loop completion, with a single benchmark run
comparing the final optimized source against the original baseline. It does not
use an `overall_status` field or a global ranking across all iterations.

Per-iteration decision outcomes are recorded in `closed_loop_iterations.jsonl`
using `IterationStatus` values (see `orchestrator/experiments/closed_loop_state.py`):

- `accepted_improvement`
- `valid_not_improved`
- `rejected`
- `materialization_failed`
- `verification_failed`
- `no_op`
- `generation_failed`

## 14. Non-goals

Selection and reporting do **not** implement:

- promotion into the main `cpp/` source tree
- benchmark modification
- benchmark threshold modification
- candidate generation prompt format or materialization format
- source-tree mutation from final selector/reporting artifacts

## 15. Closed-loop comparison in the runner

The comparator can compare a new verified candidate against either:

1. the original baseline run (`reference_kind="baseline"`), or
2. a previously accepted verified candidate run used as the current best
   (`reference_kind="verified_candidate"`).

For each verified candidate, the closed-loop runner writes
`decision_vs_original_baseline.json` to the candidate run directory and
records the `decision_vs_current_best` outcome as a field on the iteration
record (stored in `closed_loop_iterations.jsonl`).

Only the `decision_vs_current_best` outcome controls promotion. If it is
`accepted_improvement`, the closed-loop runner promotes the materialized
candidate workspace into
`workspace/experiments/<experiment_id>/current_best_source/` and updates
`current_best_state.json`.

`decision_vs_original_baseline.json` is for reporting/control and traceability.
It does not control promotion.

Final selector/reporting artifacts, including `closed_loop_selection_report.json`,
are analysis-only. They never promote candidates, update `current_best_source`,
rewrite `final_optimized_source`, or modify the main `cpp/` source tree.
