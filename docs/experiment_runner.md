# Experiment Runner

## Overview

The experiment runner is the main entry point for LLM optimization experiments. It coordinates candidate generation, materialization, verification, decision artifacts, optional best-candidate selection, and closed-loop iterative optimization.

The separate `orchestrator/cli/main.py` entry point remains dedicated to clean baseline configure/build/run/benchmark automation.

Experiment runs use:

- `workspace/` for isolated candidate workspaces and experiment-local mutable source trees.
- `results/` for persistent run and experiment artifacts.

Materialization, verification, selection, and closed-loop current-best promotion never modify the main `cpp/` source tree automatically.

## Configs

Experiment configs live under `configs/experiments/`. A config defines:

- `target_file`: the logical repo-relative source file sent to candidate generation.
- `pipeline`: which non-benchmark stages are enabled.
- `candidate_generation`: generation limits such as `max_source_chars`.
- `candidate_format`: selects candidate edit format and source presentation.
- `history_policy`: optional variant-local prompt history for non-closed-loop runs.
- `selection`: optional baseline-vs-candidates best-result selection and, in closed-loop mode, the required original baseline reference.
- `closed_loop`: optional iterative current-best optimization mode.
- `variants`: one or more model/config/context/parameter setups.
- `optimization_scope.allowed_files`: the strict set of repo-relative files candidates may modify.

Single-setup legacy configs remain supported by creating one synthetic `default` variant.

Example line-range candidate format config:

```json
{
  "candidate_format": {
    "type": "line_range_edits",
    "source_presentation": "line_numbered",
    "require_original_verification": true,
    "allow_exact_search_fallback": true
  }
}
```

Closed-loop mode is enabled with:

```json
{
  "closed_loop": {
    "enabled": true
  },
  "selection": {
    "enabled": false,
    "baseline_run_dir": "results/runs/<baseline_run_id>"
  }
}
```

`selection.baseline_run_dir` is required in closed-loop mode as the original baseline reference, even when final non-closed-loop selection is disabled.

## Candidate Formats

The experiment runner passes `candidate_format.type` and `candidate_format.source_presentation` to `generate_candidate`.

- `unified_diff`: legacy/fallback format using plain source, `candidate.diff`, and `git apply` materialization.
- `line_range_edits`: preferred robust format using `line_numbered` source, `candidate.edits.json`, deterministic line-range materialization, and system-generated `candidate.generated.diff`.

See `docs/candidate_edit_formats.md` for the dedicated format reference.

## Non-closed-loop Mode

Non-closed-loop mode supports multiple variants and multiple iterations. Each variant has its own:

- `variant_id`
- base `llm_config`
- optional `llm_overrides`
- iteration count
- additional prompt context

The runner executes all iterations for each variant and records both global and variant-local iteration numbers.

Enabled stages run in this order:

1. `generate_candidate`
2. `materialize_candidate`
3. `verify_candidate`

If a stage fails, later stages for that iteration are skipped. The experiment continues with later iterations and variants.

When `history_policy.enabled` is true, later non-closed-loop iterations receive a compact summary of previous attempts from the same variant only. History is not shared between variants. The context excludes full diffs, full LLM responses, and reasoning content.

Per-variant history artifacts are saved under:

```text
results/experiments/<experiment_id>/variants/<variant_id>/
```

## Closed-loop Mode

Closed-loop mode is implemented as a single-variant iterative optimization chain. It optimizes the current best accepted source instead of repeatedly optimizing the original baseline.

Closed-loop constraints:

- exactly one variant is supported; multiple variants fail with a clear error
- `selection.baseline_run_dir` is required and must contain the original baseline `metrics.json`
- all planned iterations are attempted; there is no early stopping
- current-best promotion is experiment-local only
- multi-variant closed-loop strategies are not implemented

At experiment start, the runner initializes:

```text
workspace/experiments/<experiment_id>/current_best_source/
workspace/experiments/<experiment_id>/current_best_state.json
```

`current_best_source/` is populated from the clean repository `cpp/` tree into a repo-like layout, for example:

```text
workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc
```

The main `cpp/` source tree remains the clean baseline and is never modified automatically.

## Generation Source Root

Candidate generation separates the logical target file from the physical source root used for reading source code. By default, `--source-root` is the repository root, so non-closed-loop commands read `cpp/external/lambdatwist/p3p.cc` from the clean repo source tree.

