# Architecture

This project uses C++ for the algorithmic layer and Python for automation around baseline preparation, LLM candidate generation, candidate materialization, verification, and selection.

The current minimal case study is Lambda Twist P3P in the absolute-pose solver benchmark family.

## Baseline Boundary

The clean baseline path is:

1. CMake configures the C++ project.
2. The Lambda Twist baseline target and project-owned executables are built.
3. A smoke test, runner, adapter validator, and absolute-pose family benchmark execute from `orchestrator/cli/main.py`.
4. Parsed benchmark metrics are stored under `results/runs/<run_id>/` and indexed in `results/index.jsonl`.

The C++ baseline boundary is:

- `cpp/external/lambdatwist/`: imported third-party Lambda Twist source.
- `lambdatwist_baseline`: project CMake target wrapping the imported solver.
- `baseline_runner` and `baseline_smoke_test`: project-owned compatibility entry points.
- `baseline_benchmark`: old compatibility benchmark target, still kept building.
- `absolute_pose_lambdatwist_adapter_validator` and `absolute_pose_lambdatwist_benchmark`: project-owned benchmark-family evaluation entry points.

The baseline Python entry point is `orchestrator/cli/main.py`. It remains separate from LLM optimization experiments.

## LLM Experiment Commands

The main implemented orchestration commands are:

- `orchestrator.llm.generate_candidate`: reads one source file, builds a controlled prompt, calls the configured LLM or mock client, parses the response, and stores candidate artifacts.
- `orchestrator.patching.materialize_candidate`: materializes a candidate inside `workspace/candidates/<candidate_run_id>/` only.
- `orchestrator.execution.verify_candidate`: runs deterministic smoke, adapter validation, family benchmark, and benchmark parsing inside a materialized candidate workspace.
- `orchestrator.experiments.run_experiment`: runs configured multi-variant/multi-iteration candidate generation, optional materialization, optional verification, history, and selection.
- `orchestrator.benchmarking.candidate_decision`: evaluates one verified candidate against one baseline artifact.
- `orchestrator.experiments.best_candidate_selector`: selects the best candidate among verified candidates using pairwise decisions.

Experiment runs use `workspace/` for isolated candidate copies and `results/` for persistent outputs. The main `cpp/` source tree is not modified by candidate materialization.

## Candidate Edit Format Layer

The system no longer assumes every LLM candidate is a raw unified diff. Candidate format is selected through experiment config using `candidate_format`.

### `unified_diff`

- `schema_version`: `1.0`
- Legacy/fallback format.
- The LLM returns a `unified_diff` string.
- `generate_candidate` writes `candidate.diff`.
- The materializer applies the patch with `git apply`.
- If normal hunk-count validation fails, the materializer can try `git apply --recount` and records whether the recount fallback was used.

### `line_range_edits`

- `schema_version`: `1.1`
- Preferred robust format for real LLM experiments.
- The LLM receives `line_numbered` source.
- The LLM returns `edits[]` with `file`, `start_line`, `end_line`, `original`, and `replace`.
- `original` is source text only and must not include line-number prefixes.
- The materializer verifies the actual source text at the requested line range before applying.
- If enabled, an exact-search fallback may be used only when the `original` text occurs exactly once.
- The system writes `candidate.generated.diff` after deterministic materialization.
- The main `cpp/` source tree is never modified.

See `docs/candidate_edit_formats.md` for the dedicated format reference.

## Scope and Selection

Configured experiments pass `optimization_scope.allowed_files` to candidate generation and materialization. The materializer enforces candidate `target_files` plus format-specific changed-file paths against that allowlist:

- `unified_diff`: diff header paths are checked.
- `line_range_edits`: `edits[].file` paths are checked.

Verification produces `verification.json` using the same absolute-pose benchmark family as the baseline. Pairwise candidate decision and multi-candidate best-result selection are implemented in Python and consume verified artifacts. Selection does not promote code.

## Not Implemented Yet

- Automatic promotion of candidates into the main source tree.
- Closed-loop optimization that automatically promotes or reuses selected candidates.
- Advanced reporting, plots, and final aggregated analysis.
- Additional solver families/adapters beyond the current minimal Lambda Twist P3P path.
