# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository supports a bachelor thesis focused on automated optimization of C++ 3D vision algorithms with LLM support.
The first minimal case study is a P3P solver.

## Current Status

The repository scaffold is complete and the first working Lambda Twist baseline is established.
The C++ project includes a baseline library target (`lambdatwist_baseline`), a project-owned runner (`baseline_runner`), a smoke test (`baseline_smoke_test`), an old compatibility benchmark (`baseline_benchmark`), and a new absolute-pose family benchmark with a Lambda Twist P3P adapter validator.
A Python CLI entry point automates the baseline configure/build/test/run/family-benchmark flow from the command line, writes per-run artifacts under `results/runs/<run_id>/`, and appends compact JSONL records to `results/index.jsonl`.

Baseline benchmark parsing and candidate verification with the same family benchmark path are implemented. Baseline-vs-candidate comparison, best candidate selection, advanced reporting or experiment analysis, automatic promotion into the main source tree, and a closed-loop LLM optimization flow are intentionally not implemented yet.
Environment expectations are documented in `docs/setup.md`, and baseline state details are documented in `docs/baseline.md`.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests and benchmark placeholders, external baselines
|- orchestrator/   # Python orchestration (minimal baseline CLI + scaffold modules)
|- configs/        # Placeholder configuration files
|- workspace/      # Reserved temporary run workspace
|- results/        # Persistent run artifacts and the JSONL run index
|- docs/           # Project documentation
`- scripts/        # Helper scripts only
```

## Architecture

The project is structured around a C++ algorithmic core and a Python automation layer. Experiment runs use `workspace/` for temporary artifacts and `results/` for persistent outputs, including per-run directories and `results/index.jsonl`, but full experiment management is not implemented yet.
The planned persistent run output format is documented in `docs/result_storage_format.md`.

The baseline CLI and the LLM experiment runner are intentionally separate entry
points. `orchestrator/cli/main.py` remains the baseline configure/build/run
command. `orchestrator.experiments.run_experiment` is the main entry point for
LLM optimization experiments.

## Baseline Automation

The minimal baseline command-line flow is available through `orchestrator/cli/main.py`.
It requires `EIGEN3_INCLUDE_DIR` and optionally supports `CMAKE_EXE`, `CMAKE_GENERATOR`, `CMAKE_CXX_COMPILER`, and `CMAKE_MAKE_PROGRAM`.
On Windows outside CLion, explicit toolchain environment variables may be needed so CMake does not select an unavailable default generator.

The automated flow is:

1. Configure CMake.
2. Build `baseline_smoke_test`.
3. Build `baseline_runner`.
4. Build `absolute_pose_lambdatwist_adapter_validator`.
5. Build `absolute_pose_lambdatwist_benchmark`.
6. Run `baseline_smoke_test`.
7. Run `baseline_runner`.
8. Run `absolute_pose_lambdatwist_adapter_validator`.
9. Run `absolute_pose_lambdatwist_benchmark` and parse its metrics.

```powershell
$env:EIGEN3_INCLUDE_DIR="C:\path\to\eigen"
$env:CMAKE_GENERATOR="MinGW Makefiles"
$env:CMAKE_CXX_COMPILER="C:\path\to\g++.exe"
$env:CMAKE_MAKE_PROGRAM="C:\path\to\mingw32-make.exe"
py orchestrator/cli/main.py
```

If `python` is available on `PATH`, `python orchestrator/cli/main.py` is also valid.
Set `CMAKE_EXE` only when the intended `cmake.exe` is not already selected by `PATH`.

### Build Configuration

Benchmark and evaluation builds default to **Release** for accurate runtime metrics. Override with:

```powershell
$env:CMAKE_BUILD_TYPE="Debug"
```

Or on Unix:

```bash
export CMAKE_BUILD_TYPE=Debug
```

The build type is recorded in run artifacts (`metadata.json`, `verification.json`) and verified by the benchmark artifact audit. Debug builds are not suitable for performance comparisons.

## LLM Adapter

The first connected LLM is DeepSeek V4 Flash using `DEEPSEEK_API_KEY`.
The LLM layer also includes a controlled optimization prompt builder with conservative C++/Eigen safety rules and a response parser with basic candidate diff sanity checks.
Automatic patch application or promotion to the main source tree is not implemented, and candidates are not integrated into the baseline pipeline yet. Candidate diffs can only be materialized in isolated workspace copies.

```powershell
$env:DEEPSEEK_API_KEY="..."
py -m orchestrator.llm.deepseek_client `
  --config configs/llm_deepseek_flash.json `
  --system 'You are a strict JSON-only assistant. Return only valid JSON. No markdown. No explanation.' `
  --user 'Return exactly this JSON object and nothing else: {"status":"ok"}'
