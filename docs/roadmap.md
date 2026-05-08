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
- Current state: Lambda Twist P3P has a smoke test, adapter validator, family benchmark, parsed baseline metrics, parsed candidate verification metrics, artifact audit, and selection-compatible runtime/correctness fields.
- Not complete: broader datasets, additional solver families, advanced benchmark statistics, and direct JSON metrics output from C++ benchmarks.

## 4. First LLM Integration

- Introduce initial LLM-driven code modification and evaluation loop entry point.
- Status: completed.
- Current state: DeepSeek and mock LLM paths are available, controlled prompt builder is implemented, response parser supports `unified_diff` and `line_range_edits`, and candidate artifacts are stored under `results/runs/`.
- Not complete: automatic promotion into the main `cpp/` source tree.

## 4a. Candidate Materialization and Benchmark Verification

- Materialize generated candidates only in isolated workspace copies and run deterministic benchmark-family verification.
- Status: completed for the minimal P3P scenario.
- Current state: `unified_diff` materialization works with `git apply` and `--recount` fallback. `line_range_edits` materialization works with deterministic line-range edits. Candidate verification runs smoke test, adapter validator, benchmark, and benchmark parser.
- Not complete: promotion.

## 4b. Candidate Edit Format Layer

- Separate semantic optimization from mechanical patch application.
- Status: implemented.
- Current state: `candidate_format` config support, `plain`/`unified_diff` path, `line_numbered`/`line_range_edits` path, `candidate.edits.json` artifact, `candidate.generated.diff` artifact, and real DeepSeek Pro Max `line_range_edits` full-cycle completion.

## 5. Iterative Optimization Pipeline

- Build iterative optimization workflow with controlled experiment tracking.
- Status: implemented at controlled experiment-runner level.
- Current state: multi-variant runs, multi-iteration runs, variant-local history, generation, materialization, verification, pairwise decisions, and best-candidate selection are implemented.
- Not complete: closed-loop automatic promotion/reuse based on selected candidate.

## 6. Experiment Management and Reporting

- Consolidate experiment metadata, result storage, and reporting outputs.
- Status: partially implemented.
- Current state: experiment artifacts, `iterations.jsonl`, `experiment_status.json`, `summary.txt`, candidate decisions, and `best_candidate_selection.json` are implemented.
- Not complete: advanced reporting, plots, final aggregated tables/statistics, and broader experiment analysis.