# Closed-loop Optimization

## Purpose

Closed-loop optimization lets each iteration improve the current best accepted source instead of always starting from the original clean baseline. This allows later LLM generations to build on accepted improvements while keeping the repository `cpp/` tree unchanged.

The mutable source state is experiment-local. Accepted candidates update `workspace/experiments/<experiment_id>/current_best_source/`, not the main source tree.

## Core Flow

The implemented closed-loop flow is:

```text
original baseline
  -> current_best_source
  -> generation
  -> materialization
  -> verification
  -> decision_vs_current_best
  -> optional promotion
  -> next iteration
```

At the start of a closed-loop experiment, `current_best_source` is initialized from the clean baseline. Each planned iteration attempts to generate, materialize, and verify one candidate. If the candidate is a verified improvement over the current best, it is promoted into the experiment-local current best and becomes the source for the next iteration.

## Source Roots

Closed-loop mode separates logical repository paths from physical source roots:

- The logical `target_file` remains repo-relative, for example `cpp/external/lambdatwist/p3p.cc`.
- `generate_candidate` uses `--source-root workspace/experiments/<experiment_id>/current_best_source` to read the active source text.
- `materialize_candidate` uses `--base-source-root workspace/experiments/<experiment_id>/current_best_source` to apply the candidate against the same source version the LLM saw.
- Candidate `target_files`, `allowed_files`, prompt metadata, and decision artifacts continue to use logical repo-relative paths.
- The main `cpp/` source tree is not modified automatically.

This separation keeps artifacts stable and repo-relative while allowing the physical source for later iterations to advance through accepted candidates.

## Current Best State

The mutable closed-loop source state is stored under the experiment workspace:

```text
workspace/experiments/<experiment_id>/current_best_source/
workspace/experiments/<experiment_id>/current_best_state.json
```

At finalization, a copy of the final current-best metadata is also written under the experiment results directory:

```text
results/experiments/<experiment_id>/current_best_state.json
```

`current_best_source/` is a repo-like tree. For the current P3P target, the active source file is stored at:

```text
workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc
```

## Iteration Statuses

Closed-loop iteration records can use these statuses:

- `accepted_improvement`
- `valid_not_improved`
- `rejected`
- `materialization_failed`
- `verification_failed`
- `no_op`
- `generation_failed`

Only `accepted_improvement` updates `current_best_source`. A verified candidate
must pass correctness/comparability gates and reduce runtime by at least the
default `min_runtime_reduction_percent = 0.5` to be accepted. Faster candidates
below that threshold are `valid_not_improved` and are not promoted. Such
candidates are valid rather than rejected; their decision artifacts use
`non_acceptance_reasons`, for example
`runtime_improvement_below_minimum_threshold`, while `rejection_reasons` stays
reserved for hard rejection/correctness/audit failures.

## Decision Artifacts

Closed-loop verified candidates write two reference decision artifacts in the candidate run directory:

- `decision_vs_current_best.json`: controls promotion. If its status is `accepted_improvement`, the candidate becomes the new experiment-local current best.
- `decision_vs_original_baseline.json`: compares the candidate against the original clean baseline for reporting/control. It does not control promotion.

Compatibility/default selection artifacts may also appear when useful:

- `candidate_decision.json`: default pairwise decision filename used by the baseline-vs-candidate path.
- `best_candidate_selection.json`: non-closed-loop best-candidate selection output when that selection path is enabled.

Closed-loop final analysis is written to `closed_loop_selection_report.json`. It reports the final state and safety flags, but it never promotes candidates or modifies source trees.

## Compact History

Before later closed-loop generations, the runner builds compact benchmark-aware history from previous meaningful iterations. The history tells the LLM that it is improving the current best source, not the original baseline.

Included statuses:

- `accepted_improvement`
- `valid_not_improved`
- `rejected`
- `materialization_failed` with usable candidate information
- `verification_failed` with usable candidate information

Excluded statuses:

- `no_op`
- generation failures without a usable candidate

The compact history contains summaries, benchmark-aware result text, short failure or rejection reasons, and deterministic guidance. It does not include full code, full diffs, full `candidate.json`, full `verification.json`, benchmark logs, audit objects, stack traces, or no-op entries.

For materialization failures, compact history uses generic deterministic
guidance when it can identify ambiguous repeated original text, line-range
original mismatches, or disabled fallback. It does not implement repeated failure
grouping/detection, LLM-based failure summaries, or special-case repair logic.

The exact history context passed to generation is logged under:

```text
results/experiments/<experiment_id>/logs/iteration_003_closed_loop_history_context.txt
```

## Final Artifacts

Closed-loop final artifacts are written under:

```text
results/experiments/<experiment_id>/
```

Key artifacts are:

- `final_optimized_source/`: copy of the final `current_best_source/` tree.
- `final_optimized_source.diff`: unified diff from the original clean baseline to the final optimized source.
- `closed_loop_iterations.jsonl`: compact per-iteration JSONL records.
- `closed_loop_summary.json`: summary of final best iteration, accepted improvements, status counts, final repeated-validation metrics when available, and final artifact paths.
- `closed_loop_selection_report.json`: analysis-only final report that separates promotion decisions from final analysis.
- `summary.txt`: human-readable experiment summary with a closed-loop section.
- `experiment_status.json`: includes a `closed_loop` block with final artifact paths, final best metadata, accepted improvement count, final repeated-validation metrics, and status counts.

`candidate.generated.diff` and `final_optimized_source.diff` have different meanings:

- `candidate.generated.diff` is an iteration-local diff from that iteration's base/current-best source to the materialized candidate.
- `final_optimized_source.diff` is the final diff from the original clean baseline to the final optimized source.

## Safety Invariants

- The main `cpp/` source tree is never modified automatically.
- `current_best_source` is updated only after `accepted_improvement`.
- `decision_vs_original_baseline.json` is reporting/control only and does not promote candidates.
- The final selector/report never promotes candidates or modifies source.
- All planned iterations are attempted; there is no early stopping.

## Current Limitations

- Exactly one variant is supported in closed-loop mode.
- Automatic promotion into the main `cpp/` source tree is not implemented.
- Multi-variant closed-loop strategy is not implemented.
- Additional solver families beyond the current minimal Lambda Twist P3P path are not implemented.
- Candidate acceptance uses lower median runtime plus a default 0.5% minimum runtime-reduction threshold after correctness and comparability gates. Repeated-benchmark confidence policies are not implemented.
- Pairwise correctness is benchmark-defined and absolute: both artifacts must have `parsed_correctness_passed == true`.
- Line-number mismatch diagnosis is not implemented as a special repair mechanism.
- The current minimal P3P prototype focuses on runtime and PoseLib-style calibrated-pose correctness metrics. Memory measurement is not implemented yet and remains future optional work.
