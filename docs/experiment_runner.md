# Experiment Runner

## Overview

The experiment runner is the closed-loop LLM optimization entry point. Every experiment starts from an explicit original baseline run, keeps an experiment-local `current_best_source`, and attempts all configured iterations.

The separate `orchestrator/cli/main.py` entry point remains dedicated to clean baseline configure/build/run/benchmark automation.

Experiment runs use:

- `workspace/` for isolated candidate workspaces and experiment-local mutable source trees.
- `results/` for persistent run and experiment artifacts.

Candidate materialization, verification, reporting, and current-best promotion never modify the main `cpp/` source tree automatically.

## Configs

Experiment configs live under `configs/experiments/`. A config defines:

- `experiment_name` and optional `description`.
- `target_file`: the logical repo-relative source file sent to candidate generation.
- `baseline_run_dir`: required original baseline run directory containing `metrics.json`.
- `candidate_generation`: generation limits such as `max_source_chars`.
- `candidate_format`: selects candidate edit format and source presentation.
- `history_policy`: removed; closed-loop prompts always include compact previous-iteration history internally.
- `optimization_scope.allowed_files`: the strict set of repo-relative files candidates may modify.
- `variants`: exactly one model/config/context/parameter setup.
- `reporting`: optional report generation settings.

Removed config concepts are invalid: `pipeline`, `selection`, `closed_loop`, top-level `llm_config`, top-level `iterations`, and top-level `additional_context`.

Example skeleton:

```json
{
  "experiment_name": "p3p_closed_loop",
  "target_file": "cpp/external/lambdatwist/p3p.cc",
  "baseline_run_dir": "results/runs/<baseline_run_id>",
  "candidate_generation": {"max_source_chars": 120000},
  "candidate_format": {
    "type": "line_range_edits",
    "source_presentation": "line_numbered",
    "require_original_verification": true,
    "allow_exact_search_fallback": true
  },
  "optimization_scope": {
    "allowed_files": ["cpp/external/lambdatwist/p3p.cc"]
  },
  "variants": [
    {
      "variant_id": "deepseek_flash",
      "llm_config": "configs/llm_deepseek_flash.json",
      "iterations": 3,
      "additional_context": "Prefer one small, safe performance improvement per iteration."
    }
  ]
}
```

## Candidate Formats

The experiment runner passes `candidate_format.type` and `candidate_format.source_presentation` to `generate_candidate`.

- `unified_diff`: legacy/fallback format using plain source, `candidate.diff`, and `git apply` materialization.
- `line_range_edits`: preferred robust format using `line_numbered` source, `candidate.edits.json`, deterministic line-range materialization, and system-generated `candidate.generated.diff`.

See `docs/candidate_edit_formats.md` for the dedicated format reference.

## Closed-loop Flow

At experiment start, the runner initializes:

```text
workspace/experiments/<experiment_id>/current_best_source/
workspace/experiments/<experiment_id>/current_best_state.json
```

`current_best_source/` is populated from the clean repository `cpp/` tree into a repo-like layout, for example:

```text
workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc
```

Each planned iteration runs this flow:

1. Build compact closed-loop history from previous meaningful iterations.
2. Run `generate_candidate` with `--source-root workspace/experiments/<experiment_id>/current_best_source`.
3. Detect no-op candidates and record `no_op` without materialization or verification.
4. Run `materialize_candidate` with `--base-source-root workspace/experiments/<experiment_id>/current_best_source`.
5. Run deterministic `verify_candidate` in the isolated candidate workspace.
6. Compare the verified candidate against the current best and write `decision_vs_current_best.json`.
7. Compare the verified candidate against the original baseline and write `decision_vs_original_baseline.json`.
8. Promote only when `decision_vs_current_best.json` has `status: "accepted_improvement"`.

Only `decision_vs_current_best.json` controls promotion. `decision_vs_original_baseline.json` is for reporting/control and does not control promotion.

## Finalization

After all iterations finish, the runner writes:

```text
results/experiments/<experiment_id>/final_optimized_source/
results/experiments/<experiment_id>/final_optimized_source.diff
results/experiments/<experiment_id>/final_diff_stats.json
results/experiments/<experiment_id>/closed_loop_iterations.jsonl
results/experiments/<experiment_id>/closed_loop_summary.json
results/experiments/<experiment_id>/closed_loop_selection_report.json
results/experiments/<experiment_id>/current_best_state.json
results/experiments/<experiment_id>/final_selection_report.json
results/experiments/<experiment_id>/final_selection/
```

`closed_loop_selection_report.json` is reporting-only. It records the already-made control decision and safety flags; it does not promote candidates, rewrite `current_best_source`, rewrite `final_optimized_source`, or modify the main `cpp/` tree.

`final_selection_report.json` runs one final benchmark on the final optimized source and compares it against the original baseline. It does not call an LLM, rerun every candidate, or affect promotion decisions.

Automatic reporting runs only after closed-loop final artifacts and the final single-run comparison are written. It creates files under `results/experiments/<experiment_id>/report/`, including `report_data.json`, `report.html`, plots, and optionally `report.pdf`.

## Verification and Decisions

`verify_candidate` is deterministic and does not call any LLM API. It configures CMake, builds/runs smoke and adapter checks, runs `absolute_pose_lambdatwist_benchmark`, parses benchmark stdout into `verification.json`, and fails verification if parsed correctness is false.

Candidate verification builds default to **Release** for accurate runtime metrics. Set `CMAKE_BUILD_TYPE=Debug` in the environment to override. The final single-run comparison uses the same CMake environment conventions.

Pairwise decisions use `orchestrator.benchmarking.candidate_decision`:

- `reference_kind="baseline"` loads reference metrics from `<reference_run_dir>/metrics.json`.
- `reference_kind="verified_candidate"` loads reference metrics from `<reference_run_dir>/verification.json`.

## Compact Closed-loop History

Closed-loop prompt history summarizes meaningful previous iterations and combines that summary with the variant's `additional_context`. It can include accepted improvements, valid-but-not-improved candidates, rejected candidates, materialization failures with usable candidate information, and verification failures with usable candidate information.

The history excludes no-op iterations and generation failures without usable candidate information. It intentionally does not include full source code, full diffs, full `candidate.json`, full `verification.json`, benchmark logs, audit objects, stack traces, or no-op entries.

The exact history context used for each iteration is logged under:

```text
results/experiments/<experiment_id>/logs/iteration_003_closed_loop_history_context.txt
```

## Optimization Scope

The main optimization pipeline enforces a strict optimization scope. LLM candidates may modify only files listed in `optimization_scope.allowed_files`.

Fixed evaluation infrastructure cannot be changed by optimization candidates: benchmark code, adapters, validators, CMake files, Python orchestrator code, configs, docs, tests, result storage, comparator, audit, and parser code.

## Limitations

- Exactly one variant is supported.
- Automatic promotion of candidates into the main `cpp/` source tree is not implemented.
- Multi-variant closed-loop strategies are future work.
- Additional solver families/adapters beyond the current minimal Lambda Twist P3P path are future work.
