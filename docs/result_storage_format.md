# Result Storage Format

Results are persisted under `results/`. Candidate workspaces are created under `workspace/` and are regenerable.

## Candidate Runs

LLM candidate runs write:

- `metadata.json`
- `status.json`
- `summary.txt`
- `llm_request.json`
- `llm_response.json`
- `candidate.json`
- `candidate.edits.json`

Materialization writes:

- `materialization.json`
- `apply_candidate.log`
- `candidate.generated.diff` when edits are applied

`candidate.generated.diff` is produced by the infrastructure after edits are materialized. It is an inspection artifact, not an LLM-returned candidate representation.

Verification writes `verification.json`. Its `benchmark` section is a repeated
benchmark artifact: candidate verification runs 100 sequential benchmark
executions, stores `repeated_benchmark_samples`, and uses
`parsed_runtime_ns_per_problem_median` as the median of those sample
`runtime_ns_per_problem_median` values. Borderline 1.0% to under-2.0% candidates
are remeasured with another 100 candidate-only executions; the final stored
candidate artifact then has `benchmark_run_count = 200` and a merged 200-sample
median. Mean and max are not top-level decision/report metrics.

The candidate JSON schema is documented in `candidate_edit_formats.md`.

## Experiment Results

Closed-loop experiment results include:

- `experiment_config_snapshot.json`
- `experiment_config_effective.json`
- `experiment_metadata.json`
- `experiment_status.json`
- `closed_loop_iterations.jsonl`
- `closed_loop_summary.json`
- `closed_loop_selection_report.json`
- `current_best_state.json`
- `final_optimized_source/`
- `final_optimized_source.diff`
- `final_diff_stats.json`
- `report/` when reporting is enabled

Experiment metadata and report data may have their own storage schema identifiers. Those identifiers are artifact contracts and are unrelated to the LLM candidate schema.

Baseline run `metrics.json` uses the same repeated benchmark artifact schema in
its `benchmark` section. Baseline benchmark measurement always runs 100
sequential benchmark executions.

The final best is the last accepted candidate/current best after iterations.
There is no separate final validation benchmark phase.
