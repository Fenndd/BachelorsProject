# Experiment Workflow

The optimization pipeline runs these stages in sequence for each iteration.

## 1. Baseline Benchmark

The baseline run measures the original solver using 100 sequential repeated benchmark
executions. Each execution produces one raw sample containing a
`runtime_ns_per_problem_median` value. The median of all sample
`runtime_ns_per_problem_median` values becomes
`parsed_runtime_ns_per_problem_median`, which is the primary decision metric.

The benchmark uses the PoseLib-native benchmark path configured through the solver
registry. Build type defaults to **Release** for benchmark measurement.
Results are stored in `results/runs/<run_id>/metrics.json`.

## 2. LLM Candidate Generation

The LLM receives the target source file with 1-based line numbers and returns one
JSON candidate object containing:

- `summary` — short summary of the proposed optimization
- `rationale` — why the change may improve performance
- `correctness_notes` — why numerical behavior should remain unchanged
- `edits` — list of edit objects, each with `start_line`, `end_line`, `original`, `replace`

The target file is configured outside the candidate JSON. All edits apply to it.
A no-op candidate uses `edits: []` (a valid outcome).

If the LLM call or response parsing fails, the iteration records as `generation_failed`.

See `candidate_edit_formats.md` for the exact schema.

## 3. Candidate Materialization

The materializer copies the base source tree (the original `cpp/` tree or the
experiment-local `current_best_source`) into an isolated workspace. It applies
each edit in reverse line-number order to keep line ranges stable.

Line-range matching proceeds through increasingly tolerant strategies:

1. Exact match
2. Trailing whitespace-tolerant match
3. Surrounding whitespace-tolerant match (with indentation adaptation)
4. Exact-search fallback (whole-file search for the `original` text)

After applying edits, the materializer writes `candidate.generated.diff` as an
inspection artifact. The main `cpp/` source tree is never modified.

Artifacts include `materialization.json` and `apply_candidate.log`.

If the target file is not found, the candidate scope is invalid, or edits cannot
be applied, the iteration records as `materialization_failed`.

A no-op candidate produces `materialization.json` with status `skipped`.

## 4. Candidate Verification

Each materialized candidate is built in its isolated workspace and benchmarked
using the same benchmark path as the baseline. Verification runs 100 sequential
benchmark executions and writes `verification.json`.

If the candidate fails to build, run, or produce valid benchmark output, the
iteration records as `verification_failed`.

## 5. Pairwise Decision

The candidate is compared against an explicit reference:

- **Baseline reference** (`reference_kind = "baseline"`) — loaded from
  `metrics.json` (100 repeated benchmark runs).
- **Verified-candidate reference** (`reference_kind = "verified_candidate"`) —
  loaded from `verification.json` (100 repeated benchmark runs).

### Hard Rejection Gates

A candidate is rejected if any of these conditions hold:

- Artifact audit determines the candidate is not comparable to the reference
- Benchmark artifact is missing
- `parse_success` is not `true`
- `parsed_correctness_passed` is not `true` for either the reference or the candidate
- Runtime is missing, zero, negative, non-finite, or otherwise invalid
- `runtime_unit` is not `ns`
- Any of `family`, `solver`, `parsed_num_problems`, `benchmark_options`, or
  `build_type` differ from the reference
- Optional: `parsed_gt_found_percent` drops by more than
  `gt_found_max_drop_points` percentage points (disabled by default, enabled via
  `selection.gt_found_max_drop_points` in the experiment config)

Correctness and comparability are mandatory gates before runtime comparison.

### Runtime Comparison

Primary metric: `parsed_runtime_ns_per_problem_median` — the median of the
repeated `runtime_ns_per_problem_median` samples. Lower values are better.
Mean and max are not decision metrics.

Formulas:

```
speedup = reference_runtime / candidate_runtime
runtime_reduction_percent = ((reference_runtime - candidate_runtime) / reference_runtime) * 100
```

Default thresholds:

| Threshold | Value | Role |
|---|---|---|
| `min_runtime_reduction_percent` | 1.0% | Minimum runtime reduction to accept |
| `immediate_accept_runtime_reduction_percent` | 2.0% | Accept immediately without confirmation |

### Decision Statuses

