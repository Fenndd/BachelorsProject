# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository supports a bachelor thesis focused on automated optimization of C++ 3D vision algorithms with LLM support.
The first minimal case study is a P3P solver.

## Current Status

The repository scaffold is complete and the first working Lambda Twist baseline is established at a minimal level.
The C++ project includes a baseline library target (`lambdatwist_baseline`), a project-owned runner (`baseline_runner`), a smoke test (`baseline_smoke_test`), and a minimal benchmark (`baseline_benchmark`).
A Python CLI entry point automates the baseline configure/build/test/run/benchmark flow from the command line, writes per-run artifacts under `results/runs/<run_id>/`, and appends compact JSONL records to `results/index.jsonl`.

Full validation, benchmark runtime parsing, automatic patch application, candidate build/test/benchmark, run comparison, best candidate selection, advanced reporting or experiment analysis, and a closed-loop LLM optimization flow are intentionally not implemented yet.
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

## LLM Adapter

The first connected LLM is DeepSeek V4 Flash using `DEEPSEEK_API_KEY`.
The LLM layer also includes a controlled optimization prompt builder with conservative C++/Eigen safety rules and a response parser with basic candidate diff sanity checks.
Automatic patch application to the main source tree is not implemented, and candidates are not integrated into the baseline pipeline yet.

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

Generated candidate patches can be materialized only into an isolated workspace
copy under `workspace/candidates/<candidate_run_id>/`. The materialization
command validates patch scope against `candidate.json["target_files"]` and
verifies that a non-empty patch changes at least one target file. It does not
modify the main `cpp/` source tree, and build/test/benchmark of materialized
candidates is not implemented yet.

```powershell
py -m orchestrator.patching.materialize_candidate `
  --candidate-run results/runs/<candidate_run_id>
```

A successfully materialized candidate can then be verified inside the same
isolated workspace copy. Verification configures CMake, builds only
`baseline_smoke_test`, and runs only `baseline_smoke_test`. It still does not
run candidate benchmarks or compare performance, and the main `cpp/` source
tree remains unchanged. The current implementation is intentionally a narrow
Step 9 smoke verifier in `orchestrator/execution/candidate_smoke_verification.py`;
it is not the future general candidate execution pipeline.

```powershell
py -m orchestrator.execution.verify_candidate `
  --candidate-run results/runs/<candidate_run_id>
```

Experiment configs are introduced for future multi-iteration and multi-variant
runs. The current experiment runner supports dry-run planning, candidate
generation, and optional materialization/verification according to config
pipeline flags. It does not benchmark, compare performance, or select a best
candidate yet. Experiment runs also write per-variant history artifacts under
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
Candidate benchmarks, benchmark runtime parsing, candidate comparison, best
candidate selection, candidate promotion into the main source tree, and full
closed-loop optimization with ranking are still not implemented.

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

## Next Planned Steps

1. Expand the smoke test into a real validation strategy.
2. Define a proper benchmark protocol for baseline and optimized variants.
3. Parse benchmark runtime from stored benchmark output.
4. Introduce run comparison, best candidate selection, and the first LLM-assisted optimization loop.