In closed-loop mode, `generate_candidate` reads from the experiment-local current-best source tree:

```text
--source cpp/external/lambdatwist/p3p.cc
--source-root workspace/experiments/<experiment_id>/current_best_source
```

This reads the physical file:

```text
workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc
```

The LLM prompt, candidate `target_files`, `allowed_files`, and candidate metadata still use the stable repo-relative logical path `cpp/external/lambdatwist/p3p.cc`. The temporary workspace path is recorded in artifacts for traceability but is not presented as the optimization target file.

## Materialization Base Source Root

Candidate materialization separates logical repo-relative candidate paths from the physical source tree copied into the isolated workspace.

By default, old behavior is preserved: `materialize_candidate` copies the legacy `--source-root` value, which defaults to `cpp`, into the candidate workspace so paths such as `cpp/external/lambdatwist/p3p.cc` resolve under `workspace/candidates/<candidate_run_id>/cpp/...`.

In closed-loop mode, materialization uses an explicit repo-like base source root:

```text
--base-source-root workspace/experiments/<experiment_id>/current_best_source
```

`--base-source-root` must contain repo-relative paths directly, for example:

```text
workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc
```

The materializer copies that tree into the isolated candidate workspace and applies the candidate there. It never modifies `--base-source-root` directly and never modifies the main `cpp/` source tree automatically.

`--source-root` remains supported for backward compatibility. To avoid ambiguous copy semantics, an explicit `--source-root` cannot be combined with `--base-source-root`.

For `line_range_edits`, `candidate.generated.diff` is generated by comparing the copied base source before edits with the candidate workspace after edits. In closed-loop runs, this is an iteration-local diff from `current_best_source` to that candidate.

`materialization.json` includes `diff_stats` for the applied or generated unified
diff. For line-range candidates, the stats are parsed from
`candidate.generated.diff` and include `edit_count` plus whether exact-search
fallback was used. For legacy unified diffs, the stats are parsed from
`candidate.diff`.

## Iteration Flow

In closed-loop mode, each planned iteration runs this flow:

1. Build compact closed-loop history from previous meaningful iterations.
2. Run `generate_candidate` with `--source-root workspace/experiments/<experiment_id>/current_best_source` and, when context exists, `--context <additional context plus closed-loop history>`.
3. Detect no-op candidates and record `no_op` without materialization or verification.
4. Run `materialize_candidate` with `--base-source-root workspace/experiments/<experiment_id>/current_best_source`.
5. Run deterministic `verify_candidate` in the isolated candidate workspace.
6. Compare the verified candidate against the current best and write `decision_vs_current_best.json`.
7. Compare the verified candidate against the original baseline and write `decision_vs_original_baseline.json`.
8. If `decision_vs_current_best.json` has `status: "accepted_improvement"`, replace experiment-local `current_best_source` with the materialized candidate workspace and update `current_best_state.json`.

Only `decision_vs_current_best.json` controls promotion. `decision_vs_original_baseline.json` is for reporting/control and does not control promotion.

Each closed-loop JSONL iteration record includes optional `phase_timings` for
generation, materialization, verification, benchmark, and total iteration
wall-clock durations. Stage durations come from the existing subprocess timing
records. `benchmark_seconds` may be `null` until verification exposes a separate
benchmark-only duration.

Each record also includes an optional `outcome_reason` object for new runs. It
normalizes why the iteration reached its status without changing how that status
is computed. Categories are `generation`, `no_op`, `materialization`,
`verification`, `decision`, and `unknown`; severities are `info`, `warning`, and
`error`. Example codes include `llm_response_parse_failed`,
`line_range_mismatch`, `benchmark_correctness_failed`, `accepted_improvement`,
and `valid_not_improved`. Older records without this field are reconstructed
best-effort by the report data collector from existing candidate artifacts.

No-op candidates are recorded as `no_op` when `expected_effect="none"` and the edit payload is empty (`edits` for `line_range_edits`, or `unified_diff` for `unified_diff`).

## Experiment Metadata

Experiment runs write:

```text
results/experiments/<experiment_id>/experiment_metadata.json
```

The artifact contains `experiment_metadata.v1` process metadata: start/end time,
total duration, selected git state, OS/platform/Python version, and selected CMake
environment fields. It does not persist API keys or full environment variables.

