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
- `results/experiments/<experiment_id>/final_selection_report.json` exists for new closed-loop runs.
- `results/experiments/<experiment_id>/final_selection/` exists when the final best is not baseline.

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
    └── diff_stats_by_iteration.svg
```

`report.pdf` is optional when only HTML output was requested. Some SVGs may contain placeholder text if their corresponding metadata is unavailable.

## `report_data.json` Checks

- JSON parses successfully.
- `schema_version` is present and is `report.v2` for current generated reports.
- `experiment`, `baseline_metrics`, `final_result`, `iterations`, `status_counts`, and `artifacts` are present.
- Current reports include per-iteration `phase_timings`, `llm_usage`, `diff_stats`, and `outcome_reason` where applicable.
- Current reports include top-level `reason_code_counts`.
- Current reports include top-level `final_selection` when the final selection artifact is available.
- Final report headline final metrics use the single-run comparison metrics when available.
- Executive Summary headline baseline and final runtimes use the single-run comparison basis when available.
- No API keys, full environment dumps, full logs, or full diffs are embedded.

## Plot Checks

- All expected SVG files are present under `report/plots/`.
- Runtime plots show baseline/current-best/candidate progression where data exists.
- `phase_timings.svg` shows stacked per-iteration phase durations or placeholder text.
- LLM token and latency plots show per-iteration values or placeholder text.
- `failure_reason_breakdown.svg` shows outcome reason-code counts or placeholder text.
- `diff_stats_by_iteration.svg` shows changed lines per iteration or placeholder text.

## HTML Report Checks

- `report.html` opens in a browser without visible template errors.
- Core sections are present: cover, executive summary, experiment configuration, benchmark configuration, final single-run comparison, baseline metrics, runtime progress, correctness, status breakdown, candidate funnel, per-iteration table, final best candidate summary, reporting status, and artifact map.
- Enriched sections are present: Outcome and Failure Analysis, Phase Timings, LLM Usage, Diff Statistics, Closed-Loop Selection, Reproducibility and Environment, and Iteration Appendix.
- The user-facing report focuses on closed-loop optimization.
- Closed-loop promotion policy is `decision_vs_current_best.accepted_improvement_only`.
- After closed-loop completion and before report generation, the runner performs a single benchmark run on the final optimized source and compares it against the original baseline. The comparison does not affect candidate promotion and does not change `current_best_source`.
- Executive Summary headline speedup, runtime reduction, baseline runtime, final runtime, and correctness preserved come from `final_selection_report.json`. If the single-run comparison failed, was skipped (baseline is best), or metrics are unavailable, those headline fields show `Not available`.
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

## Final Single-Run Comparison Checks

- The Final Single-Run Comparison section shows the comparison status and whether the final best is baseline.
- The artifact map lists both the raw `experiment_config_snapshot.json` and effective `experiment_config_effective.json` when present.
- `final_selection_report.json` exists at the experiment root.
- Status is one of `skipped`, `completed`, or `failed`.
- Speedup and runtime reduction percent match `final_selection_report.json`.
- Baseline and final per-problem median runtimes match `final_selection_report.json`.
- If the final best is baseline, the report shows `skipped` with speedup 1.0 and no rebuild.
- If the single-run comparison failed, the report shows the `failed_step` and `error_message` from `final_selection_report.json`.
- If the single-run comparison is missing, the report clearly states that the final comparison was not available.

## Reproducibility Checks

- Git commit, branch, dirty worktree, OS, platform, Python version, CMake executable, generator, C++ compiler, and CMake build type are visible when recorded.
- Build type is reproducibility metadata; `Release` is the default benchmark build type.

## Diff Statistics Checks

- Final diff summary cards match final-best diff statistics when available.
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
- When single-run comparison metrics are available, final runtime/speedup values match those comparison metrics.
- Report artifact paths point inside the completed experiment directory.
- `experiment_metadata.finished_at` and `experiment_status.finished_at` represent the full experiment cycle, including the single-run comparison and reporting.
- Reporting remains read-only: no source files, candidate workspaces, verification artifacts, benchmark results, or promotion state are modified by report inspection or viewing.
