# Experiment Runner

Experiment configs describe closed-loop runs. Candidate representation is not configurable.

## Config Fields

- `experiment_name`: human-readable experiment name.
- `description`: optional description.
- `target_file`: repository-relative source file optimized by the run.
- `baseline_run_dir`: baseline run used as the original comparison reference.
- `candidate_generation.max_source_chars`: source-size guard for LLM prompts.
- `optimization_scope.allowed_files`: files candidates may edit.
- `reporting`: optional report generation settings.
- `variants`: currently one closed-loop variant with LLM config and iteration count.

## Candidate Generation

The runner always invokes `orchestrator.core.llm.generate_candidate` with line-numbered source. The LLM always returns `edits[]` using the fixed line-range schema.

## Materialization

The runner invokes `orchestrator.core.patching.materialize_candidate`, which applies the candidate `edits[]` in an isolated workspace. The main `cpp/` tree is never modified by the experiment runner.

The materializer writes `candidate.generated.diff` after applying edits so reviewers can inspect the resulting source change.