Closed-loop finalization also writes:

```text
results/experiments/<experiment_id>/final_diff_stats.json
```

The same final diff summary is embedded as `final_diff_stats` in
`closed_loop_summary.json` for reporting consumers.

The normalized `report/report_data.json` artifact uses `schema_version:
"report.v2"`. It includes per-iteration `outcome_reason` and top-level
`reason_code_counts`, grouped by reason category and code. The existing
`reason_summary` remains for compatibility with older incomplete artifacts.

## Verification and Decisions

`verify_candidate` is deterministic and does not call any LLM API. It uses the same benchmark-family verification path as baseline preparation:

1. configure CMake in the isolated workspace
2. build and run `baseline_smoke_test`
3. build and run the Lambda Twist P3P adapter validator
4. build and run `absolute_pose_lambdatwist_benchmark`
5. parse the family benchmark stdout into `verification.json`

If parsing succeeds but `correctness_passed=false`, verification fails at `benchmark_correctness_check` while preserving parsed metrics.

Candidate verification builds default to **Release** for accurate runtime metrics. Set `CMAKE_BUILD_TYPE=Debug` in the environment to override. The build type is recorded in `verification.json`.

Pairwise candidate decisions and multi-candidate best-result selection consume verified artifacts and audit comparability. The reference-vs-candidate decision path supports:

- `reference_kind="baseline"` for references storing benchmark metrics in `metrics.json`
- `reference_kind="verified_candidate"` for references storing benchmark metrics in `verification.json`

The old baseline-vs-candidate command path remains supported and writes `candidate_decision.json` by default.

## Compact Closed-loop History

Closed-loop mode uses a dedicated compact history builder instead of the non-closed-loop variant-local `history_policy` sliding window. Before each generation stage, it summarizes all meaningful previous closed-loop iterations and combines that summary with the variant's `additional_context`.

The history tells the LLM that it is improving the current best source, not the original baseline. It can include:

- `accepted_improvement`: accepted changes already included in `current_best_source`
- `valid_not_improved`: correct candidates that were not faster than the current best
- `rejected`: candidates that failed correctness or selection gates
- `materialization_failed`: candidates with usable candidate information whose edits could not be applied
- `verification_failed`: candidates with usable candidate information that broke build, tests, benchmark execution, API compatibility, or metric generation

The history excludes no-op iterations and generation failures without usable candidate information. Generation failures with candidate summaries are also excluded by the current deterministic policy because they are not reliable optimization patterns.

History entries are plain compact text. They include candidate summaries, speedups/runtime information when available, short failure or rejection reasons, and deterministic guidance such as "this improvement is already included" or "do not repeat this optimization pattern." They intentionally do not include full source code, full diffs, full `candidate.json`, full `verification.json`, benchmark logs, audit objects, stack traces, or no-op entries.

The exact closed-loop history context used for each iteration is logged under:

```text
results/experiments/<experiment_id>/logs/iteration_003_closed_loop_history_context.txt
```

If no meaningful history exists yet, the log contains:

```text
No meaningful closed-loop history yet.
```

Each `closed_loop_iterations.jsonl` record also includes:

- `history_included`: whether this iteration will be included in future closed-loop history
- `history_guidance`: the deterministic guidance string for included records, or `null` for excluded records

## Final Artifacts

A normal experiment writes:

```text
results/experiments/<experiment_id>/
|- experiment_config_snapshot.json
|- experiment_status.json
|- iterations.jsonl
|- summary.txt
|- best_candidate_selection.json   # only when selection.enabled=true in non-closed-loop selection
|- logs/
|- variants/
|  `- <variant_id>/
|     |- variant_history.jsonl
|     `- variant_summary.txt
`- variant_configs/
   `- <variant_id>_llm_config.json
```

Closed-loop mode additionally writes:

```text
results/experiments/<experiment_id>/final_optimized_source/
results/experiments/<experiment_id>/final_optimized_source.diff
results/experiments/<experiment_id>/closed_loop_iterations.jsonl
results/experiments/<experiment_id>/closed_loop_summary.json
results/experiments/<experiment_id>/closed_loop_selection_report.json
results/experiments/<experiment_id>/current_best_state.json
```

