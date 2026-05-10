# Experiment Runner

The experiment runner is the Step 10 orchestration layer for moving from one
LLM optimization attempt to reproducible multi-attempt experiments.

It is the main entry point for LLM optimization experiments. The separate
`orchestrator/cli/main.py` entry point remains dedicated to clean baseline
configure/build/run/benchmark automation.

## Configs

Experiment configs live under `configs/experiments/`. A config defines:

- `target_file`: the source file sent to candidate generation.
- `pipeline`: which non-benchmark stages are enabled.
- `candidate_generation`: generation limits such as `max_source_chars`.
- `candidate_format`: selects candidate edit format and source presentation.
- `history_policy`: optional variant-local prompt history.
- `selection`: optional baseline-vs-candidates best result selection.
- `closed_loop`: optional iterative current-best optimization mode.
- `variants`: one or more model/config/context/parameter setups.

Single-setup legacy configs remain supported by creating one synthetic
`default` variant.

`configs/experiments/mock_p3p_basic.json` uses the offline mock LLM config and
is intended for reproducible storage/orchestration checks without an API key.

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

## Candidate Formats

The experiment runner passes `candidate_format.type` and `candidate_format.source_presentation` to `generate_candidate`.

- `unified_diff`: legacy/fallback format using plain source, `candidate.diff`, and `git apply` materialization.
- `line_range_edits`: preferred robust format using `line_numbered` source, `candidate.edits.json`, deterministic line-range materialization, and system-generated `candidate.generated.diff`.

See `docs/candidate_edit_formats.md` for the dedicated format reference.

## Variants And Iterations

Each variant has its own:

- `variant_id`
- base `llm_config`
- optional `llm_overrides`
- iteration count
- additional prompt context

The runner executes all iterations for each variant and records both global and
variant-local iteration numbers.

## Pipeline Stages

Enabled stages run in this order:

1. `generate_candidate`
2. `materialize_candidate`
3. `verify_candidate`

If a stage fails, later stages for that iteration are skipped. The experiment
continues with later iterations and variants.

Materialization and verification operate only on isolated candidate workspaces;
the main `cpp/` source tree is not modified.

For configured experiments, `optimization_scope.allowed_files` is passed to
`generate_candidate` as repeated `--allowed-file` arguments and to
`materialize_candidate` as the external allowlist. For `unified_diff`, candidate
`target_files` and diff header paths are checked against `allowed_files`. For
`line_range_edits`, candidate `target_files` and `edits[].file` are checked
against `allowed_files`. Manual materialization without `--allowed-file` remains
supported for legacy usage, but the main experiment pipeline always enforces the
configured scope.

The active Step 9 materialization command is
`orchestrator.patching.materialize_candidate`. The older
`orchestrator/patching/apply_patch.py` module is only a compatibility marker for
a future broader patching API.

For `unified_diff`, materialization checks candidate patches with normal
`git apply --check`. If that check fails because an LLM-generated unified diff
has malformed hunk line counts, the materializer tries Git's
`git apply --check --recount` fallback and applies with `git apply --recount`
only if the recount check succeeds.

For `line_range_edits`, materialization does not require `candidate.diff`. It
verifies line ranges, applies deterministic edits, and writes
`candidate.generated.diff`. Deterministic C++ verification and benchmark
correctness checks still decide whether a materialized candidate is valid.

### Materialization Base Source Root

Candidate materialization separates the logical repo-relative candidate paths
from the physical source tree copied into the isolated workspace. By default,
old behavior is preserved: `materialize_candidate` copies the legacy
`--source-root` value, which defaults to `cpp`, into the candidate workspace so
paths such as `cpp/external/lambdatwist/p3p.cc` still resolve under
`workspace/candidates/<candidate_run_id>/cpp/...`.

For closed-loop preparation, materialization also accepts an explicit
repo-like base source root:

```powershell
py -m orchestrator.patching.materialize_candidate `
  --candidate-run results/runs/<candidate_run_id> `
  --base-source-root workspace/experiments/<experiment_id>/current_best_source `
  --overwrite `
  --allowed-file cpp/external/lambdatwist/p3p.cc
```

