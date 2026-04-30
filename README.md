# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository is a project scaffold for a bachelor thesis focused on automated optimization of C++ 3D vision algorithms with LLM support.
The first minimal case study is a P3P solver.

## Current Status

The repository scaffold stage is complete, and a first working baseline is established.
The project now includes a project-owned baseline runner (`cpp/src/baseline_runner.cpp`) linked to the imported Lambda Twist baseline target.
Full validation, advanced benchmarking, experiment orchestration, and optimization stages are intentionally not implemented yet.
Environment targets for this stage are documented in `docs/setup.md`.
The first minimal orchestration entry point is now available at `orchestrator/cli/main.py` for baseline configure/build/smoke-test/run/benchmark automation.
Baseline state details are documented in `docs/baseline.md`.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests and benchmark placeholders, external baselines
|- orchestrator/   # Python orchestration (minimal baseline CLI + scaffold modules)
|- configs/        # Placeholder configuration files
|- workspace/      # Temporary run workspace
|- results/        # Persistent experiment outputs
|- docs/           # Project documentation
`- scripts/        # Helper scripts only
```

## Architecture

The project is structured around a C++ algorithmic core and a Python CLI orchestrator. Experiment runs are executed in a separate `workspace/` directory, and generated outputs are persisted in `results/` for later analysis and reporting.

## Baseline Automation

The minimal baseline command-line flow is available through `orchestrator/cli/main.py`.
It requires `EIGEN3_INCLUDE_DIR` and optionally supports `CMAKE_EXE`, `CMAKE_GENERATOR`, `CMAKE_CXX_COMPILER`, and `CMAKE_MAKE_PROGRAM` for explicit Windows/MinGW toolchain selection outside CLion.
The flow configures CMake, builds the baseline targets, runs a minimal smoke test, runs `baseline_runner`, and then runs a minimal benchmark.

```powershell
$env:EIGEN3_INCLUDE_DIR="C:\path\to\eigen"
$env:CMAKE_GENERATOR="MinGW Makefiles"
$env:CMAKE_CXX_COMPILER="C:\path\to\g++.exe"
$env:CMAKE_MAKE_PROGRAM="C:\path\to\mingw32-make.exe"
python orchestrator/cli/main.py
```

## External Baseline Code

- `cpp/external/lambdatwist/` contains an imported third-party baseline P3P solver.
- This code is not original project source code.
- Clean baseline files are expected to remain unchanged in repository baseline state.
- The main project logic and optimization workflow will be built on top of this baseline.

## Next Planned Steps

1. Expand baseline integration beyond the minimal runner boundary.
2. Implement validation and benchmarking for baseline and future variants.
3. Introduce first controlled LLM-assisted optimization loop design.
4. Add experiment management and reporting flow.
