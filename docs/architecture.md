# Architecture

This project uses C++ for the algorithmic layer and Python for automation around baseline preparation, LLM candidate generation, candidate materialization, verification, decisions, and closed-loop experiment orchestration.

The C++ benchmark layer supports one backend:

- **`poselib_native`**: a backend that reuses PoseLib's benchmark
  infrastructure for PoseLib minimal-solver cases through a
  `poselib_solver_benchmark` target and `--solver` flag.

Solver support is declared through per-solver JSON manifests under
`cpp/bench/poselib_native/solvers/`.
The solver registry (`solver_registry.py`) loads these manifests at import
time and provides descriptors that drive baseline builds, candidate
verification, and closed-loop experiment dispatch.

## Baseline Boundary

The clean baseline path:

1. CMake configures the C++ project.
2. The `poselib_solver_benchmark` target is built.
3. The `poselib_solver_benchmark` binary runs
   with `--solver <key>` and prints machine-readable JSON output.
4. The benchmark executable runs multiple times sequentially. Parsed samples are
   aggregated by median of `runtime_ns_per_problem_median`.
5. Parsed benchmark metrics are stored under `results/runs/<run_id>/` and
   indexed in `results/index.jsonl`.

The C++ baseline boundary:

- `cpp/external/poselib/`: imported third-party PoseLib source.
- `poselib_solver_benchmark`: project CMake target wrapping PoseLib's solver
  benchmark.

The baseline Python entry point is `orchestrator/cli/main.py`. It remains
separate from LLM optimization experiments. The `--solver` flag selects
which solver is benchmarked.

## Python Orchestration Components

The main orchestration components are:

- `orchestrator.core.llm.generate_candidate`: reads one source file from a configurable source root, builds a controlled prompt, calls the configured LLM or mock client, parses the response, and stores candidate artifacts.
- `orchestrator.core.patching.materialize_candidate`: materializes a candidate inside `workspace/candidates/<candidate_run_id>/` only, optionally using an explicit `--base-source-root`.
- `orchestrator.core.execution.verify_candidate`: runs deterministic adapter validation, 100 sequential family benchmark executions, and repeated-median benchmark parsing inside a materialized candidate workspace.
- `orchestrator.core.benchmarking.candidate_decision`: evaluates one verified candidate against either a baseline run or a verified-candidate reference. In closed-loop mode, the runner records the `decision_vs_current_best` outcome on each iteration record and writes `decision_vs_original_baseline.json` to disk.
- `orchestrator.experiments.closed_loop_state`: manages experiment-local `current_best_source` and `current_best_state` metadata.
- `orchestrator.experiments.closed_loop_history`: builds compact benchmark-aware history for later closed-loop generations.
- `orchestrator.experiments.run_experiment`: runs configured closed-loop iterative optimization experiments.
- Final closed-loop artifact/reporting helpers write `final_optimized_source/`, `final_optimized_source.diff`, `closed_loop_summary.json`, `closed_loop_iterations.jsonl`, `closed_loop_selection_report.json`, and the results-side `current_best_state.json`.

Experiment runs use `workspace/` for isolated source copies and `results/` for persistent outputs. The main `cpp/` source tree is not modified by candidate materialization or closed-loop current-best promotion.

## Candidate Edit Layer

The system uses one fixed LLM candidate representation: line-range edits. This is infrastructure behavior, not an experiment config option.

- The LLM receives source with 1-based line numbers.
- The LLM returns `edits[]` with `start_line`, `end_line`, `original`, and `replace`. Edits do not contain a `file` field; the materializer associates all edits with the configured `target_file`.
- `original` is source text only and must not include line-number prefixes.
- The materializer verifies the actual source text at the requested line range before applying.
- An internal exact-search fallback may be used only when the `original` text occurs exactly once.
- The system writes `candidate.generated.diff` after deterministic materialization.
- The main `cpp/` source tree is never modified.

See `docs/candidate_edit_formats.md` for the dedicated format reference.

## Scope and Verification

Configured experiments pass `optimization_scope.allowed_files` to candidate
generation and materialization. The materializer enforces that all edit target
files fall within that allowlist.

Verification produces `verification.json` using the solver descriptor from
the registry. It builds and runs the `poselib_solver_benchmark` with the solver's `--solver <key>`
sequentially. Verification does not compare against a reference;
decisions and selection are separate stages that consume verified repeated-median
artifacts.

## Closed-loop Iterative Optimization

Closed-loop optimization improves an experiment-local `current_best_source`
tree rather than repeatedly optimizing the original baseline. Each iteration
generates, materializes, and verifies one candidate against the current best.
The `decision_vs_current_best` outcome on each iteration record controls
whether the candidate is promoted into `current_best_source` for the next
iteration. `decision_vs_original_baseline.json` is retained for reporting only
and does not control promotion. The main `cpp/` source tree is never modified
automatically.

Decision thresholds and remeasurement rules are documented separately.

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


