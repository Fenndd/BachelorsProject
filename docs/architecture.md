# Architecture

This project uses C++ for the algorithmic layer and Python for automation around baseline preparation, LLM candidate generation, candidate materialization, verification, decisions, and closed-loop experiment orchestration.

The C++ benchmark layer supports two backends:

- **`absolute_pose`**: a generated backend for the Lambda Twist P3P minimal
  solver (adapter validation + absolute-pose family benchmark).
- **`poselib_native`**: a backend that reuses PoseLib's benchmark
  infrastructure for 37 PoseLib minimal-solver cases through a
  `poselib_solver_benchmark` target and `--solver` flag.

Solver support is declared through per-solver JSON manifests under
`cpp/bench/absolute_pose/solvers/` and `cpp/bench/poselib_native/solvers/`.
The solver registry (`solver_registry.py`) loads these manifests at import
time and provides descriptors that drive baseline builds, candidate
verification, and closed-loop experiment dispatch.

## Baseline Boundary

The clean baseline path:

1. CMake configures the C++ project.
2. The appropriate benchmark targets are built (depends on the selected
   solver's manifest).
3. For `absolute_pose` solvers: an adapter validator and family benchmark
   execute from `orchestrator/cli/main.py`.
4. For `poselib_native` solvers: the `poselib_solver_benchmark` binary runs
   with `--solver <key>` and prints machine-readable JSON output.
5. Parsed benchmark metrics are stored under `results/runs/<run_id>/` and
   indexed in `results/index.jsonl`.

The C++ baseline boundary:

- `cpp/external/lambdatwist/`: imported third-party Lambda Twist source.
- `cpp/external/poselib/`: imported third-party PoseLib source.
- `lambdatwist_baseline` / `poselib_solver_benchmark`: project CMake targets
  wrapping the imported solver libraries.
- `absolute_pose_lambdatwist_adapter_validator`: project-owned validator
  target (absolute_pose backend only).
- `absolute_pose_lambdatwist_benchmark`: project-owned benchmark-family
  evaluation entry point (absolute_pose backend only).

The baseline Python entry point is `orchestrator/cli/main.py`. It remains
separate from LLM optimization experiments. The `--solver` flag selects
which solver is benchmarked.

## Python Orchestration Components

The main orchestration components are:

- `orchestrator.core.llm.generate_candidate`: reads one source file from a configurable source root, builds a controlled prompt, calls the configured LLM or mock client, parses the response, and stores candidate artifacts.
- `orchestrator.core.patching.materialize_candidate`: materializes a candidate inside `workspace/candidates/<candidate_run_id>/` only, optionally using an explicit `--base-source-root`.
- `orchestrator.core.execution.verify_candidate`: runs deterministic adapter validation, family benchmark, and benchmark parsing inside a materialized candidate workspace.
- `orchestrator.core.benchmarking.candidate_decision`: evaluates one verified candidate against either a baseline run or a verified-candidate reference. In closed-loop mode, the runner records the `decision_vs_current_best` outcome on each iteration record and writes `decision_vs_original_baseline.json` to disk.
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

## Config Builder

The TUI includes an interactive Config Builder screen (accessible via the
**Build Config** button on MainScreen). It lets users create and edit
experiment JSON configs without manual JSON editing. Saved configs are
validated through `load_experiment_config` and stored under
`configs/experiments/local/`. See `docs/config_builder.md` for the full
reference.

## Parallel TUI Runs

Experiment runs are non-blocking. Multiple experiments can run in parallel.
The `ActiveRunsManager` (owned by the TUI app) manages lifecycle, output
streaming, cancellation, and the Active Runs panel on MainScreen. Users can
leave the live output screen without cancelling the run and reopen it later.
Quitting the TUI while runs are active triggers a confirmation dialog. See
`docs/parallel_runs.md` for details.

## Scope and Verification

Configured experiments pass `optimization_scope.allowed_files` to candidate
generation and materialization. The materializer enforces candidate
`target_files` and `edits[].file` paths against that allowlist.

Verification produces `verification.json` using the solver descriptor from
the registry. For `absolute_pose` solvers, this runs adapter validation then
the family benchmark. For `poselib_native` solvers, this builds and runs the
`poselib_solver_benchmark` with the solver's `--solver <key>`. Verification
does not compare against a reference; decisions and selection are separate
stages that consume verified artifacts.

## Closed-loop Iterative Optimization

Closed-loop optimization improves an experiment-local `current_best_source`
tree rather than repeatedly optimizing the original baseline. Each iteration
generates, materializes, and verifies one candidate against the current best.
The `decision_vs_current_best` outcome on each iteration record controls
whether the candidate is promoted into `current_best_source` for the next
iteration. `decision_vs_original_baseline.json` is retained for reporting only
and does not control promotion. The main `cpp/` source tree is never modified
automatically.

See `docs/closed_loop_optimization.md` for the full reference on the control
flow, source-root separation, history, iteration statuses, decision artifacts,
and final artifacts.

## Result Boundaries

Persistent artifacts are written under `results/`. Temporary and mutable
source copies are written under `workspace/`. Generated experiment outputs
are ignored by git.

Per-iteration closed-loop artifacts are stored under experiment-scoped
prefixes:

- Candidate runs: `results/runs/<experiment_id>/it_01/`, `it_02/`, ...
- Candidate workspaces: `workspace/candidates/<experiment_id>/it_01/`, ...
- Current best source: `workspace/experiments/<experiment_id>/current_best_source/`
- Current best state: `workspace/experiments/<experiment_id>/current_best_state.json`

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

- Automatic promotion of candidates into the main `cpp/` source tree is not
  implemented.
- Closed-loop mode currently supports exactly one variant; multi-variant
  closed-loop strategy is not implemented.
- Robust estimator support is not the current benchmark target; the
  pipeline focuses on minimal-solver performance.
- Advanced plots and broader statistical dashboards or aggregate analyses
  across multiple experiments are future work.