`closed_loop_iterations.jsonl` stores one compact JSON object per closed-loop iteration and is append-only during the run. The workspace `current_best_state.json` is updated after every iteration. At finalization, the runner also copies the final current-best metadata to the results directory as `current_best_state.json`.

`final_optimized_source/` is a copy of the final `workspace/experiments/<experiment_id>/current_best_source/` tree. If no candidate was accepted, it is still written and is baseline-equivalent.

`final_optimized_source.diff` is a unified diff from the original clean baseline source in `REPO_ROOT/<target_file>` to the final optimized source. It covers at least `target_file`. If the final source is unchanged, the diff file is written but empty.

`closed_loop_summary.json` records the experiment id, target file, total and completed iterations, original baseline paths, final best iteration, final best candidate run directory when applicable, final optimized source paths, final speedup/runtime reduction versus the original baseline when available, iterations after the final best, all closed-loop status counts including zero values, and timestamps.

`experiment_status.json` includes a `closed_loop` block with final artifact paths, accepted improvement count, final best iteration, final speedup/runtime reduction, and status counts. The human-readable `summary.txt` includes a concise closed-loop section with the same final artifact locations.

Closed-loop reports can be enabled with a top-level `reporting` block:

```json
"reporting": {
  "enabled": true,
  "formats": ["html"],
  "renderer": "auto",
  "fail_on_error": false
}
```

Automatic reporting runs only after closed-loop final artifacts are written. It creates files under `results/experiments/<experiment_id>/report/`, including `report_data.json`, `report.html`, `plots/*.svg`, and optionally `report.pdf` when `pdf` is requested. Reporting is read-only post-processing: it does not run LLM generation, verification, benchmarking, candidate promotion, source copying, or selection recomputation.

The single-experiment HTML/PDF report includes runtime, correctness, status, candidate funnel, configuration, selection, final-best, reporting-status, and artifact sections. The same unified report also surfaces enriched process metadata when present:

- Outcome and Failure Analysis: structured outcome reason counts by category/code and affected iterations, including successful, neutral, rejected, and failed iterations.
- Phase Timings: per-iteration generation, materialization, verification, benchmark, and total durations.
- LLM Usage: per-iteration token counts, API latency, model, and finish reason.
- Diff Statistics: final diff summary and per-iteration changed-line/edit statistics.
- Iteration Appendix: compact per-iteration cards with candidate summary, status, outcome reason, runtime, correctness, timings, LLM usage, diff stats, and candidate run directory.

Report generation remains compatible with older or incomplete `report_data.json` artifacts where possible. If enriched fields such as `phase_timings`, `llm_usage`, `diff_stats`, `outcome_reason`, or `reason_code_counts` are absent, HTML/PDF generation still succeeds and marks those values or plots as unavailable.

Reports can also be generated manually for a completed experiment:

```powershell
python -m orchestrator.reporting.generate_report --experiment-dir results/experiments/<experiment_id>
```

Existing reports can be inspected without regenerating files:

```powershell
python -m orchestrator.reporting.report_inspector --experiment-dir results/experiments/<experiment_id>
python -m orchestrator.reporting.report_inspector --experiment-dir results/experiments/<experiment_id> --json
```

The inspector is read-only. It checks report files, expected SVG plots, and HTML
section ids, warning about optional missing pieces such as an absent PDF for
HTML-only reports. See `docs/report_v2_checklist.md` for the manual current-report
verification checklist.

Candidate run artifacts are written under `results/runs/<candidate_run_id>/`:

```text
results/runs/<candidate_run_id>/
|- metadata.json
|- status.json
|- summary.txt
|- llm_request.json
|- llm_response.json
|- candidate.json
|- candidate.diff             # unified_diff only
|- candidate.edits.json       # line_range_edits only
|- candidate.generated.diff   # line_range_edits after materialization
|- materialization.json
|- apply_candidate.log
|- verification.json
|- verification_summary.txt
|- candidate_decision.json              # compatibility/default pairwise decision
|- decision_vs_current_best.json        # closed-loop promotion decision
|- decision_vs_original_baseline.json   # closed-loop reporting/control decision
```

Generated experiment outputs are ignored by git.

## Final Selector and Reporting

Non-closed-loop best-candidate selection is disabled by default. Enable it with a top-level `selection` block and an explicit `selection.baseline_run_dir`. The runner does not guess the latest baseline automatically.

