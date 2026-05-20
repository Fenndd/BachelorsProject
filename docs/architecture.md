# Architecture

This project uses C++ for the algorithmic layer and Python for automation around baseline preparation, LLM candidate generation, candidate materialization, verification, decisions, and closed-loop experiment orchestration.

The current minimal case study is Lambda Twist P3P in the absolute-pose solver benchmark family.

## Baseline Boundary

The clean baseline path is:

1. CMake configures the C++ project.
2. The Lambda Twist baseline target and project-owned executables are built.
3. A runner, adapter validator, and absolute-pose family benchmark execute from `orchestrator/cli/main.py`.
4. Parsed benchmark metrics are stored under `results/runs/<run_id>/` and indexed in `results/index.jsonl`.

The C++ baseline boundary is:

- `cpp/external/lambdatwist/`: imported third-party Lambda Twist source.
- `lambdatwist_baseline`: project CMake target wrapping the imported solver.
- `baseline_runner`: project-owned compatibility entry point.
- `baseline_benchmark`: old compatibility benchmark target, still kept building.
- `absolute_pose_lambdatwist_adapter_validator` and `absolute_pose_lambdatwist_benchmark`: project-owned benchmark-family evaluation entry points.

The baseline Python entry point is `orchestrator/cli/main.py`. It remains separate from LLM optimization experiments.

## Python Orchestration Components

The main orchestration components are:

- `orchestrator.llm.generate_candidate`: reads one source file from a configurable source root, builds a controlled prompt, calls the configured LLM or mock client, parses the response, and stores candidate artifacts.
- `orchestrator.patching.materialize_candidate`: materializes a candidate inside `workspace/candidates/<candidate_run_id>/` only, optionally using an explicit `--base-source-root`.
- `orchestrator.execution.verify_candidate`: runs deterministic adapter validation, family benchmark, and benchmark parsing inside a materialized candidate workspace.
- `orchestrator.benchmarking.candidate_decision`: evaluates one verified candidate against either a baseline run or a verified-candidate reference. In closed-loop mode, this writes reference-vs-candidate decisions such as `decision_vs_current_best.json`.
- `orchestrator.experiments.closed_loop_state`: manages experiment-local `current_best_source` and `current_best_state` metadata.
- `orchestrator.experiments.closed_loop_history`: builds compact benchmark-aware history for later closed-loop generations.
- `orchestrator.experiments.run_experiment`: runs configured closed-loop iterative optimization experiments.
- Final closed-loop artifact/reporting helpers write `final_optimized_source/`, `final_optimized_source.diff`, `closed_loop_summary.json`, `closed_loop_iterations.jsonl`, `closed_loop_selection_report.json`, and the results-side `current_best_state.json`.

Experiment runs use `workspace/` for isolated source copies and `results/` for persistent outputs. The main `cpp/` source tree is not modified by candidate materialization or closed-loop current-best promotion.

## Candidate Edit Layer

The system uses one fixed LLM candidate representation: line-range edits. This is infrastructure behavior, not an experiment config option.

- The LLM receives source with 1-based line numbers.
- The LLM returns `edits[]` with `file`, `start_line`, `end_line`, `original`, and `replace`.
- `original` is source text only and must not include line-number prefixes.
- The materializer verifies the actual source text at the requested line range before applying.
- An internal exact-search fallback may be used only when the `original` text occurs exactly once.
- The system writes `candidate.generated.diff` after deterministic materialization.
- The main `cpp/` source tree is never modified.

See `docs/candidate_edit_formats.md` for the dedicated format reference.

## Scope and Verification

Configured experiments pass `optimization_scope.allowed_files` to candidate generation and materialization. The materializer enforces candidate `target_files` and `edits[].file` paths against that allowlist.

Verification produces `verification.json` using the same absolute-pose benchmark family as the baseline. Verification does not compare against a reference; decisions and selection are separate stages that consume verified artifacts.

## Closed-loop Iterative Optimization

Closed-loop optimization is implemented in the experiment runner. It improves an experiment-local current best source tree rather than repeatedly optimizing the original baseline.

The core flow is:

```text
original clean baseline
  -> workspace/experiments/<experiment_id>/current_best_source/
  -> generate candidate from current_best_source
  -> materialize candidate against current_best_source
  -> verify candidate
  -> decision_vs_current_best
  -> optional current_best_source update
  -> next iteration
```

### Experiment-local current best

At experiment start, closed-loop mode initializes:

```text
workspace/experiments/<experiment_id>/current_best_source/
workspace/experiments/<experiment_id>/current_best_state.json
```

`current_best_source/` is a repo-like tree populated from the clean baseline source, for example:

```text
workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc
```

When a candidate is accepted as an improvement, the materialized candidate workspace replaces this experiment-local current-best tree and `current_best_state.json` is updated. The main `cpp/` tree remains the clean baseline and is never modified automatically.

### Source-root separation

Closed-loop mode separates logical candidate paths from physical source roots:

- `target_file` remains the stable repo-relative path, such as `cpp/external/lambdatwist/p3p.cc`.
- `generate_candidate` uses `--source-root workspace/experiments/<experiment_id>/current_best_source` to read the current source while preserving logical candidate paths.
- `materialize_candidate` uses `--base-source-root workspace/experiments/<experiment_id>/current_best_source` so the candidate is applied against the same source version the LLM saw.

This keeps candidate metadata, `target_files`, and `allowed_files` repo-relative while allowing the physical source to advance between iterations.

### Decision semantics

Closed-loop mode writes two reference comparisons for verified candidates:

- `decision_vs_current_best.json`: the control decision. Only `status: "accepted_improvement"` promotes the candidate into experiment-local `current_best_source`.
- `decision_vs_original_baseline.json`: reporting/control against the original baseline. It does not control promotion.

After all iterations, `closed_loop_selection_report.json` provides final analysis only. It never promotes candidates, rewrites `current_best_source`, rewrites `final_optimized_source`, or modifies the main `cpp/` tree.

Closed-loop mode currently supports exactly one variant. Multi-variant closed-loop strategy and automatic promotion into the main `cpp/` source tree remain limitations.

## Result Boundaries

Persistent artifacts are written under `results/`. Temporary and mutable source copies are written under `workspace/`. Generated experiment outputs are ignored by git.

Final closed-loop artifacts are stored under:

```text
results/experiments/<experiment_id>/final_optimized_source/
results/experiments/<experiment_id>/final_optimized_source.diff
results/experiments/<experiment_id>/closed_loop_summary.json
results/experiments/<experiment_id>/closed_loop_iterations.jsonl
results/experiments/<experiment_id>/closed_loop_selection_report.json
results/experiments/<experiment_id>/current_best_state.json
```

## Current Limitations

- Automatic promotion of candidates into the main `cpp/` source tree is not implemented.
- Closed-loop mode currently supports exactly one variant; multi-variant closed-loop strategy is not implemented.
- Additional solver families/adapters beyond the current minimal Lambda Twist P3P path are future work.
- Advanced plots and broader statistical dashboards or aggregate analyses are future work.
