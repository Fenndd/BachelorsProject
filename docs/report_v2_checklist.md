# Current Report Manual Verification Checklist

Use this checklist after a real closed-loop experiment has completed and report generation has run. It is for manual inspection only; it does not replace deterministic tests or rerun optimization stages.

The report is a single unified current report, not separate v1/v2 modes. The historical template filename is an implementation detail.

## Expected Experiment Artifacts

- `results/experiments/<experiment_id>/closed_loop_summary.json` exists.
- `results/experiments/<experiment_id>/closed_loop_iterations.jsonl` exists.
- `results/experiments/<experiment_id>/closed_loop_selection_report.json` exists.
- `results/experiments/<experiment_id>/experiment_metadata.json` exists for new runs.
- `results/experiments/<experiment_id>/final_optimized_source/` exists.
- `results/experiments/<experiment_id>/final_optimized_source.diff` exists.
- `results/experiments/<experiment_id>/final_diff_stats.json` exists for new runs.
- `results/experiments/<experiment_id>/val/final_validation_report.json` exists for new closed-loop runs unless final validation failed before artifact creation.

## Expected Report Directory Structure

```text
results/experiments/<experiment_id>/report/
├── report_data.json
├── report.html
├── report.pdf          # only when PDF output was requested
└── plots/
    ├── runtime_progress.svg
    ├── candidate_runtime_by_iteration.svg
    ├── runtime_reduction_by_iteration.svg
    ├── correctness_metrics.svg
    ├── status_breakdown.svg
    ├── candidate_funnel.svg
    ├── phase_timings.svg
    ├── llm_tokens_by_iteration.svg
    ├── llm_latency_by_iteration.svg
    ├── failure_reason_breakdown.svg
    ├── diff_stats_by_iteration.svg
    └── final_validation_runtime_distribution.svg
```

`report.pdf` is optional when only HTML output was requested. Some SVGs may contain placeholder text if their corresponding metadata is unavailable.

## `report_data.json` Checks

- JSON parses successfully.
- `schema_version` is present and is `report.v2` for current generated reports.
- `experiment`, `baseline_metrics`, `final_result`, `iterations`, `status_counts`, and `artifacts` are present.
- Current reports include per-iteration `phase_timings`, `llm_usage`, `diff_stats`, and `outcome_reason` where applicable.
- Current reports include top-level `reason_code_counts`.
- Current reports include top-level `final_validation` when the final validation artifact is available.
- Final report headline final metrics use repeated validation median metrics when available.
- Executive Summary headline baseline and final runtimes use the same repeated-validation basis when final validation is available.
- No API keys, full environment dumps, full logs, or full diffs are embedded.

## Plot Checks

- All expected SVG files are present under `report/plots/`.
- Runtime plots show baseline/current-best/candidate progression where data exists.
- `phase_timings.svg` shows stacked per-iteration phase durations or placeholder text.
- LLM token and latency plots show per-iteration values or placeholder text.
- `failure_reason_breakdown.svg` shows outcome reason-code counts or placeholder text.
- `diff_stats_by_iteration.svg` shows changed lines per iteration or placeholder text.
- `final_validation_runtime_distribution.svg` shows successful correctness-passing baseline/final repeated validation runtimes or placeholder text.

## HTML Report Checks

- `report.html` opens in a browser without visible template errors.
- Core sections are present: cover, executive summary, experiment configuration, benchmark configuration, final repeated benchmark validation, baseline metrics, runtime progress, correctness, status breakdown, candidate funnel, per-iteration table, final best candidate summary, reporting status, and artifact map.
- Enriched sections are present: Outcome and Failure Analysis, Phase Timings, LLM Usage, Diff Statistics, Closed-Loop Selection, Reproducibility and Environment, and Iteration Appendix.
- The user-facing report focuses on closed-loop mode. Legacy `selection_enabled` and `history_policy` fields are not shown as main report concepts.
- Closed-loop promotion policy is `decision_vs_current_best.accepted_improvement_only`.
- Final repeated benchmark validation runs automatically after closed-loop completion and before report generation. It compares original baseline source vs final optimized source, defaults to 5 repetitions, does not affect candidate promotion, and does not change `current_best_source`.
- Executive Summary headline speedup, runtime reduction, baseline runtime, final runtime, and correctness preserved come only from `val/final_validation_report.json`. If final validation is incomplete, skipped, missing, or has null comparison metrics, those headline fields show `Not available`.
- If PDF was requested, `report.pdf` was exported from final completed `report.html`, not from pending-status HTML.
- Tables show `Not available` for missing optional values instead of crashing or showing raw template placeholders.

## PDF Report Checks

- If PDF was requested, `report.pdf` exists and opens.
- The HTML/PDF reporting status is completed in both artifacts; PDF should not show pending reporting status.
- PDF content matches the HTML sections at a high level.
- Wide tables remain readable enough for A4-style review.
- If PDF was not requested, missing `report.pdf` is acceptable.