In this mode, `--base-source-root` must contain repo-relative paths directly,
for example
`workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc`.
The materializer copies that tree into the isolated candidate workspace and
applies the candidate there. It never modifies `--base-source-root` directly and
never modifies the main `cpp/` source tree automatically.

`--source-root` remains supported for backward compatibility. To avoid ambiguous
copy semantics, an explicit `--source-root` cannot be combined with
`--base-source-root`. The experiment runner's normal non-closed-loop flow does
not pass `--base-source-root`, so existing experiment behavior is unchanged.

`verify_candidate` is deterministic and does not call any LLM API. It now runs
the same benchmark-family verification path used by the baseline preparation:
configure CMake in the isolated workspace, build and run `baseline_smoke_test`,
build and run the Lambda Twist P3P adapter validator, build and run
`absolute_pose_lambdatwist_benchmark`, and parse the family benchmark stdout
into `verification.json`. If parsing succeeds but `correctness_passed=false`,
verification fails at `benchmark_correctness_check` while preserving parsed
metrics.

Candidate verification builds default to **Release** for accurate runtime
metrics. Set `CMAKE_BUILD_TYPE=Debug` in the environment to override. The build
type is recorded in `verification.json`.

Benchmark artifacts can be audited manually or as part of pairwise candidate decision and selection:

```powershell
py -m orchestrator.benchmarking.audit_benchmark_pair `
  --baseline-run results/runs/<baseline_run_id> `
  --candidate-run results/runs/<candidate_run_id>
```

The audit writes `benchmark_artifact_audit.json` into the candidate run
directory and checks whether the baseline and candidate metrics are safe to
compare. Pairwise candidate decisions and multi-candidate best-result selection
are implemented separately and still do not promote code.

The pairwise decision helper also supports explicit reference-vs-candidate
comparison for closed-loop preparation:

```powershell
py -m orchestrator.benchmarking.candidate_decision `
  --reference-run results/runs/<reference_run_id> `
  --reference-kind verified_candidate `
  --candidate-run results/runs/<candidate_run_id> `
  --output-filename decision_vs_current_best.json
```

Use `--reference-kind baseline` when the reference run stores benchmark metrics
in `metrics.json`; use `--reference-kind verified_candidate` when the reference
is a previously verified candidate storing benchmark metrics in
`verification.json`. The old `--baseline-run ... --candidate-run ...` command
remains supported and still writes `candidate_decision.json` by default.

## Best Candidate Selection

Selection is disabled by default. Enable it with a top-level `selection` block:

```json
{
  "selection": {
    "enabled": true,
    "baseline_run_dir": "results/runs/<baseline_run_id>",
    "write_candidate_decisions": true
  }
}
```

When `selection.enabled=true`, `selection.baseline_run_dir` is required. The
runner does not guess the latest baseline automatically.

After all configured iterations finish, the runner collects candidate run
directories that produced `verification.json`, including verified candidates
that later become rejected by the pairwise decision logic. It then writes:

```text
results/experiments/<experiment_id>/best_candidate_selection.json
```

The compact selection summary is also included in `experiment_status.json` and
`summary.txt`. Selection can report:

- `best_candidate_found`
- `no_improvement_found`
- `all_candidates_rejected`
- `no_candidates`

Selection does not promote, merge, copy, or commit candidates into the main
source tree.

## Variant-Local History

When `history_policy.enabled` is true, later iterations receive a compact
summary of previous attempts from the same variant only. History is not shared
between variants. The context excludes full diffs, full LLM responses, and
reasoning content.

History context files are saved under:

```text
results/experiments/<experiment_id>/logs/
```

Per-variant history artifacts are saved under:

```text
results/experiments/<experiment_id>/variants/<variant_id>/
```

## LLM Overrides

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

Candidate generation uses these resolved snapshots, not the mutable base config
files.

## Offline Mock LLM

`configs/llm_mock_candidate.json` selects `provider: "mock"` and points to a
predefined candidate JSON file under `configs/mock_candidates/`. The mock client
does not read API keys, does not use the network, and returns the configured
candidate through the same response/parsing/storage path as real LLM candidate
generation.

Direct mock candidate generation:

