# Development Environment Targets

This document defines the expected local environment for the current minimal baseline automation stage.
The repository scaffold is complete, and baseline integration with minimal command-line automation is already in place.

## Toolchain Targets

- Python: target `3.11` (or newer compatible patch release)
- CMake: minimum `3.20`
- C++ standard: `C++20`

## Expected Compiler Examples

- GCC `13+`
- Clang `16+`
- MSVC (Visual Studio 2022 toolset, `19.3x+`)

## Dependency Note

Eigen is required by the Lambda Twist baseline.
The CMake project expects `EIGEN3_INCLUDE_DIR` to point to the Eigen include root, meaning the directory that contains `Eigen/Core`.

## Command-Line Automation

The minimal baseline automation entry point is `orchestrator/cli/main.py`.
It configures CMake, builds the baseline smoke test, runner, and benchmark targets, then runs them in order.

This baseline CLI is intentionally separate from LLM optimization experiments.
Use `orchestrator.experiments.run_experiment` for configured LLM experiment
runs.

On Windows outside CLion, CMake may need explicit toolchain selection to avoid an unavailable default generator such as `NMake Makefiles`.
The script supports these environment variables:

- `EIGEN3_INCLUDE_DIR` (required)
- `CMAKE_EXE` (optional)
- `CMAKE_GENERATOR` (optional)
- `CMAKE_CXX_COMPILER` (optional)
- `CMAKE_MAKE_PROGRAM` (optional)

Example PowerShell setup:

```powershell
$env:EIGEN3_INCLUDE_DIR="C:\path\to\eigen"
$env:CMAKE_GENERATOR="MinGW Makefiles"
$env:CMAKE_CXX_COMPILER="C:\path\to\g++.exe"
$env:CMAKE_MAKE_PROGRAM="C:\path\to\mingw32-make.exe"
py orchestrator/cli/main.py
```

Use `python orchestrator/cli/main.py` instead if `python` is the available launcher in the shell.
