# Usage

All commands use the Typer CLI entry point: `python -m orchestrator.cli.app <command>`.

## Quick Start

```bash
python -m pip install -e ".[dev]"
python -m playwright install chromium
copy .env.example .env.local      # then fill in paths and keys
python -m orchestrator.cli.app doctor
```

## Diagnostics

| Command | Description |
|---|---|
| `doctor` | Show environment status, API key presence, project directories |
| `tui` | Launch the Textual terminal UI |

## Baseline

Run the C++ benchmark for a solver to produce baseline metrics:

```bash
python -m orchestrator.cli.app baseline run --solver poselib_p3p_lambdatwist
```

- `--solver` is optional; defaults to `poselib_p3p_lambdatwist`.
- Baseline artifacts are stored under `results/runs/`.
- Requires `EIGEN3_INCLUDE_DIR` set.

## Experiment Configs

Experiment configs define the LLM optimization task. Two storage locations:

| Location | Purpose |
|---|---|
| `configs/experiments/templates/` | Committed template configs (`.template.json`) |
| `configs/experiments/local/` | User-generated configs (`.json`, gitignored) |

Configs use a flat structure. See `configs/experiments/templates/basic.template.json` for the canonical shape. Key fields:

- `experiment_name`, `solver_id`, `target_file`, `baseline_run_dir`
- `llm_config` — path to an LLM config JSON (e.g. `configs/llm_deepseek_flash.json`)
- `llm_overrides` — optional overrides for provider, model, thinking, max_tokens
- `iterations` — number of closed-loop optimization iterations
- `optimization_scope.allowed_files` — files the LLM may edit
- `reporting` — enable/disable HTML/PDF report generation
- `selection.gt_found_max_drop_points` — optional correctness gate

The TUI Config Builder provides a form-based interface for creating and editing configs. See [docs/config_builder.md](config_builder.md).

List saved configs:

```bash
python -m orchestrator.cli.app experiment list
```

## Experiment Run

```bash
# Dry run — validates config, no LLM calls
python -m orchestrator.cli.app experiment run --config configs/experiments/local/my-exp.json --dry-run

# Real run — will call LLM APIs (confirms unless --yes)
python -m orchestrator.cli.app experiment run --config configs/experiments/local/my-exp.json --yes
```

- `--dry-run` is safe and does not call an LLM.
- Real runs require a valid API key (e.g. `DEEPSEEK_API_KEY` for DeepSeek configs).
- Real runs prompt for confirmation unless `--yes` is passed.

## Results

```bash
python -m orchestrator.cli.app results list                         # all saved runs
python -m orchestrator.cli.app results latest                       # most recent result
python -m orchestrator.cli.app results show latest                  # full details
python -m orchestrator.cli.app results show <name-or-path>
python -m orchestrator.cli.app results open latest                  # open in file explorer
python -m orchestrator.cli.app results open latest --artifact report
```

Available `--artifact` values: `directory`, `summary`, `final-source`, `final-diff`, `final-selection-dir`, `final-selection-report`, `report`.

## Workspace Cleanup

```bash
python -m orchestrator.cli.app workspace status
python -m orchestrator.cli.app workspace clean-candidates --yes
python -m orchestrator.cli.app workspace clean-experiments --yes
python -m orchestrator.cli.app workspace clean-all --yes
```

- `status` shows workspace size, candidate count, experiment count.
- Cleanup commands delete entries inside `workspace/` only.
- Omit `--yes` for interactive confirmation.

## Safety Guarantees

- The control layer launches existing Python entry points; it does **not** reimplement baseline or experiment logic.
- The results browser is **read-only** — it never recalculates metrics, decisions, or reports, and never promotes candidates.
- Workspace cleanup only deletes data inside `workspace/`; it never touches `results/`.
- Candidate materialization does **not** modify the main `cpp/` source tree.
- API keys and other secrets are masked in CLI and TUI displays.
- Experiment runs launched from the TUI are non-blocking — they continue in the background. See [docs/parallel_runs.md](parallel_runs.md).
