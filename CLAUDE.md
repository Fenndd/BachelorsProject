# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bachelor thesis prototype for **automated optimization of C++ 3D vision algorithms using LLMs**. The current case study is the Lambda Twist P3P solver in the absolute-pose solver benchmark family. C++ provides the algorithm/benchmark layer; Python orchestrates baseline runs, LLM candidate generation, materialization, verification, and closed-loop experiments.

## Common Commands

All Python commands assume `EIGEN3_INCLUDE_DIR` is set (in `.env.local` or the shell). On Windows outside CLion, you may also need `CMAKE_EXE`, `CMAKE_GENERATOR`, `CMAKE_CXX_COMPILER`, and `CMAKE_MAKE_PROGRAM`. See [docs/setup.md](docs/setup.md).

```powershell
python -m pip install -r requirements.txt
copy .env.example .env.local   # then fill in local paths and API keys
```

### Baseline (clean run, no LLM)

```powershell
py orchestrator/cli/main.py                           # legacy direct entry point
python -m orchestrator.cli.app baseline run           # via control layer (streams logs)
```

Both configure CMake, build `baseline_smoke_test`, `baseline_runner`, `absolute_pose_lambdatwist_adapter_validator`, `absolute_pose_lambdatwist_benchmark`, run them, parse benchmark metrics, and write a run under `results/runs/<run_id>/` plus an entry in `results/index.jsonl`. Benchmark/evaluation builds default to **Release**.

### Experiments (LLM optimization)

```powershell
python -m orchestrator.cli.app experiment list
python -m orchestrator.cli.app experiment run --config configs/experiments/mock_p3p_basic.json --dry-run
python -m orchestrator.cli.app experiment run --config configs/experiments/<file>.json --yes
```

Mock configs (`configs/experiments/mock_*.json`) do not call an LLM and need no API key. Real DeepSeek runs require `DEEPSEEK_API_KEY` in `.env.local`.

### Diagnostics, results, workspace, TUI

```powershell
python -m orchestrator.cli.app doctor                  # env + paths sanity check (masks secrets)
python -m orchestrator.cli.app results latest          # most recent run id
python -m orchestrator.cli.app results show latest
python -m orchestrator.cli.app results open latest
python -m orchestrator.cli.app workspace status
python -m orchestrator.cli.app workspace clean-candidates --yes
python -m orchestrator.cli.app workspace clean-experiments --yes
python -m orchestrator.cli.app tui                     # Textual TUI
```

### Tests

```powershell
python -m pytest                              # all tests
python -m pytest tests/test_cli_app.py        # one file
python -m pytest tests/test_cli_app.py::<name>   # one test
python -m pytest orchestrator/experiments/    # tests collocated with modules also run
```

Python tests live both under top-level `tests/` and inline as `test_*.py` next to the modules under `orchestrator/`.

## Architecture

### Two separate Python entry points

- **`orchestrator/cli/main.py`** — baseline-only automation. Configures CMake, builds, runs, parses the absolute-pose family benchmark. Never calls an LLM.
- **`orchestrator.experiments.run_experiment`** — LLM optimization experiments. Drives generation → materialization → verification → decision → optional closed-loop promotion.

The newer `orchestrator/cli/app.py` (Typer) is a **control layer**: it launches these existing entry points and reads existing artifacts. It does not reimplement pipeline logic.

### Pipeline stages (orchestrator/ submodules)

- `orchestrator.llm.generate_candidate` — reads source from a configurable `--source-root`, prompts the configured LLM (or mock), parses the response, writes candidate artifacts.
- `orchestrator.patching.materialize_candidate` — applies a candidate against `--base-source-root` inside `workspace/candidates/<candidate_run_id>/` only. Enforces `optimization_scope.allowed_files` from experiment configs.
- `orchestrator.execution.verify_candidate` — configure/build/run/parse inside the isolated candidate workspace; writes `verification.json`.
- `orchestrator.benchmarking.candidate_decision` — pairwise decision between a candidate and a reference (baseline run or another verified candidate).
- `orchestrator.experiments.best_candidate_selector` — picks the best candidate among verified ones (non-closed-loop analysis).
- `orchestrator.experiments.closed_loop_state` + `closed_loop_history` — manage experiment-local `current_best_source` and compact prompt history.
- `orchestrator.experiments.run_experiment` — top-level driver for both non-closed-loop and single-variant closed-loop runs.
- `orchestrator.control.*` — control-layer adapters used by the Typer CLI and TUI.

