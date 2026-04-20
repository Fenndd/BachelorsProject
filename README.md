# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository is a project scaffold for a bachelor thesis focused on automated optimization of C++ 3D vision algorithms with LLM support.
The first minimal case study is a P3P solver.

## Current Status

This repository is still an **initial scaffold**.
Core project logic, working optimization pipeline, API integration, and full validation flow are intentionally not implemented yet.
Environment targets for this stage are documented in `docs/setup.md`.
Python orchestration files currently exist as module stubs only, without runtime behavior.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests and benchmark placeholders, external baselines
|- orchestrator/   # Python orchestration scaffold modules (stubs only)
|- configs/        # Placeholder configuration files
|- workspace/      # Temporary run workspace
|- results/        # Persistent experiment outputs
|- docs/           # Project documentation
`- scripts/        # Helper scripts only
```

## Architecture

The project is structured around a C++ algorithmic core and a Python CLI orchestrator. Experiment runs are executed in a separate `workspace/` directory, and generated outputs are persisted in `results/` for later analysis and reporting.

## External Baseline Code

- `cpp/external/lambdatwist/` contains an imported third-party baseline P3P solver.
- This code is not original project source code.
- Clean baseline files are expected to remain unchanged in repository baseline state.
- The main project logic and optimization workflow will be built on top of this baseline.

## Next Planned Steps

1. Finalize scaffold-level configuration conventions and documentation.
2. Add baseline integration wrappers without changing third-party source internals.
3. Introduce first controlled LLM-assisted optimization loop design.
4. Add experiment management and reporting flow.
