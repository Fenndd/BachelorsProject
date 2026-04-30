# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository supports a bachelor thesis focused on automated optimization of C++ 3D vision algorithms with LLM support.
The first minimal case study is a P3P solver.

## Current Status

The repository scaffold is complete and the first working Lambda Twist baseline is established at a minimal level.
The C++ project includes a baseline library target (`lambdatwist_baseline`), a project-owned runner (`baseline_runner`), a smoke test (`baseline_smoke_test`), and a minimal benchmark (`baseline_benchmark`).
A Python CLI entry point automates the baseline configure/build/test/run/benchmark flow from the command line.

Full validation, advanced benchmarking, result storage, experiment management, and LLM-driven optimization are intentionally not implemented yet.
Environment expectations are documented in `docs/setup.md`, and baseline state details are documented in `docs/baseline.md`.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests and benchmark placeholders, external baselines
|- orchestrator/   # Python orchestration (minimal baseline CLI + scaffold modules)
|- configs/        # Placeholder configuration files
|- workspace/      # Reserved temporary run workspace
|- results/        # Reserved future experiment outputs
|- docs/           # Project documentation
`- scripts/        # Helper scripts only
```

## Architecture

The project is structured around a C++ algorithmic core and a Python automation layer. Future experiment runs are expected to use `workspace/` for temporary artifacts and `results/` for persistent outputs, but full experiment management is not implemented yet.

## Baseline Automation

The minimal baseline command-line flow is available through `orchestrator/cli/main.py`.
It requires `EIGEN3_INCLUDE_DIR` and optionally supports `CMAKE_EXE`, `CMAKE_GENERATOR`, `CMAKE_CXX_COMPILER`, and `CMAKE_MAKE_PROGRAM`.
On Windows outside CLion, explicit toolchain environment variables may be needed so CMake does not select an unavailable default generator.

The automated flow is:

1. Configure CMake.
2. Build `baseline_smoke_test`.
3. Build `baseline_runner`.
4. Build `baseline_benchmark`.
5. Run `baseline_smoke_test`.
6. Run `baseline_runner`.
7. Run `baseline_benchmark`.

```powershell
$env:EIGEN3_INCLUDE_DIR="C:\path\to\eigen"
$env:CMAKE_GENERATOR="MinGW Makefiles"
$env:CMAKE_CXX_COMPILER="C:\path\to\g++.exe"
$env:CMAKE_MAKE_PROGRAM="C:\path\to\mingw32-make.exe"
py orchestrator/cli/main.py
```

If `python` is available on `PATH`, `python orchestrator/cli/main.py` is also valid.
Set `CMAKE_EXE` only when the intended `cmake.exe` is not already selected by `PATH`.

## External Baseline Code

- `cpp/external/lambdatwist/` contains an imported third-party baseline P3P solver.
- This code is not original project source code.
- Clean baseline files are expected to remain unchanged in repository baseline state.
- The main project logic and optimization workflow will be built on top of this baseline.

## Next Planned Steps

1. Expand the smoke test into a real validation strategy.
2. Define a proper benchmark protocol for baseline and optimized variants.
3. Add controlled experiment metadata and result storage.
4. Introduce the first LLM-assisted optimization loop.