After configured non-closed-loop iterations finish, selection collects candidate run directories that produced `verification.json` and writes:

```text
results/experiments/<experiment_id>/best_candidate_selection.json
```

`best_candidate_selection.json` is an experiment-level artifact. It belongs under
`results/experiments/<experiment_id>/` when written, not under individual
`results/runs/<candidate_run_id>/` candidate run directories.

Selection can report:

- `best_candidate_found`
- `no_improvement_found`
- `all_candidates_rejected`
- `no_candidates`

Closed-loop `closed_loop_selection_report.json` is a reporting-only final analysis artifact. It separates the control decision already made during iteration execution from final analysis fields such as final speedup and status counts. It does not promote candidates, rewrite `current_best_source`, rewrite `final_optimized_source`, or modify the main `cpp/` tree.

## Optimization Scope

The main optimization pipeline enforces a strict optimization scope. LLM candidates may modify only the algorithm implementation files explicitly listed in `optimization_scope.allowed_files` in the experiment config.

Fixed evaluation infrastructure cannot be changed by optimization candidates:

- benchmark code (`cpp/bench/`)
- adapter code (`cpp/bench/families/.../adapters/`)
- validator code
- CMake files (`cpp/CMakeLists.txt` and subdirectory CMakeLists)
- Python orchestrator (`orchestrator/`)
- configs (`configs/`)
- documentation (`docs/`)
- tests (`cpp/tests/`)
- result storage code (`results/`)
- comparator, audit, and parser code

If `optimization_scope` is missing, backward compatibility is preserved by defaulting `allowed_files` to `[target_file]`.

Validation rules for `allowed_files`:

- Must be a non-empty list of non-empty strings.
- Paths must be relative repository paths using POSIX forward slashes.
- No absolute paths, `..` components, Windows drive prefixes, or null bytes.
- `target_file` must be included in `allowed_files` or validation fails with a clear error.

During the main experiment pipeline, the materializer enforces:

1. candidate `target_files` subset of external `allowed_files`
2. patched files from diff or `edits[].file` subset of candidate `target_files`
3. patched files from diff or `edits[].file` subset of external `allowed_files`

When `materialize_candidate` is run manually without `--allowed-file`, it falls back to legacy behavior where `candidate.json["target_files"]` acts as its own allowlist. This is preserved for backward compatibility with manual CLI usage; the main experiment pipeline always supplies the configured scope.

## LLM Overrides and Mock Client

Variants can use a base LLM config plus `llm_overrides` for supported fields:

- `provider`
- `model`
- `base_url`
- `api_key_env`
- `thinking`
- `max_tokens`

The runner writes resolved per-variant LLM config snapshots under:

```text
results/experiments/<experiment_id>/variant_configs/
```

Candidate generation uses these resolved snapshots, not the mutable base config files.

`provider: "mock"` uses predefined candidate JSON files under `configs/mock_candidates/`. The mock client does not read API keys, does not use the network, and returns the configured candidate through the same response/parsing/storage path as other candidate generation.

## Build Type

All benchmark evaluation builds, including baseline and candidate verification, default to **Release**. Debug builds are not suitable for runtime comparisons.

The build type flows through to:

- CMake configure (`-DCMAKE_BUILD_TYPE=<value>`)
- CMake build (`--config <value>`)
- artifacts (`metadata.json`, `verification.json`)

The benchmark artifact audit enforces matching build types before allowing comparison.

## Safety Invariants

- The main `cpp/` source tree is never modified automatically.
- Candidate materialization applies changes only inside isolated candidate workspaces.
- Closed-loop `current_best_source` is updated only after `decision_vs_current_best.json` reports `accepted_improvement`.
- `decision_vs_original_baseline.json` is reporting/control only and does not promote candidates.
- Final selector/reporting artifacts never promote candidates or rewrite source trees.
- All planned closed-loop iterations are attempted; there is no early stopping.

## Limitations

- Closed-loop mode currently supports exactly one variant.
- Automatic promotion of candidates into the main `cpp/` source tree is not implemented.
- Multi-variant closed-loop strategies are not implemented.
- Additional solver families/adapters beyond the current minimal Lambda Twist P3P path are future work.
- Advanced plots and broader statistical dashboards or aggregate analyses are future work.