| Status | Condition |
|---|---|
| `rejected` | Failed any hard rejection gate |
| `valid_not_improved` | Passed all hard gates but is not faster than the reference, or runtime reduction is below 1.0% |
| `confirmation_required` | Runtime reduction ≥ 1.0% but < 2.0% — requires additional verification |
| `accepted_improvement` | Runtime reduction ≥ 2.0% (immediate), or ≥ 1.0% after confirmation |

Candidates below the 1.0% threshold are recorded as `valid_not_improved` with
`non_acceptance_reasons` containing `runtime_improvement_below_minimum_threshold`.
Their `rejection_reasons` remain empty because they passed hard rejection gates.

### Borderline Confirmation

When `confirmation_required`, the runner executes another 100 candidate-only
benchmark runs, merges all 200 candidate samples, recomputes the median, and
re-evaluates the decision. The final stored candidate artifact has
`benchmark_run_count = 200` and a merged 200-sample median.

After confirmation, the candidate is decided as either `accepted_improvement`
or `valid_not_improved`.

See `best_result_selection_policy.md` for the full decision policy reference.

## 6. Closed-Loop Current-Best Promotion

In closed-loop mode, the experiment maintains a mutable experiment-local
`current_best_source` under `workspace/experiments/<experiment_id>/current_best_source/`.
The initial state is a copy of the original `cpp/` tree.

Each iteration produces two decision artifacts:

| Artifact | Location | Role |
|---|---|---|
| `decision_vs_current_best` | Field on `closed_loop_iterations.jsonl` record | Controls promotion |
| `decision_vs_original_baseline.json` | File in candidate run directory | Reporting and traceability only |

Only `decision_vs_current_best` with status `accepted_improvement` triggers
promotion — the candidate's materialized workspace becomes the new
`current_best_source` for the next iteration.

The main `cpp/` source tree is never modified automatically.

### Iteration Statuses

| Status | Meaning |
|---|---|
| `generation_failed` | LLM call or response parsing failed |
| `no_op` | Candidate returned `edits: []` |
| `materialization_failed` | Edits could not be applied |
| `verification_failed` | Build or benchmark failed |
| `rejected` | Failed hard rejection gates |
| `valid_not_improved` | Passed gates but did not beat the current best |
| `accepted_improvement` | Accepted and promoted to current best |

All planned iterations are attempted. There is no early stopping.

### Closed-Loop History

Before later iterations, the runner builds compact history context from previous
meaningful iterations. The history includes summaries, benchmark results, and
deterministic guidance for the LLM. It excludes full code, diffs, logs, and
no-op entries.

The history tells the LLM that it is improving the current best source, not the
original baseline. History context is logged to
`results/experiments/<experiment_id>/logs/iteration_NNN_closed_loop_history_context.txt`.

See `closed_loop_optimization.md` for the full closed-loop reference.

## 7. Final Artifacts and Report

After all iterations complete, the following artifacts are written under
`results/experiments/<experiment_id>/`:

| Artifact | Description |
|---|---|
| `final_optimized_source/` | Copy of the final `current_best_source` tree |
| `final_optimized_source.diff` | Unified diff from original baseline to final optimized source |
| `final_diff_stats.json` | Diff statistics |
| `closed_loop_iterations.jsonl` | Per-iteration JSONL records |
| `closed_loop_summary.json` | Experiment summary with status counts and final best metadata |
| `closed_loop_selection_report.json` | Read-only analysis report (never modifies source) |
| `final_selection_report.json` | Final repeated-median comparison against original baseline |
| `current_best_state.json` | Final current-best metadata (copied to results) |
| `experiment_config_snapshot.json` | Snapshot of the experiment config as run |
| `experiment_config_effective.json` | Effective config with defaults resolved |
| `experiment_metadata.json` | Start/finish timestamps |
| `experiment_status.json` | Final experiment status including closed-loop block |
| `summary.txt` | Human-readable experiment summary |
| `report/` | HTML/PDF report (when reporting is enabled) |

The final best is the last accepted candidate after all iterations, or the
original baseline if no candidate was accepted. There is no separate final
validation benchmark phase — the final comparison uses existing repeated
benchmark artifacts.

Final selection and reporting artifacts are analysis-only. They never promote
candidates, update `current_best_source`, rewrite `final_optimized_source`,
or modify the main `cpp/` source tree.
