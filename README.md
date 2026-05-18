# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

## Short Project Overview

This repository supports a bachelor thesis on automated optimization of C++ 3D vision algorithms using LLM-generated candidates. The current minimal case study is the Lambda Twist P3P solver in the absolute-pose solver benchmark family.

The project combines a clean C++ baseline and benchmark layer under `cpp/`, a Python orchestration layer under `orchestrator/`, persistent artifacts under `results/`, and isolated workspaces under `workspace/`.

## Current Status

Implemented now:

- Baseline automation through `orchestrator/cli/main.py`.
- Absolute-pose benchmark family for Lambda Twist P3P, including adapter validation and parsed benchmark metrics.
- LLM candidate generation through `orchestrator.llm.generate_candidate`.
- Candidate edit formats for `unified_diff` and `line_range_edits`.
- Candidate materialization and verification in isolated workspaces.
- Pairwise candidate decision and multi-candidate best-result selection.
- Closed-loop iterative optimization in the experiment runner with experiment-local `current_best_source`.
- Compact benchmark-aware closed-loop history for later generations.
- Final closed-loop artifacts and analysis-only selector/reporting.
- Automatic final repeated benchmark validation after closed-loop completion and before report generation.
- Single unified current single-experiment HTML/PDF report with runtime, correctness, final repeated validation, failure analysis, phase timing, LLM usage, reproducibility metadata, diff statistics, iteration appendix sections, and a read-only report inspector.

Not implemented yet:

- Automatic candidate promotion into the main `cpp/` source tree.
- Multi-variant closed-loop optimization strategy.
- Additional solver families/adapters beyond the current minimal Lambda Twist P3P path.
- JSON metrics output directly from C++ benchmarks.
- Broader statistical dashboards or aggregate reports across multiple experiments.
- Memory measurement; the current prototype focuses on runtime and correctness/reprojection metrics.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests, benchmark targets, external baselines
|- orchestrator/   # Python baseline, LLM, materialization, verification, selection, experiments
|- configs/        # LLM, mock candidate, and experiment configs
|- workspace/      # Isolated candidate and experiment-local current-best workspaces
|- results/        # Persistent baseline, candidate, verification, decision, experiment artifacts
|- docs/           # Project documentation
`- scripts/        # Helper scripts only
```

## Architecture Summary

The baseline CLI and the LLM experiment runner are separate entry points:

- `orchestrator/cli/main.py` prepares and records clean baseline runs.
- `orchestrator.experiments.run_experiment` runs configured LLM optimization experiments.

Experiment runs use `workspace/` for isolated source copies and `results/` for persistent outputs. Candidate materialization and closed-loop promotion never modify the main `cpp/` source tree automatically.

Closed-loop mode uses this control flow:

```text
clean baseline
  -> workspace/experiments/<experiment_id>/current_best_source/
  -> candidate generation from current_best_source
  -> candidate materialization against current_best_source
  -> verification
  -> decision_vs_current_best
  -> optional current_best_source update
  -> next iteration
```

The logical `target_file` remains repo-relative, for example `cpp/external/lambdatwist/p3p.cc`. Generation reads the physical file from the active source tree through `--source-root`, and materialization applies candidates against the same active source tree through `--base-source-root`.

`decision_vs_current_best.json` controls whether a candidate is promoted into the experiment-local `current_best_source`. `decision_vs_original_baseline.json` is retained for reporting/control against the original baseline. Final selector/reporting artifacts analyze the completed run only; they do not promote candidates or modify source trees.

Key closed-loop artifacts are written under `results/experiments/<experiment_id>/`:

- `final_optimized_source/`
- `final_optimized_source.diff`
- `closed_loop_summary.json`
- `closed_loop_iterations.jsonl`
- `closed_loop_selection_report.json`
- `val/final_validation_report.json`
- `current_best_state.json`

See `docs/architecture.md`, `docs/experiment_runner.md`, `docs/closed_loop_optimization.md`, `docs/result_storage_format.md`, `docs/candidate_edit_formats.md`, and `docs/best_result_selection_policy.md`.

## Baseline Automation

The baseline command-line flow requires `EIGEN3_INCLUDE_DIR` and optionally supports `CMAKE_EXE`, `CMAKE_GENERATOR`, `CMAKE_CXX_COMPILER`, and `CMAKE_MAKE_PROGRAM`.

```powershell
$env:EIGEN3_INCLUDE_DIR="C:\path\to\eigen"
py orchestrator/cli/main.py
```

The flow configures CMake, builds/runs `baseline_smoke_test`, `baseline_runner`, `absolute_pose_lambdatwist_adapter_validator`, and `absolute_pose_lambdatwist_benchmark`, parses metrics, and checks `correctness_passed`. Benchmark and evaluation builds default to **Release**. Build type is recorded as reproducibility metadata in reports.

The user-facing report is a single unified current report, not separate v1/v2 modes. It focuses on closed-loop mode. Legacy `selection_enabled` and `history_policy` fields are not shown as main report concepts; closed-loop promotion policy is `decision_vs_current_best.accepted_improvement_only`. Verification time includes benchmark execution, so `benchmark_seconds` is not separately shown in the main report. Missing PDF is valid for HTML-only reports; when PDF is requested, it is exported from the final completed HTML. Final repeated benchmark validation runs automatically after closed-loop completion and before report generation. It compares the original baseline source against the final optimized source, defaults to 5 benchmark repetitions, does not affect candidate promotion, and does not change `current_best_source`. Its artifacts live under `val/`; `b` means baseline and `f` means final. Final validation uses a minimal shortened `cpp/` build tree for Windows path-length safety, while the original repository `cpp/` layout is unchanged. Report headline baseline/final runtimes, speedup, runtime reduction, and correctness preserved come only from final repeated validation median metrics; if final validation is incomplete or unavailable, those headline metrics are unavailable. Single-run closed-loop selection metrics are iteration analytics only. Build type is reproducibility metadata; `Release` is the default benchmark build type.

