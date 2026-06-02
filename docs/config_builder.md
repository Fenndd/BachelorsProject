# Config Builder

## Purpose

The TUI Config Builder lets you create and edit experiment JSON configs
without manually editing JSON files. Access it from the MainScreen via the
**Build Config** button.

## Storage Layout

```
configs/experiments/
  templates/          versioned template configs (*.template.json)
  local/              user-generated configs (*.json)
```

- **Templates** (`configs/experiments/templates/*.template.json`) are
  committed to the repository and serve as starting points.
- **Local configs** (`configs/experiments/local/*.json`) are user-generated
  and ignored by git.
- Use **Load Template** to populate the form from a committed template.
- Use **Load Local** to reload a previously saved local config for editing.

## Main Fields

| Field | Description |
|---|---|
| `experiment_name` | Name of the experiment. |
| `description` | Optional description. |
| `solver_id` | Solver to optimize, populated from manifests. |
| `target_file` | Repo-relative path of the source file the LLM will edit. |
| `optimization_scope.allowed_files` | One file path per line; the LLM may only touch these files. |
| `baseline_run_dir` | Select a completed baseline run. |
| `reporting.enabled` | Enable/disable report generation. |
| `reporting.formats` | `html`, `pdf`, or both. |
| `reporting.renderer` | PDF renderer: `auto`, `weasyprint`, or `playwright`. |
| `selection.gt_found_max_drop_points` | Optional correctness gate (see below). |
| `llm_config` | LLM config file under `configs/`. |
| `llm_overrides.provider` | Override LLM provider. |
| `llm_overrides.model` | Override model name. |
| `llm_overrides.max_tokens` | Override max tokens. |
| `llm_overrides.thinking.enabled` | Enable thinking mode. |
| `llm_overrides.thinking.effort` | Thinking effort: `low`, `medium`, or `high`. |
| `iterations` | Number of closed-loop iterations. |
| `additional_context` | Optional context injected into the LLM prompt. |

## `selection.gt_found_max_drop_points`

Optional correctness gate that limits how much the ground-truth found
percentage can regress.

- **Empty / `null`**: the gate is disabled.
- **Number**: maximum allowed drop in **percentage points** compared to
  the baseline reference.

## Validation

All actions that write or run a config validate the payload:

- **Validate**: reports errors without saving.
- **Save to local/**: validates, then writes the config.
- **Save & Run**: validates, saves, then shows a paid-run confirmation
  dialog before starting the experiment.

Invalid configs cannot be saved or run.

## Relationship to LLM

The LLM receives only the configured `target_file` and
`optimization_scope.allowed_files`. Benchmark files, adapter sources,
CMake files, and other infrastructure code are never sent to the LLM.

## Example Config

```json
{
  "experiment_name": "example-p3p-lambdatwist",
  "description": null,
  "solver_id": "poselib_p3p_lambdatwist",
  "target_file": "cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc",
  "baseline_run_dir": "results/runs/2026-01-01_12-00-00_baseline",
  "optimization_scope": {
    "allowed_files": ["cpp/external/poselib/PoseLib/solvers/p3p_lambdatwist.cc"]
  },
  "reporting": {
    "enabled": true,
    "formats": ["html"],
    "renderer": "auto"
  },
  "selection": {"gt_found_max_drop_points": null},
  "llm_config": "configs/llm_deepseek_flash.json",
  "llm_overrides": null,
  "iterations": 3,
  "additional_context": "Optimize the solver for runtime while preserving correctness."
}
```