```powershell
py -m orchestrator.llm.generate_candidate `
  --config configs/llm_mock_candidate.json `
  --source cpp/external/lambdatwist/p3p.cc
```

### Generation Source Root

Candidate generation separates the logical target file from the physical source
root used for reading source code. By default, `--source-root` is the repository
root, so existing commands continue to read `cpp/external/lambdatwist/p3p.cc`
from the clean repo source tree.

For closed-loop preparation, `generate_candidate` can instead read from an
experiment-local current-best source tree:

```powershell
py -m orchestrator.llm.generate_candidate `
  --config configs/llm_mock_line_range_p3p.json `
  --source cpp/external/lambdatwist/p3p.cc `
  --source-root workspace/experiments/<experiment_id>/current_best_source `
  --candidate-type line_range_edits `
  --source-presentation line_numbered
```

This reads the physical file
`workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc`,
but the LLM prompt, candidate `target_files`, `allowed_files`, and candidate
metadata still use the stable repo-relative logical path
`cpp/external/lambdatwist/p3p.cc`. The temporary workspace path is recorded in
artifacts for traceability but is not presented as the optimization target file.
The main `cpp/` source tree remains the clean baseline and is not modified
automatically.

## Artifacts

A real experiment writes:

```text
results/experiments/<experiment_id>/
|- experiment_config_snapshot.json
|- experiment_status.json
|- iterations.jsonl
|- summary.txt
|- best_candidate_selection.json   # only when selection.enabled=true
|- logs/
|- variants/
|  `- <variant_id>/
|     |- variant_history.jsonl
|     `- variant_summary.txt
`- variant_configs/
   `- <variant_id>_llm_config.json