## Experimental Terminal Control Layer

The first skeleton of the Interactive Terminal Control Layer is available through a new Typer/Rich CLI and Textual TUI. It is currently a thin control surface for basic project status, local environment diagnostics, and placeholders only; real baseline and experiment launching from this layer will be connected in later steps.

The repository includes a safe `.env.example` template. Local machine paths and API keys belong in `.env.local`, which is ignored by Git along with `.env`.

```powershell
copy .env.example .env.local
```

```powershell
python -m orchestrator.cli.app --help
python -m orchestrator.cli.app doctor
python -m orchestrator.cli.app baseline run
python -m orchestrator.cli.app experiment list
python -m orchestrator.cli.app experiment run --config configs/experiments/mock_p3p_basic.json --dry-run
python -m orchestrator.cli.app experiment run --config configs/experiments/<file>.json --yes
python -m orchestrator.cli.app results list
python -m orchestrator.cli.app results latest
python -m orchestrator.cli.app results show latest
python -m orchestrator.cli.app results open latest
python -m orchestrator.cli.app tui
```

The `doctor` command currently checks project structure and environment variables, masks API keys, and reports missing or invalid local paths.
The `baseline run` command launches the existing baseline automation entry point through the new control layer and streams logs to the terminal. It requires `EIGEN3_INCLUDE_DIR` to be configured in `.env.local` or the process environment. The TUI also exposes an experimental Run Baseline screen with live logs.
The `experiment run --dry-run` command is safe and does not call an LLM. Real experiment runs may use API tokens configured in `.env.local`; the CLI asks for confirmation unless `--yes` is supplied. The TUI provides experiment config selection with dry-run/real-run controls and live logs.
The results browser is read-only. It lists saved artifacts and opens existing result directories/files, but it does not recalculate metrics, decisions, reports, or modify artifacts. The TUI Browse Results screen provides the same read-only navigation.

See `docs/interactive_terminal_control_layer.md` for the full CLI/TUI command reference and safety notes.

The existing baseline entry point remains `orchestrator/cli/main.py`, and the new command layer does not change optimization, benchmark, validation, materialization, or closed-loop experiment behavior.

## LLM Candidate Generation and Candidate Edit Formats

LLM candidate generation is implemented by `orchestrator.llm.generate_candidate`. It supports two candidate formats selected with `--candidate-type` and experiment `candidate_format.type`.

### `unified_diff`

`unified_diff` is the legacy/fallback format. The LLM receives plain source and returns a `unified_diff` string. Generation writes `candidate.diff`; materialization applies it with `git apply` and can use a `git apply --recount` fallback for malformed hunk counts.

### `line_range_edits`

`line_range_edits` is the preferred robust format for full-cycle LLM experiments. The LLM receives `line_numbered` source and returns structured `edits[]` entries with `file`, `start_line`, `end_line`, `original`, and `replace`. Generation writes `candidate.edits.json`; materialization applies the edits deterministically and writes the system-generated `candidate.generated.diff`.

See `docs/candidate_edit_formats.md` for details.

## Candidate Materialization and Verification

Materialization runs only inside `workspace/candidates/<candidate_run_id>/`.

The materializer enforces `optimization_scope.allowed_files` from experiment configs:

- `unified_diff`: candidate `target_files` and diff header paths must remain allowed.
- `line_range_edits`: candidate `target_files` and `edits[].file` must remain allowed.

Verification configures/builds/runs inside the isolated candidate workspace and writes `verification.json`. It does not call an LLM and does not modify the main `cpp/` source tree.

## Selection and Reporting

Pairwise candidate decision and multi-candidate best-result selection consume verified benchmark artifacts and explicit references. The closed-loop runner uses reference-vs-candidate decisions against the current best for promotion and against the original baseline for reporting.

Selection and final reporting do not promote, merge, copy, or commit candidates into the main source tree.

Generated reports are read-only visualizations under `results/experiments/<experiment_id>/report/`. The single-experiment report uses `schema_version: "report.v2"` and extends the original report with Outcome and Failure Analysis, Phase Timings, LLM Usage, Diff Statistics, Final Repeated Benchmark Validation, and an Iteration Appendix. Final validation aggregates and plots use only successful correctness-passing repetitions. Older or incomplete artifacts are handled through graceful degradation where possible, with missing fields or plots marked as unavailable.

Completed reports can be checked without regenerating anything:

```powershell
python -m orchestrator.reporting.report_inspector --experiment-dir results/experiments/<experiment_id>
```

See `docs/report_v2_checklist.md` for the manual current-report verification checklist.

## External Baseline Code

- `cpp/external/lambdatwist/` contains imported third-party baseline P3P solver code.
- This code is not original project source code.
- Clean baseline files are expected to remain unchanged in repository baseline state.
- Candidate changes are materialized only in isolated workspace copies unless future main-source promotion support is implemented.
