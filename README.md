# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository supports a bachelor thesis on automated optimization of C++ 3D vision algorithms using LLM-generated candidates. The current minimal case study is the Lambda Twist P3P solver in the absolute-pose solver benchmark family.

The project combines a clean C++ baseline and benchmark layer under `cpp/`, a Python orchestration layer under `orchestrator/`, persistent artifacts under `results/`, and isolated workspaces under `workspace/`.

## Current Status

Implemented:

- Baseline automation through `orchestrator/cli/main.py`.
- Absolute-pose benchmark family for Lambda Twist P3P, including adapter validation and parsed benchmark metrics.
- LLM candidate generation through `orchestrator.core.llm.generate_candidate`.
- A single line-range edit schema for LLM-generated candidates.
- Candidate materialization and verification in isolated workspaces.
- Pairwise candidate decision for closed-loop promotion and reporting.
- Closed-loop iterative optimization in the experiment runner with experiment-local `current_best_source`.
- Compact benchmark-aware closed-loop history for later generations.
- Final closed-loop artifacts and analysis-only selector/reporting.
- Automatic final repeated benchmark validation after closed-loop completion and before report generation.
- Single unified HTML/PDF report with runtime, correctness, final repeated validation, failure analysis, phase timing, LLM usage, reproducibility metadata, diff statistics, iteration appendix sections, and a read-only report inspector.

Not implemented yet:

- Automatic candidate promotion into the main `cpp/` source tree.
- Multi-variant closed-loop optimization strategy.
- Additional solver families/adapters beyond the current minimal Lambda Twist P3P path.
- JSON metrics output directly from C++ benchmarks.
- Broader statistical dashboards or aggregate reports across multiple experiments.
- Memory measurement; the current prototype focuses on runtime and PoseLib-style calibrated-pose correctness metrics.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests, benchmark targets, external baselines
|- orchestrator/   # Python baseline, LLM, materialization, verification, selection, experiments
|- configs/        # LLM and experiment configs
|- workspace/      # Isolated candidate and experiment-local current-best workspaces
|- results/        # Persistent baseline, candidate, verification, decision, experiment artifacts
|- docs/           # Project documentation
`- scripts/        # Helper scripts only
```

## Architecture Summary

The baseline CLI and the LLM experiment runner are separate entry points:

- `orchestrator/cli/main.py` prepares and records clean baseline runs.
- `orchestrator.experiments.run_experiment` runs configured LLM optimization experiments.
- `orchestrator/cli/app.py` (Typer) is the control layer: it launches these existing entry points and reads existing artifacts without reimplementing pipeline logic.

Experiment runs use `workspace/` for isolated source copies and `results/` for persistent outputs. Candidate materialization and closed-loop promotion never modify the main `cpp/` source tree automatically.

See `docs/closed_loop_optimization.md` for the full closed-loop control flow.

## Baseline Automation

The baseline command-line flow requires `EIGEN3_INCLUDE_DIR` and optionally supports `CMAKE_EXE`, `CMAKE_GENERATOR`, `CMAKE_CXX_COMPILER`, and `CMAKE_MAKE_PROGRAM`.

```powershell
$env:EIGEN3_INCLUDE_DIR="C:\path\to\eigen"
py orchestrator/cli/main.py
```

The flow configures CMake, builds/runs `absolute_pose_lambdatwist_adapter_validator` and `absolute_pose_lambdatwist_benchmark`, parses metrics, and checks `correctness_passed`. Benchmark and evaluation builds default to **Release**.

## Experimental Terminal Control Layer

The Typer/Rich CLI and Textual TUI provide a control surface for project status, diagnostics, and launching baseline and experiment runs.

```powershell
copy .env.example .env.local   # fill in local paths and API keys

python -m orchestrator.cli.app --help
python -m orchestrator.cli.app doctor
python -m orchestrator.cli.app baseline run
python -m orchestrator.cli.app experiment list
python -m orchestrator.cli.app experiment run --config configs/experiments/basic_deepseek_flash_3iter.json --dry-run
python -m orchestrator.cli.app experiment run --config configs/experiments/<file>.json --yes
python -m orchestrator.cli.app results list
python -m orchestrator.cli.app results latest
python -m orchestrator.cli.app results show latest
python -m orchestrator.cli.app results open latest
python -m orchestrator.cli.app tui
```

The results browser is read-only. Workspace cleanup only affects `workspace/`; it does not delete `results/`. API keys and other secrets are masked in CLI/TUI diagnostics.

See `docs/interactive_terminal_control_layer.md` for the full command reference and TUI screen list.

## LLM Candidate Generation and Candidate Edit Schema

LLM candidate generation is implemented by `orchestrator.core.llm.generate_candidate`. The LLM receives line-numbered source and returns structured `edits[]` entries with `file`, `start_line`, `end_line`, `original`, and `replace`. Generation writes `candidate.json` and `candidate.edits.json`; materialization applies the edits deterministically and writes `candidate.generated.diff`.

See `docs/candidate_edit_formats.md` for details.

## Candidate Materialization and Verification

Materialization runs only inside `workspace/candidates/<candidate_run_id>/` using the `optimization_scope.allowed_files` allowlist from the experiment config. Verification configures/builds/runs inside the isolated candidate workspace and writes `verification.json`.

## Selection and Reporting

Pairwise candidate decisions consume verified benchmark artifacts and explicit references. The closed-loop runner uses the `decision_vs_current_best` outcome on each iteration record to control promotion into the experiment-local current best. `decision_vs_original_baseline.json` is retained for reporting and traceability only.

Completed reports can be checked without regenerating anything:

```powershell
python -m orchestrator.reporting.report_inspector --experiment-dir results/experiments/<experiment_id>
```

See `docs/best_result_selection_policy.md` for the full decision policy and improvement thresholds.

## External Baseline Code

- `cpp/external/lambdatwist/` contains imported third-party baseline P3P solver code.
- This code is not original project source code.
- Clean baseline files are expected to remain unchanged in repository baseline state.
- Candidate changes are materialized only in isolated workspace copies.

## Documentation

- `docs/architecture.md` — pipeline components and module boundaries
- `docs/setup.md` — toolchain targets, env vars, build-type override
- `docs/closed_loop_optimization.md` — closed-loop control flow, artifacts, safety
- `docs/candidate_edit_formats.md` — LLM edit schema
- `docs/result_storage_format.md` — artifact paths and storage layout
- `docs/best_result_selection_policy.md` — pairwise decision rules, thresholds, statuses
- `docs/absolute_pose_benchmark.md` — benchmark protocol, output keys, baseline CLI steps
- `docs/interactive_terminal_control_layer.md` — Typer CLI and TUI reference