## Outcome and Failure Analysis Checks

- `reason_code_counts` in `report_data.json` matches the Outcome and Failure Analysis table.
- Categories and reason codes are compact structured values, not raw stack traces.
- Successful, neutral, rejected, and failed iteration reasons can all appear.
- Iteration lists point to the relevant iterations.
- Placeholder text appears if structured reason data is absent.

## Phase Timings Checks

- Per-iteration timing rows match `iterations[*].phase_timings`.
- `generation_seconds`, `materialization_seconds`, `verification_seconds`, and total values are shown when available.
- Verification time includes benchmark execution; `benchmark_seconds` is not separately shown in the main report.

## LLM Usage Checks

- Token counts, model, finish reason, and API latency match `iterations[*].llm_usage`.
- Mock or provider responses without usage metadata display unavailable values.
- No prompts, secrets, raw provider responses, or API keys are exposed in the report.
- Aggregate LLM token and latency totals are shown when usage metadata exists.
- Most Expensive Iteration and Highest Latency Iteration cards are shown when usage metadata exists.

## Final Validation Checks

- The Final Repeated Benchmark Validation section shows enabled/skipped status and benchmark repetitions.
- Final validation artifacts are under `val/`; `b` is the baseline group and `f` is the final group.
- Final validation uses a minimal shortened `cpp/` build tree, not a full copy of the repository `cpp/` tree; the original repository layout remains unchanged.
- `final_validation_report.json` includes `source_layout` metadata describing how the shortened tree maps to the original `cpp/` layout.
- Status is one of `skipped`, `completed`, `completed_partial`, or `incomplete`.
- If `final_validation.benchmark_repetitions` was missing in the config, the report shows default 5 repetitions.
- Successful baseline/final run counts match `final_validation_report.json`.
- Baseline/final benchmark runs attempted match `final_validation_report.json`.
- Baseline and final median/mean/std/min/max runtime values match `final_validation_report.json`.
- Median speedup and median runtime reduction percent match `final_validation_report.json`.
- Baseline and final all-correctness-passed values are shown only when at least one relevant successful validation run exists; otherwise they show `Not available`.
- Setup failures are represented in each group's `setup` block, with `runs: []` and `benchmark_runs_attempted: 0`, not as fake failed benchmark repetitions.
- Run records use benchmark-only repeated validation (`validation_mode: benchmark_only`, `benchmark_run_status`) after one configure/build per source, not the full per-candidate verifier, and do not include `verification_status`.
- Aggregates and plots include only successful correctness-passing repetitions; plots filter on `benchmark_run_status`, not per-iteration verification status.
- If final validation is `completed_partial` with comparison metrics, the report still shows normal metric cards/tables and also shows a warning diagnostics panel with dominant failure, suggested logs, setup failure flags, group status fields, and attempted benchmark runs.
- If final validation is incomplete, the report shows compact diagnostics with setup statuses, group statuses, setup failure flags, dominant failure, path-length warning state, max observed path length, and suggested logs instead of a mostly empty full metrics table.
- If final validation is skipped, the report clearly states that it was disabled/skipped and does not show the full empty metrics table.
- If final validation is missing, the report clearly states that final repeated benchmark validation was not available.

## Reproducibility Checks

- Git commit, branch, dirty worktree, OS, platform, Python version, CMake executable, generator, C++ compiler, and CMake build type are visible when recorded.
- Build type is reproducibility metadata; `Release` is the default benchmark build type.

## Diff Statistics Checks

- Final diff summary cards match `final_best_candidate.diff_stats` when available.
- Per-iteration rows match `iterations[*].diff_stats`.
- Changed lines equal lines added plus lines removed in the plot.
- Fallback usage is shown as Yes, No, or Not available.

## Iteration Appendix Checks

- Each iteration has a compact appendix entry.
- Entries include status, candidate summary, expected effect, risk level, outcome reason, runtime, speedups, correctness, promotion flag, timings, LLM usage, diff stats, and candidate run directory.
- Full JSON dumps, full logs, and full diffs are not included.

## Graceful Degradation Checks

- Older or incomplete `report_data.json` can still render where possible.
- Missing `phase_timings`, `llm_usage`, `diff_stats`, `outcome_reason`, and `reason_code_counts` produce unavailable markers or placeholder plots.
- HTML-only reports are accepted when PDF was not requested.

## Final Consistency Checks

- Final best iteration matches `closed_loop_summary.json` and `closed_loop_selection_report.json`.
- Accepted improvement counts match status counts.
- Final runtime/speedup values match the final best candidate metrics.
- When final validation metrics are available, final runtime/speedup values match repeated validation median metrics, not single-run selection metrics.
- Report artifact paths point inside the completed experiment directory.
- `experiment_metadata.finished_at` and `experiment_status.finished_at` represent the full experiment cycle, including final validation and reporting.
- Reporting remains read-only: no source files, candidate workspaces, verification artifacts, benchmark results, or promotion state are modified by report inspection or viewing.
