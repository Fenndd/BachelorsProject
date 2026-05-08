# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository supports a bachelor thesis on automated optimization of C++ 3D vision algorithms using LLM-generated candidates. The current minimal case study is the Lambda Twist P3P solver in the absolute-pose solver benchmark family.

The project combines a C++ baseline and benchmark layer under `cpp/`, a Python orchestration layer under `orchestrator/`, persistent artifacts under `results/`, and isolated candidate workspaces under `workspace/`.

## Current Status

Implemented now:

- Baseline automation through `orchestrator/cli/main.py`.
- Absolute-pose benchmark family for Lambda Twist P3P, including adapter validation and parsed benchmark metrics.
- LLM candidate generation through `orchestrator.llm.generate_candidate`.
- The **Candidate Edit Format Layer** with `unified_diff` and `line_range_edits`.
- Candidate materialization and verification in isolated workspaces.
- Pairwise candidate decision and multi-candidate best-result selection.

Not implemented yet:

- Candidate promotion into the main `cpp/` source tree.
- Closed-loop optimization that automatically promotes or reuses selected candidates.
- Advanced reporting, plots, or final aggregated experiment analysis.
- Additional solver families/adapters beyond the current minimal Lambda Twist P3P path.

The real DeepSeek Pro Max line-range full-cycle config exists at `configs/experiments/deepseek_pro_max_p3p_line_range_full_cycle_selection.json`. Real DeepSeek runs require `DEEPSEEK_API_KEY`.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests, benchmark targets, external baselines
|- orchestrator/   # Python baseline, LLM, materialization, verification, selection, experiments
|- configs/        # LLM, mock candidate, and experiment configs
|- workspace/      # Isolated candidate workspaces
|- results/        # Persistent baseline, candidate, verification, decision, experiment artifacts
|- docs/           # Project documentation
`- scripts/        # Helper scripts only
```

## Architecture

The baseline CLI and the LLM experiment runner are separate entry points:

- `orchestrator/cli/main.py` prepares and records clean baseline runs.
- `orchestrator.experiments.run_experiment` runs configured LLM optimization experiments.

Experiment runs use `workspace/` for isolated candidate copies and `results/` for persistent outputs. Candidate materialization never modifies the main `cpp/` source tree.

See `docs/architecture.md`, `docs/experiment_runner.md`, `docs/result_storage_format.md`, `docs/candidate_edit_formats.md`, and `docs/best_result_selection_policy.md`.

## Baseline Automation

The baseline command-line flow requires `EIGEN3_INCLUDE_DIR` and optionally supports `CMAKE_EXE`, `CMAKE_GENERATOR`, `CMAKE_CXX_COMPILER`, and `CMAKE_MAKE_PROGRAM`.

```powershell
$env:EIGEN3_INCLUDE_DIR="C:\path\to\eigen"
py orchestrator/cli/main.py
```

The flow configures CMake, builds/runs `baseline_smoke_test`, `baseline_runner`, `absolute_pose_lambdatwist_adapter_validator`, and `absolute_pose_lambdatwist_benchmark`, parses metrics, and checks `correctness_passed`. Benchmark and evaluation builds default to **Release**.

## LLM Candidate Generation and Candidate Edit Formats

LLM candidate generation is implemented by `orchestrator.llm.generate_candidate`. It supports two candidate formats selected with `--candidate-type` and experiment `candidate_format.type`.

### `unified_diff`

`unified_diff` is the legacy/fallback format. The LLM receives plain source and returns a `unified_diff` string. Generation writes `candidate.diff`; materialization applies it with `git apply` and can use a `git apply --recount` fallback for malformed hunk counts.

### `line_range_edits`

`line_range_edits` is the preferred robust format for real full-cycle LLM experiments. The LLM receives `line_numbered` source and returns structured `edits[]` entries with `file`, `start_line`, `end_line`, `original`, and `replace`. Generation writes `candidate.edits.json`; materialization applies the edits deterministically and writes the system-generated `candidate.generated.diff`.

See `docs/candidate_edit_formats.md` for details.

## Candidate Materialization and Verification

Materialization runs only inside `workspace/candidates/<candidate_run_id>/`.

The materializer enforces `optimization_scope.allowed_files` from experiment configs:

- `unified_diff`: candidate `target_files` and diff header paths must remain allowed.
- `line_range_edits`: candidate `target_files` and `edits[].file` must remain allowed.

Verification configures/builds/runs inside the isolated candidate workspace and writes `verification.json`. It does not call an LLM and does not modify the main `cpp/` source tree.

## Experiment Runner Commands

Baseline:

```powershell
py orchestrator/cli/main.py
```

Line-range mock full-cycle experiment:

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/mock_p3p_line_range_full_cycle_selection.json
```

Line-range DeepSeek Pro Max dry-run:

```powershell
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_pro_max_p3p_line_range_full_cycle_selection.json `
  --dry-run
```

Line-range DeepSeek Pro Max real run:

```powershell
$env:DEEPSEEK_API_KEY="..."
py -m orchestrator.experiments.run_experiment `
  --config configs/experiments/deepseek_pro_max_p3p_line_range_full_cycle_selection.json
```

Mock configs do not require an API key.

## Selection

Pairwise candidate decision and multi-candidate best-result selection are implemented. Selection consumes verified benchmark artifacts and an explicit `selection.baseline_run_dir`. It writes `candidate_decision.json` when configured and `best_candidate_selection.json` for experiment-level selection.

Selection does not promote, merge, copy, or commit candidate code.

## External Baseline Code

- `cpp/external/lambdatwist/` contains imported third-party baseline P3P solver code.
- This code is not original project source code.
- Clean baseline files are expected to remain unchanged in repository baseline state.
- Candidate changes are materialized only in isolated workspace copies unless future promotion support is implemented.

## Current State

The following features are implemented and verified at the current minimal level:

- Project-owned adapter validator for Lambda Twist P3P.
- Deterministic synthetic case generation and correctness policy with configurable thresholds.
- Family benchmark architecture with core/adapter/runner separation via CMake targets.
- Stable snake-case key-value benchmark stdout with optional metadata fields.
- Python parser for required and optional benchmark fields.
- Baseline `metrics.json` and candidate `verification.json` with `benchmark_options` for reproducibility.
- `benchmark_artifact_audit` comparability checks.
- Pairwise `candidate_decision.json` logic.
- Multi-candidate `best_candidate_selection.json` selection.
- Experiment runner with multi-variant, iteration, history, candidate generation, materialization, verification, and selection.
- `candidate_format` support for `unified_diff` and `line_range_edits`.

## Not Implemented Yet

- Candidate promotion into the main source tree.
- Closed-loop optimization that automatically promotes or reuses selected candidates.
- Additional solver adapters or benchmark families.
- JSON metrics output directly from C++ benchmarks.
- Advanced reporting, plots, and final aggregated experiment analysis.