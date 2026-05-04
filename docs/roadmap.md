# High-Level Roadmap

## 1. Project Scaffold
- Finalize repository structure, base documentation, and placeholder configuration files.
- Status: completed.

## 2. Baseline Integration
- Integrate imported baseline solver into project-level execution flow boundaries.
- Status: completed at the minimal working baseline level.

## 3. Validation and Benchmarking
- Define validation strategy and benchmarking protocol for baseline and optimized variants.
- Status: started at a minimal level.
- Current state: one smoke test and one simple fixed-input benchmark exist.
- Not complete: full validation, benchmark methodology, datasets, statistics, benchmark runtime parsing, and candidate benchmark execution are not implemented.

## 4. First LLM Integration
- Introduce initial LLM-driven code modification and evaluation loop entry point.
- Status: completed at the first connected-LLM level.
- Current state: DeepSeek V4 Flash is connected through a small standard-library client, controlled optimization prompts can be generated, responses are parsed into validated candidate artifacts, and LLM candidate runs are stored under `results/runs/<run_id>_llm_candidate/`. A deterministic mock LLM config is also available for offline candidate-generation tests without an API key.
- Not complete: generated candidates are not automatically promoted into the main `cpp/` source tree, candidate benchmarks are not run, and candidates are not compared or ranked.

## 4a. Candidate Materialization and Smoke Verification
- Materialize generated candidate diffs only in isolated workspace copies and run a narrow smoke verification.
- Status: started.
- Current state: non-empty candidate diffs can be applied under `workspace/candidates/<candidate_run_id>/`, without modifying the main `cpp/` source tree. Materialized candidates can be configured, built, and smoke-tested through the candidate verification command.
- Not complete: candidate benchmark runs, benchmark parsing, performance comparison, and promotion of accepted candidates are not implemented.

## 5. Iterative Optimization Pipeline
- Build iterative optimization workflow with controlled experiment tracking.
- Status: started.
- Current state: an experiment runner can execute configured candidate-generation iterations, optionally materialize candidates, optionally smoke-verify materialized candidates, and write experiment artifacts under `results/experiments/<experiment_id>/`.
- Not complete: benchmark-based evaluation, run comparison, best candidate selection, and closed-loop optimization with ranking are not implemented.

## 6. Experiment Management and Reporting
- Consolidate experiment metadata, result storage, and reporting outputs.
- Status: started at the storage and experiment-artifact level.
- Current state: baseline runs, LLM candidate runs, and experiment runs write persistent artifacts. Baseline and LLM candidate runs also append compact records to `results/index.jsonl`.
- Not complete: advanced reporting, experiment analysis, benchmark statistics, and candidate comparison reports are not implemented.
