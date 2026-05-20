# High-Level Roadmap

## 1. Project Scaffold

- Finalize repository structure, base documentation, and placeholder configuration files.
- Status: completed.

## 2. Baseline Integration

- Integrate imported baseline solver into project-level execution flow boundaries.
- Status: completed at the minimal working baseline level.

## 3. Validation and Benchmarking

- Define validation strategy and benchmarking protocol for baseline and optimized variants.
- Status: completed for the current Lambda Twist P3P absolute-pose path.
- Current state: Lambda Twist P3P has an adapter validator, family benchmark, parsed baseline metrics, parsed candidate verification metrics, artifact audit, and selection-compatible runtime/correctness fields.
- Not complete: broader datasets, additional solver families, advanced benchmark statistics, and direct JSON metrics output from C++ benchmarks.

## 4. First LLM Integration

- Introduce initial LLM-driven code modification and evaluation loop entry point.
- Status: completed.
- Current state: DeepSeek and mock LLM paths are available, controlled prompt builder is implemented, response parser supports the single line-range edit schema, and candidate artifacts are stored under `results/runs/`.
- Not complete: automatic promotion into the main `cpp/` source tree.

## 4a. Candidate Edit Schema

- Fixed infrastructure using line-numbered prompts, line-range `edits[]` candidates, and deterministic materialization.
- Status: implemented.
- Current state: line-numbered prompts, `edits[]` candidates, `candidate.edits.json`, `candidate.generated.diff`, and the full-cycle line-range materialization path for mock and configured LLM runs.

## 5. Iterative Optimization Pipeline

- Build iterative optimization workflow with controlled experiment tracking.
- Status: implemented at controlled experiment-runner level.
- Current state: single-variant closed-loop optimization, multi-iteration runs, closed-loop history, generation, materialization, verification, and pairwise decisions are implemented.
- Closed-loop state: implemented with experiment-local `current_best_source`, `current_best_state`, generation from the current best via `--source-root`, materialization against the current best via `--base-source-root`, compact benchmark-aware history, and promotion into experiment-local current best using `decision_vs_current_best`.
- Not complete: automatic promotion into the main `cpp/` source tree and multi-variant closed-loop strategy.

## 6. Experiment Management and Reporting

- Consolidate experiment metadata, result storage, and reporting outputs.
- Status: implemented for the current minimal experiment workflow.
- Current state: `experiment_status.json`, `summary.txt`, candidate decisions, final closed-loop artifacts, `final_selection_report.json`, and `closed_loop_selection_report.json` are implemented.
- Closed-loop reporting artifacts include `final_optimized_source/`, `final_optimized_source.diff`, `closed_loop_iterations.jsonl`, `closed_loop_summary.json`, `closed_loop_selection_report.json`, and results-side `current_best_state.json`.
- Not complete: advanced plots, broader statistical reports/dashboards, additional aggregate analyses, and direct JSON metrics output from C++ benchmarks.

## Remaining Future Work

- Automatic promotion into the main `cpp/` source tree.
- Multi-variant closed-loop optimization strategy.
- Additional solver families/adapters.
- Advanced plots, broader statistical reports/dashboards, and additional aggregate analyses.
- Direct JSON metrics output from C++ benchmarks.
