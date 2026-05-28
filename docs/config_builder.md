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

| Field | Widget | Description |
|---|---|---|
| `experiment_name` | Input | Name of the experiment. |
| `description` | Input | Optional description. |
| Algorithm (`solver_id`) | Select | Solver to optimize, populated from manifests. |
| `target_file` | Input | Repo-relative path of the source file the LLM will edit. |
| `optimization_scope.allowed_files` | TextArea | One file path per line; the LLM may only touch these files. |
| `baseline_run_dir` | Select | Select a completed baseline run. |
| `reporting.enabled` | Switch | Enable/disable reporting (controls HTML switch + PDF select). |
| `reporting.formats` | HTML Switch + PDF Select | Toggle HTML report generation and select PDF renderer (`auto`, `weasyprint`, or `playwright`). |
| `selection.gt_found_max_drop_points` | Input | Optional correctness gate (see below). |
| `variant_id` | Input | Variant identifier (auto-generated if empty). |
| `llm_config` | Select | LLM config file under `configs/`. |
| `llm_overrides.provider` | Select | Override LLM provider or use config default. |
| `llm_overrides.model` | Input | Override model name. |
| `llm_overrides.max_tokens` | Input | Override max tokens. |
| `llm_overrides.thinking.enabled` | Switch | Enable thinking mode. |
| `llm_overrides.thinking.effort` | Select | Thinking effort: `low`, `medium`, or `high`. |
| `iterations` | Input | Number of closed-loop iterations (default 3). |
| `additional_context` | TextArea | Optional context injected into the LLM prompt. |

## `selection.gt_found_max_drop_points`

This is an optional correctness gate that limits how much the ground-truth
found percentage can regress.

- **Empty / `null`**: the gate is disabled. `gt_found` is observed and
  reported but does not block candidate acceptance.
- **Number**: maximum allowed drop in **percentage points** compared to
  the reference. For example, if the reference achieves 100.0% gt_found and
  the configured value is 2.0, a candidate at 97.5% would be rejected
  (drop of 2.5 pp > 2.0 pp).

This gate applies to current-best iteration decisions and to the final
selection comparison. GT-found deltas are always recorded in decision
comparison metadata, even when the gate is disabled.

## Validation

All three actions that write or run a config validate the payload through
`load_experiment_config`:

- **Validate**: dry-runs validation and reports errors in the build log.
- **Save to local/**: validates, then writes the config. A second
  validation pass ensures the saved file is loadable.
- **Save & Run**: validates, saves, then shows a **paid-run confirmation**
  dialog. This is because real experiment runs may use paid LLM APIs. Only
  after explicit confirmation does the run start.

Invalid configs cannot be saved or run.

## Relationship to LLM

The LLM receives only the configured `target_file` and
`optimization_scope.allowed_files`. Benchmark files, adapter sources,
CMake files, and other infrastructure code are never sent to the LLM by
default.

## Example Config

```json
{
  "experiment_name": "example-poselib-p3p",
  "description": null,
  "solver_id": "poselib_p3p",
  "target_file": "cpp/external/poselib/PoseLib/solvers/p3p.cc",
  "baseline_run_dir": "results/runs/2026-01-01_12-00-00_baseline",
  "optimization_scope": {
    "allowed_files": ["cpp/external/poselib/PoseLib/solvers/p3p.cc"]
  },
  "reporting": {
    "enabled": true,
    "formats": ["html"],
    "renderer": "auto"
  },
  "selection": {"gt_found_max_drop_points": null},
  "variants": [
    {
      "variant_id": "default",
      "description": null,
      "llm_config": "configs/llm_deepseek_flash.json",
      "llm_overrides": null,
      "iterations": 3,
      "additional_context": null
    }
  ]
}
```
