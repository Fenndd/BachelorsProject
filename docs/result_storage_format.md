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

## Candidate Schema

Candidates use one fixed line-range edit schema:

- `summary`
- `rationale`
- `risk_level`
- `expected_effect`
- `target_files`
- `correctness_notes`
- `edits`
- `requires_manual_review`

Each edit contains `file`, `start_line`, `end_line`, `original`, and `replace`.

No-op candidates set `expected_effect` to `none` and return `edits: []`.

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
