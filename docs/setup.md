# Development Environment Targets

This document defines the expected local environment for the current baseline and LLM experiment pipeline.

## Toolchain Targets

- Python: target `3.11` or newer compatible patch release.
- CMake: minimum `3.20`.
- C++ standard: `C++20`.

## Expected Compiler Examples

- GCC `13+`
- Clang `16+`
- MSVC / Visual Studio 2022 toolset `19.3x+`

## Dependency Note

Eigen is required by the Lambda Twist baseline. The CMake project expects `EIGEN3_INCLUDE_DIR` to point to the Eigen include root, meaning the directory that contains `Eigen/Core`.

## Command-Line Automation

The baseline automation entry point is `orchestrator/cli/main.py`. It configures CMake, builds the adapter validator and absolute-pose benchmark, then runs and parses them.

This baseline CLI is intentionally separate from LLM optimization experiments. Use `orchestrator.experiments.run_experiment` for configured LLM experiment runs.

On Windows outside CLion, CMake may need explicit toolchain selection to avoid an unavailable default generator. The scripts support these environment variables:

- `EIGEN3_INCLUDE_DIR` (required for baseline and candidate verification)
- `CMAKE_EXE` (optional)
- `CMAKE_GENERATOR` (optional)
- `CMAKE_CXX_COMPILER` (optional)
- `CMAKE_MAKE_PROGRAM` (optional)
- `CMAKE_BUILD_TYPE` (optional; defaults to `Release`)

Simple baseline example:

```powershell
$env:EIGEN3_INCLUDE_DIR="C:\path\to\eigen"
py orchestrator/cli/main.py
```

Use `python orchestrator/cli/main.py` instead if `python` is the available launcher in the shell.

## LLM Experiment Environment

- `DEEPSEEK_API_KEY` is required for real DeepSeek runs.
- `EIGEN3_INCLUDE_DIR` is required for baseline and candidate verification.
- `CMAKE_BUILD_TYPE` defaults to `Release` and should remain `Release` for performance comparison.

Example PowerShell setup based on a common Windows/CLion-style toolchain. These paths are examples only and are not mandatory:

```powershell
$env:EIGEN3_INCLUDE_DIR = "C:\Libraries\eigen-3.4.1"
$env:CMAKE_EXE = "C:\Users\<user>\AppData\Local\Programs\CLion\bin\cmake\win\x64\bin\cmake.exe"
$env:CMAKE_GENERATOR = "Ninja"
$env:CMAKE_CXX_COMPILER = "C:\Users\<user>\AppData\Local\Programs\CLion\bin\mingw\bin\g++.exe"
$env:CMAKE_MAKE_PROGRAM = "C:\Users\<user>\AppData\Local\Programs\CLion\bin\ninja\win\x64\ninja.exe"
$env:CMAKE_BUILD_TYPE = "Release"
$env:DEEPSEEK_API_KEY = "..."
```

## Build Type Override

Baseline and candidate benchmarks default to `Release` builds for accurate
runtime metrics. Debug builds are not suitable for performance comparisons.

Override `CMAKE_BUILD_TYPE` to `Debug` for debugging only:

```powershell
$env:CMAKE_BUILD_TYPE = "Debug"
py orchestrator/cli/main.py
```

```bash
export CMAKE_BUILD_TYPE=Debug
python orchestrator/cli/main.py
```

The resolved build type is:

- passed to CMake configure as `-DCMAKE_BUILD_TYPE=<value>`
- passed to `cmake --build` as `--config <value>`
- recorded in `metadata.json` and `metrics.json` for reproducibility

Baseline and candidate benchmarks must use the same build type for valid
comparison. The benchmark artifact audit enforces this check.