```

Generated experiment outputs are ignored by git.

## Closed-loop Optimization Mode (Stage 7)

Closed-loop optimization is being introduced in stages. Stage 1 defines the
state and artifact schema. Stage 5 added the first real closed-loop
orchestration flow while still keeping the main `cpp/` source tree clean. Stage
6 adds compact benchmark-aware LLM history for closed-loop generation. Stage 7
adds final result artifacts after all planned iterations finish.

Enable it with:

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

Closed-loop constraints:

- exactly one variant is supported; multiple variants fail with a clear error
- `selection.baseline_run_dir` is required as the original baseline reference,
  even when `selection.enabled=false`
- all planned iterations are attempted; there is no early stopping
- final artifacts summarize the single current-best chain; multi-variant
  closed-loop strategies are intentionally left for later stages

The mutable experiment-local current best source is stored outside `cpp/` under:

```text
workspace/experiments/<experiment_id>/current_best_source/
workspace/experiments/<experiment_id>/current_best_state.json
```

Final closed-loop outputs are stored under the experiment result directory:

```text
results/experiments/<experiment_id>/final_optimized_source/
results/experiments/<experiment_id>/final_optimized_source.diff
results/experiments/<experiment_id>/closed_loop_iterations.jsonl
results/experiments/<experiment_id>/closed_loop_summary.json
results/experiments/<experiment_id>/current_best_state.json
```

`closed_loop_iterations.jsonl` stores one compact JSON object per closed-loop
iteration and is append-only during the run. The workspace
`current_best_state.json` is updated after every iteration. At finalization, the
runner also copies the final current-best metadata to the results directory as
`current_best_state.json`.

`final_optimized_source/` is a copy of the final
`workspace/experiments/<experiment_id>/current_best_source/` tree. If no
candidate was accepted, it is still written and is baseline-equivalent.

`final_optimized_source.diff` is a unified diff from the original clean baseline
source in `REPO_ROOT/<target_file>` to the final optimized source. It currently
covers at least `target_file`. If the final source is unchanged, the diff file is
written but empty.

`closed_loop_summary.json` records the experiment id, target file, total and
completed iterations, original baseline paths, final best iteration, final best
candidate run directory when applicable, final optimized source paths, final
speedup/runtime reduction versus the original baseline when available, iterations
after the final best, all closed-loop status counts including zero values, and
timestamps.

`experiment_status.json` includes a `closed_loop` block with final artifact paths,
accepted improvement count, final best iteration, final speedup/runtime
reduction, and status counts. The human-readable `summary.txt` includes a concise
closed-loop section with the same final artifact locations.

At experiment start, the runner initializes
`workspace/experiments/<experiment_id>/current_best_source/` by copying the clean
repository `cpp/` tree into a repo-like layout, for example:

```text
workspace/experiments/<experiment_id>/current_best_source/cpp/external/lambdatwist/p3p.cc
```

Each iteration then runs:

1. build compact closed-loop history from all previous meaningful iterations
2. `generate_candidate` with `--source-root workspace/experiments/<experiment_id>/current_best_source`
   and, when context exists, `--context <additional context plus closed-loop history>`
3. `materialize_candidate` with `--base-source-root workspace/experiments/<experiment_id>/current_best_source`
4. `verify_candidate`
5. pairwise comparison against the current best
6. pairwise comparison against the original baseline

Only `decision_vs_current_best.json` controls promotion. If its status is
`accepted_improvement`, the materialized workspace from `materialization.json`
`workspace_path` replaces `current_best_source`, and `current_best_state.json` is
updated to point at the accepted candidate. `decision_vs_original_baseline.json`
is written for reporting/control but does not control promotion.

No-op candidates (`expected_effect="none"` with empty `edits` for
`line_range_edits`, or empty `unified_diff` for `unified_diff`) are recorded as
`no_op` and do not run materialization or verification.

### Compact Closed-loop LLM History

In closed-loop mode, the runner uses a dedicated compact history builder instead
of the non-closed-loop variant-local `history_policy` sliding window. Before each
generation stage, it summarizes **all meaningful previous closed-loop
iterations** and combines that summary with the variant's `additional_context`.
The combined text is passed to `generate_candidate` through `--context`.

The history tells the LLM that it is improving the current best source, not the
original baseline. It can include:

- `accepted_improvement`: accepted changes already included in
  `current_best_source`
- `valid_not_improved`: correct candidates that were not faster than the current
  best
- `rejected`: candidates that failed correctness or selection gates
- `materialization_failed`: candidates with usable candidate information whose
  edits could not be applied
- `verification_failed`: candidates with usable candidate information that broke
  build, tests, benchmark execution, API compatibility, or metric generation

The history excludes no-op iterations and generation failures without usable
candidate information. Generation failures with candidate summaries are also not
included by the current deterministic policy because they are not reliable
optimization patterns.

History entries are plain compact text. They include candidate summaries,
speedups/runtime information when available, short failure or rejection reasons,
and deterministic guidance such as "this improvement is already included" or
"do not repeat this optimization pattern." They intentionally do **not** include
full source code, full diffs, full `candidate.json`, full `verification.json`,
benchmark logs, audit objects, stack traces, or no-op entries.

The exact closed-loop history context used for each iteration is logged under:

```text
results/experiments/<experiment_id>/logs/iteration_003_closed_loop_history_context.txt
```

If no meaningful history exists yet, the log contains:

```text
No meaningful closed-loop history yet.
```

Each `closed_loop_iterations.jsonl` record also includes:

- `history_included`: whether this iteration will be included in future
  closed-loop history
- `history_guidance`: the deterministic guidance string for included records, or
  `null` for excluded records

The main `cpp/` source tree remains the clean baseline and is never modified
automatically by closed-loop experiments.

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
|- candidate_decision.json    # when selection writes pairwise decisions
|- decision_vs_current_best.json       # closed-loop promotion decision
|- decision_vs_original_baseline.json  # closed-loop reporting/control decision
```

Only `decision_vs_current_best.json` controls whether a verified candidate
becomes the new current best; `decision_vs_original_baseline.json` is for
reporting/control.

Stage 3 prepares candidate generation for that future runner by allowing it to
read from `current_best_source` via `--source-root` while preserving the logical
repo-relative target path seen by the LLM. It still does not implement candidate
promotion, current-best updates, or full closed-loop orchestration.

Stage 4 prepares materialization for the same future runner by allowing
`materialize_candidate` to copy and apply candidates relative to an explicit
`--base-source-root`. In future closed-loop iterations, generation will read
from `current_best_source` and materialization will receive the same directory as
`--base-source-root`, so `line_range_edits` line numbers and original text refer
to the same source version the LLM saw. The per-candidate
`candidate.generated.diff` is therefore an iteration-local diff from
`base_source_root` to the materialized candidate workspace. The final
`final_optimized_source.diff` is a separate final reporting artifact generated
against the original clean baseline.

