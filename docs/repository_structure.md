# Repository Structure

## Directory Roles

- `cpp/`: C++ code area for project algorithm integration, project-owned runner/test/benchmark targets, and shared baseline sample data.
- `cpp/external/`: third-party imported baselines and dependencies.
- `orchestrator/`: Python automation code for baseline runs, LLM candidate generation, materialization, verification, candidate decisions, best-candidate selection, and experiment orchestration.
- `configs/`: LLM configs, mock candidate configs, model/default configs, and experiment configs, including `candidate_format` selection.
- `workspace/`: isolated temporary candidate workspaces created by materialization.
- `results/`: persistent baseline, candidate generation, materialization, verification, decision, selection, and experiment artifacts.
- `docs/`: architecture notes, roadmap, setup, and repository-level conventions.
- `scripts/`: helper scripts for maintenance and utility tasks.

## Data and Code Boundaries

- External third-party code: imported baseline implementations in `cpp/external/`.
- Project source code: project-owned implementation and orchestration logic outside third-party imports.
- Temporary workspace data: isolated candidate copies in `workspace/` that can be regenerated.
- Persistent experiment results: stored outputs in `results/` used for comparison, selection, analysis, and reporting.

## Baseline Ownership Policy

- `cpp/external/lambdatwist/` is imported third-party baseline code.
- It must not be treated as original project source code.
- In a clean repository state, imported baseline files should remain unchanged.
- Candidate modifications happen in isolated workspace copies unless future explicit promotion support is implemented.
