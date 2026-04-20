# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository is a project scaffold for a bachelor thesis focused on automated optimization of C++ 3D vision algorithms with LLM support.
The first minimal case study is a P3P solver.

## Current Status

This repository is still an **initial scaffold**.
Core project logic, working optimization pipeline, API integration, and full validation flow are intentionally not implemented yet.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests and benchmark placeholders, external baselines
|- orchestrator/   # Future Python CLI orchestration layer (structure only)
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
- The main project logic and optimization workflow will be built on top of this baseline.

## Next Planned Steps

1. Finalize scaffold-level configuration conventions and documentation.
2. Add baseline integration wrappers without changing third-party source internals.
3. Introduce first controlled LLM-assisted optimization loop design.
4. Add experiment management and reporting flow.
