# Environment Setup

## Prerequisites

- **Python** `>=3.11`
- **CMake** `>=3.20`
- **C++20** capable compiler (GCC 13+, Clang 16+, or MSVC 2022 19.3x+)
- **Eigen 3** — set `EIGEN3_INCLUDE_DIR` to the directory containing `Eigen/Core`

## Install

```bash
python -m pip install -e ".[dev]"
python -m playwright install chromium   # for PDF report rendering
```

## Local Environment

Copy the template and fill in your paths and keys:

```bash
copy .env.example .env.local    # Windows
cp .env.example .env.local      # Unix
```

Required in `.env.local`:

| Variable | Purpose |
|---|---|
| `EIGEN3_INCLUDE_DIR` | Path to Eigen include root |
| `DEEPSEEK_API_KEY` | API key for DeepSeek (real experiment runs only) |

Optional CMake toolchain variables (useful on Windows outside an IDE):

| Variable | Purpose |
|---|---|
| `CMAKE_EXE` | Path to `cmake` executable |
| `CMAKE_GENERATOR` | CMake generator (e.g. `Ninja`) |
| `CMAKE_CXX_COMPILER` | Path to C++ compiler |
| `CMAKE_MAKE_PROGRAM` | Path to make/ninja executable |

## Build Type

The pipeline defaults to `Release` builds for accurate performance metrics.
The resolution order is:

1. `BENCHMARK_CMAKE_BUILD_TYPE` (primary)
2. `CMAKE_BUILD_TYPE` (fallback)
3. `Release` (default)

Set `BENCHMARK_CMAKE_BUILD_TYPE=Release` in `.env.local` for reproducible benchmarks.
Debug builds are not suitable for performance comparisons.

## Next Steps

See [docs/usage.md](usage.md) for running baselines, experiments, and viewing results.
