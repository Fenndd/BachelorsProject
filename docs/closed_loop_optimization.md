# Closed-loop Optimization

## Purpose

Closed-loop optimization lets each iteration improve the current best accepted source instead of always starting from the original clean baseline. This allows later LLM generations to build on accepted improvements while keeping the repository `cpp/` tree unchanged.

The mutable source state is experiment-local. Accepted candidates update `workspace/experiments/<experiment_id>/current_best_source/`, not the main source tree.

For the full pipeline overview including baseline benchmarking, generation, materialization, verification, and final artifacts, see `experiment_workflow.md`.

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

## Closed-loop History in Prompts

Closed-loop optimization always includes compact previous-iteration history in later LLM prompts. Each generation receives the iteration number, status, phase durations, verification metrics, and deterministic guidance. This helps later iterations understand what was attempted and avoid redundant or failing approaches.

## Source Roots

Closed-loop mode separates logical repository paths from physical source roots:

- The logical `target_file` remains repo-relative, for example `cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc`.
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
workspace/experiments/<experiment_id>/current_best_source/cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc
```

## Iteration Statuses

Only `accepted_improvement` updates `current_best_source`. Acceptance criteria and
decision thresholds are defined in `best_result_selection_policy.md`.

## Decision Artifacts

For each verified candidate, the closed-loop runner records the
`decision_vs_current_best` outcome as a field on the iteration record
(stored in `closed_loop_iterations.jsonl`). It also writes
`decision_vs_original_baseline.json` as a file in the candidate run directory.

- `decision_vs_current_best` (iteration record field): controls promotion. If
  its value is `accepted_improvement`, the candidate becomes the new
  experiment-local current best.
- `decision_vs_original_baseline.json` (file): compares the candidate against
  the original clean baseline for reporting/control. It does not control
  promotion.

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

For materialization failures, compact history includes generic deterministic
guidance identifying the failure pattern (ambiguous repeated text, line-range
mismatch, disabled fallback, or fallback with no match).

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
- `closed_loop_summary.json`: summary of final best iteration, accepted improvements, status counts, and final artifact paths.
- `closed_loop_selection_report.json`: analysis-only final report that separates promotion decisions from final analysis.
- `summary.txt`: human-readable experiment summary with a closed-loop section.
- `experiment_status.json`: includes a `closed_loop` block with final artifact paths, final best metadata, accepted improvement count, and status counts.

`candidate.generated.diff` and `final_optimized_source.diff` have different meanings:

- `candidate.generated.diff` is an iteration-local diff from that iteration's base/current-best source to the materialized candidate.
- `final_optimized_source.diff` is the final diff from the original clean baseline to the final optimized source.

## Safety Invariants

- The main `cpp/` source tree is never modified automatically.
- `current_best_source` is updated only after `accepted_improvement`.
- `decision_vs_original_baseline.json` is reporting/control only and does not promote candidates.
- The final selector/report never reruns benchmarks, promotes candidates, or modifies source.
- All planned iterations are attempted; there is no early stopping.
