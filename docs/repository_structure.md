# Repository Structure

## Directory Roles

- `cpp/`: C++ code area for project algorithm integration, project-owned wrappers, and future validation assets.
- `cpp/external/`: third-party imported baselines and dependencies.
- `orchestrator/`: future Python CLI orchestration components and workflow modules.
- `configs/`: configuration placeholders for defaults, experiments, and model settings.
- `workspace/`: temporary run directory used during experiment execution.
- `results/`: persistent experiment outputs for later analysis and reporting.
- `docs/`: architecture notes, roadmap, and repository-level conventions.
- `scripts/`: helper scripts for maintenance and utility tasks.

## Data and Code Boundaries

- External third-party code: imported baseline implementations in `cpp/external/` (not authored as original project code).
- Project source code: project-owned implementation and orchestration logic outside third-party imports.
- Temporary workspace data: ephemeral run artifacts in `workspace/` that can be regenerated.
- Persistent experiment results: stored outputs in `results/` kept for comparison, analysis, and reporting.

## Baseline Ownership Policy

- `cpp/external/lambdatwist/` is imported third-party baseline code.
- It must not be treated as original project source code.
- In a clean repository state, imported baseline files should remain unchanged.
- Future experiment modifications should happen outside the clean baseline, for example via project-owned wrappers or workspace copies.