```

Manual candidate generation is also available. It reads a source file, sends a controlled prompt to DeepSeek, parses the response, and saves `llm_request.json`, `llm_response.json`, `candidate.json`, and `candidate.diff` artifacts. Candidate patches are saved but not applied.

```powershell
py -m orchestrator.llm.generate_candidate `
  --config configs/llm_deepseek_flash.json `
  --source cpp/external/lambdatwist/p3p.cc
```

For offline development, the same candidate-generation path can use a deterministic
mock response without an API key or network call:

```powershell
py -m orchestrator.llm.generate_candidate `
  --config configs/llm_mock_candidate.json `
  --source cpp/external/lambdatwist/p3p.cc
```

Generated candidate patches can be materialized only into an isolated workspace
copy under `workspace/candidates/<candidate_run_id>/`. The materialization
command validates patch scope against `candidate.json["target_files"]` and
verifies that a non-empty patch changes at least one target file. It does not
modify the main `cpp/` source tree. The active Step 9 patching command is
`orchestrator.patching.materialize_candidate`; `orchestrator/patching/apply_patch.py`
is only a compatibility marker for a future broader patching API.

```powershell
py -m orchestrator.patching.materialize_candidate `
  --candidate-run results/runs/<candidate_run_id>
```

A successfully materialized candidate can then be verified inside the same
isolated workspace copy. Verification configures CMake, builds and runs
`baseline_smoke_test`, builds and runs the Lambda Twist P3P adapter validator,
builds and runs `absolute_pose_lambdatwist_benchmark`, and parses benchmark
stdout into `verification.json`. It is deterministic, does not call an LLM, does
not compare performance against the baseline, and does not modify the main
`cpp/` source tree.

```powershell
py -m orchestrator.execution.verify_candidate `
  --candidate-run results/runs/<candidate_run_id>
```

Experiment configs are introduced for future multi-iteration and multi-variant
runs. The current experiment runner supports dry-run planning, candidate
generation, and optional materialization/verification according to config
pipeline flags. Verification includes the family benchmark path, but the runner
does not compare performance or select a best candidate yet. Experiment runs also write per-variant history artifacts under
`results/experiments/<experiment_id>/variants/`. The runner can optionally use
compact variant-local history in later prompts; this history is not shared
between variants. Sample configs are available at
`configs/experiments/deepseek_flash_p3p_basic.json`,
`configs/experiments/deepseek_flash_p3p_generate_materialize_verify.json`, and
`configs/experiments/deepseek_flash_p3p_variants.json`. A variant-local history
example is available at
`configs/experiments/deepseek_flash_p3p_variants_with_history.json`.
Experiment variants can also apply reproducible LLM parameter overrides and
save resolved per-variant LLM config snapshots; the Flash-only sample is
`configs/experiments/deepseek_flash_p3p_parameter_variants.json`. The optional
`configs/llm_deepseek_pro_max.json` config is intended for later final or
high-quality runs and is not used by the default cheaper Flash experiments.
The Step 10 experiment runner is summarized in `docs/experiment_runner.md`.
Candidate comparison, best candidate selection, candidate promotion into the
main source tree, and full closed-loop optimization with ranking are still not
implemented.

The mock experiment config is useful for checking storage and orchestration
without calling DeepSeek:

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/mock_p3p_basic.json
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_basic.json `
  --dry-run
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_basic.json
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_generate_materialize_verify.json
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_variants.json `
  --dry-run
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_variants.json
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_variants_with_history.json `
  --dry-run
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_variants_with_history.json
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_parameter_variants.json `
  --dry-run
```

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_flash_p3p_parameter_variants.json
```

## External Baseline Code

- `cpp/external/lambdatwist/` contains an imported third-party baseline P3P solver.
- This code is not original project source code.
- Clean baseline files are expected to remain unchanged in repository baseline state.
- The main project logic and optimization workflow will be built on top of this baseline.

## Current State (Pre-Comparator)

The following features are implemented and verified:

- Project-owned adapter validator for Lambda Twist P3P
- Deterministic synthetic case generation and correctness policy with configurable thresholds
- Family benchmark architecture with core/adapter/runner separation via CMake targets
- Stable snake-case key-value benchmark stdout with optional metadata fields
- Python parser for required and optional benchmark fields
- Baseline `metrics.json` and candidate `verification.json` with `benchmark_options` block for reproducibility
- `benchmark_artifact_audit` that compares `benchmark_options` and `build_type` before allowing comparison
- `valid_cases` and `total_solutions` parsed when present in benchmark output
- Experiment runner with multi-variant, iteration, history, and pipeline support

## Not Implemented Yet

- Baseline-vs-candidate comparison (Step 11)
- Best candidate selection and ranking
- Accepted/rejected/improved decision logic
- Candidate promotion into the main source tree
- Full closed-loop LLM optimization with ranking
- Additional solver adapters or benchmark families
- JSON metrics output from C++ benchmarks
