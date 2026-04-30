# Repository Structure

## Directory Roles

- `cpp/`: C++ code area for project algorithm integration, project-owned runner/test/benchmark targets, and shared baseline sample data.
- `cpp/external/`: third-party imported baselines and dependencies.
- `orchestrator/`: Python automation code, including the minimal baseline CLI entry point and future workflow modules.
- `configs/`: placeholder configuration files for defaults, experiments, and model settings.
- `workspace/`: reserved temporary run directory for future experiment execution.
- `results/`: reserved persistent output directory for future analysis and reporting.
- `docs/`: architecture notes, roadmap, and repository-level conventions.
- `scripts/`: helper scripts for maintenance and utility tasks.

## Data and Code Boundaries

- External third-party code: imported baseline implementations in `cpp/external/` (not authored as original project code).
- Project source code: project-owned implementation and orchestration logic outside third-party imports.
- Temporary workspace data: future ephemeral run artifacts in `workspace/` that can be regenerated.
- Persistent experiment results: future stored outputs in `results/` kept for comparison, analysis, and reporting.

## Baseline Ownership Policy

- `cpp/external/lambdatwist/` is imported third-party baseline code.
- It must not be treated as original project source code.
- In a clean repository state, imported baseline files should remain unchanged.
- Future experiment modifications should happen outside the clean baseline, for example via project-owned wrappers or workspace copies.
