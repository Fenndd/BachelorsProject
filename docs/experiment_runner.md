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
- `history_policy`: optional variant-local prompt history.
- `selection`: optional baseline-vs-candidates best result selection.
- `variants`: one or more model/config/context/parameter setups.

Single-setup legacy configs remain supported by creating one synthetic
`default` variant.

`configs/experiments/mock_p3p_basic.json` uses the offline mock LLM config and
is intended for reproducible storage/orchestration checks without an API key.

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
`materialize_candidate` as the external allowlist. The materializer enforces that
candidate `target_files` and diff header paths remain inside this external
allowlist. Manual materialization without `--allowed-file` remains supported for
legacy usage, but the main experiment pipeline always enforces the configured
scope.

The active Step 9 materialization command is
`orchestrator.patching.materialize_candidate`. The older
`orchestrator/patching/apply_patch.py` module is only a compatibility marker for
a future broader patching API.

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

Benchmark artifacts can be audited manually before future comparison work:

```powershell
py -m orchestrator.benchmarking.audit_benchmark_pair `
  --baseline-run results/runs/<baseline_run_id> `
  --candidate-run results/runs/<candidate_run_id>
```

The audit writes `benchmark_artifact_audit.json` into the candidate run
directory and checks whether the baseline and candidate metrics are safe to
compare. Pairwise candidate decisions and multi-candidate best-result selection
are implemented separately and still do not promote code.

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

## Artifacts

A real experiment writes:

```text
results/experiments/<experiment_id>/
|- experiment_config_snapshot.json
|- experiment_status.json
|- iterations.jsonl
|- summary.txt
|- logs/
|- variants/
|  `- <variant_id>/
|     |- variant_history.jsonl
|     `- variant_summary.txt
`- variant_configs/
   `- <variant_id>_llm_config.json
```

Generated experiment outputs are ignored by git.

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
2. **patched files from diff ⊆ candidate target_files**
3. **patched files from diff ⊆ external allowed_files**

If any check fails, the materializer exits with a clear error message such as:

```
candidate target_files outside allowed optimization scope: cpp/bench/...
```

or:

```
candidate.diff modifies files outside allowed optimization scope: cpp/CMakeLists.txt
```

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
- full closed-loop optimization with ranking