### Hard boundaries — do not violate

- **The main `cpp/` source tree is never modified by candidate materialization or closed-loop promotion.** Candidate edits live in `workspace/candidates/<id>/` and (in closed loop) `workspace/experiments/<id>/current_best_source/`.
- `cpp/external/lambdatwist/` is **imported third-party code**; clean baseline files must remain unchanged in repo state.
- `workspace/` is mutable, regenerable, git-ignored. `results/` is persistent.
- Results browser, selection, and final reporting are **read-only**: they never promote candidates or modify source trees.

### Candidate edit formats (selected via `candidate_format.type`)

- `unified_diff` (legacy/fallback) — LLM returns a diff; materializer uses `git apply` with an optional `git apply --recount` fallback. Stored as `candidate.diff`.
- `line_range_edits` (preferred for full-cycle runs) — LLM sees `line_numbered` source and returns `edits[]` with `file`, `start_line`, `end_line`, `original`, `replace`. Materializer verifies `original` text at the line range before applying. Stored as `candidate.edits.json` plus a system-generated `candidate.generated.diff`.

See [docs/candidate_edit_formats.md](docs/candidate_edit_formats.md).

### Closed-loop control flow

Enabled via `closed_loop.enabled: true` in an experiment config (requires `selection.baseline_run_dir`). Single-variant only.

```
clean baseline
  -> workspace/experiments/<experiment_id>/current_best_source/
  -> generate (--source-root current_best_source)
  -> materialize (--base-source-root current_best_source)
  -> verify
  -> decision_vs_current_best   (controls promotion)
  -> decision_vs_original_baseline   (reporting only)
  -> optional promotion of current_best_source
  -> next iteration
```

Logical `target_file` paths (e.g. `cpp/external/lambdatwist/p3p.cc`) stay repo-relative across iterations; only the physical source root changes. Final artifacts land under `results/experiments/<experiment_id>/`: `final_optimized_source/`, `final_optimized_source.diff`, `closed_loop_summary.json`, `closed_loop_iterations.jsonl`, `closed_loop_selection_report.json`, `current_best_state.json`.

See [docs/closed_loop_optimization.md](docs/closed_loop_optimization.md).

### C++ layer

- CMake project rooted at [cpp/CMakeLists.txt](cpp/CMakeLists.txt), C++20, requires Eigen via `EIGEN3_INCLUDE_DIR` (must contain `Eigen/Core`).
- Key targets: `lambdatwist_baseline` (static lib wrapping imported solver), `baseline_runner`, `baseline_smoke_test`, `baseline_benchmark` (legacy, still built), `absolute_pose_lambdatwist_adapter_validator`, `absolute_pose_lambdatwist_benchmark`, `absolute_pose_correctness_policy_test`.
- Project-owned benchmark code lives under [cpp/bench/families/geometric_pose_solvers/absolute_pose_solvers/](cpp/bench/families/geometric_pose_solvers/absolute_pose_solvers/).

## Configs

- `configs/experiments/*.json` — experiment definitions (`target_file`, `pipeline`, `candidate_generation`, `candidate_format`, `history_policy`, `selection`, `closed_loop`, `variants`, `optimization_scope.allowed_files`).
- `configs/llm_*.json` — LLM client configs (DeepSeek flash/pro/pro_max, mock).
- `configs/mock_candidates/` — canned candidates used by mock LLM configs.

## Important Reference Docs

- [docs/architecture.md](docs/architecture.md) — top-level architecture
- [docs/experiment_runner.md](docs/experiment_runner.md) — config schema and runner semantics
- [docs/closed_loop_optimization.md](docs/closed_loop_optimization.md)
- [docs/candidate_edit_formats.md](docs/candidate_edit_formats.md)
- [docs/result_storage_format.md](docs/result_storage_format.md)
- [docs/best_result_selection_policy.md](docs/best_result_selection_policy.md)
- [docs/interactive_terminal_control_layer.md](docs/interactive_terminal_control_layer.md)
- [docs/setup.md](docs/setup.md) — toolchain targets and env vars