Stage 5 implements candidate promotion into the experiment-local
`current_best_source` and current-best state updates. Stage 6 implements compact
benchmark-aware closed-loop LLM history. Stage 7 implements final optimized
source storage, final diff export, results-side current-best metadata, and final
closed-loop summary/status reporting.

## Optimization Scope (Strict File Access Control)

The main optimization pipeline enforces a strict optimization scope. LLM
candidates may modify **only** the algorithm implementation files explicitly
listed in `optimization_scope.allowed_files` in the experiment config.

### What Cannot Be Modified

The following are fixed evaluation infrastructure and **cannot** be changed by
optimization candidates:

- **Benchmark code** (`cpp/bench/`)
- **Adapter code** (`cpp/bench/families/.../adapters/`)
- **Validator code**
- **CMake files** (`cpp/CMakeLists.txt` and subdirectory CMakeLists)
- **Python orchestrator** (`orchestrator/`)
- **Configs** (`configs/`)
- **Documentation** (`docs/`)
- **Tests** (`cpp/tests/`)
- **Result storage code** (`results/`)
- **Comparator, audit, and parser code**

### Config Shape

```json
{
  "optimization_scope": {
    "allowed_files": [
      "cpp/external/lambdatwist/p3p.cc"
    ]
  }
}
```

If `optimization_scope` is missing, backward compatibility is preserved by
defaulting `allowed_files` to `[target_file]`. Existing configs continue to
work without changes.

### Validation Rules for allowed_files

- Must be a non-empty list of non-empty strings
- Paths must be relative repository paths (POSIX forward-slash style)
- No absolute paths, `..` components, Windows drive prefixes, or null bytes
- `target_file` must be included in `allowed_files` or validation fails with a
  clear error

### Enforcement (Three-Layer Check)

During the main experiment pipeline, the materializer enforces:

1. **candidate target_files ⊆ external allowed_files**
2. **patched files from diff or edits[].file ⊆ candidate target_files**
3. **patched files from diff or edits[].file ⊆ external allowed_files**

If any check fails, the materializer exits with a clear error message such as:

```
candidate target_files outside allowed optimization scope: cpp/bench/...
```

or:

```
candidate.diff modifies files outside allowed optimization scope: cpp/CMakeLists.txt
```

For `line_range_edits`, equivalent scope failures refer to `edits[].file`.

### Fallback for Manual Usage

When `materialize_candidate` is run manually without `--allowed-file`, it falls
back to legacy behavior where `candidate.json["target_files"]` acts as its own
allowlist. This is **not secure** for the main optimization pipeline and is
only preserved for backward compatibility with manual CLI usage.

### Future Adapter-Generation Pipeline

A separate adapter-preparation pipeline where the LLM helps create adapters is
a possible future addition. It is **not** part of the current main optimization
pipeline and would use a different scope configuration.

### CLI Arguments

`generate_candidate` accepts:

```
--allowed-file <path>    (may be repeated)
```

If no `--allowed-file` is provided, it defaults to `[source]`.

`materialize_candidate` accepts:

```
--allowed-file <path>    (may be repeated)
```

If no `--allowed-file` is provided, the materializer falls back to
`candidate.json["target_files"]` for legacy compatibility.

## Build Type

All benchmark evaluation builds (baseline and candidate verification) default
to **Release**. Debug builds are not suitable for runtime comparisons.

To override the build type for an experiment:

```powershell
$env:CMAKE_BUILD_TYPE="Debug"
py -m orchestrator.experiments.run_experiment --config configs/experiments/my_config.json
```

The build type flows through to:
- CMake configure (`-DCMAKE_BUILD_TYPE=<value>`)
- CMake build (`--config <value>`)
- Artifacts (`metadata.json`, `verification.json`)

The benchmark artifact audit enforces matching build types before allowing
comparison.

## Not Implemented Yet

The experiment runner still does not implement:

- promotion of candidates into the main source tree
- multi-variant closed-loop strategies
