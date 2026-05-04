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

The active Step 9 materialization command is
`orchestrator.patching.materialize_candidate`. The older
`orchestrator/patching/apply_patch.py` module is only a compatibility marker for
a future broader patching API.

`verify_candidate` is deterministic and does not call any LLM API. It now runs
the same benchmark-family verification path used by the baseline preparation:
configure CMake in the isolated workspace, build and run `baseline_smoke_test`,
build and run the Lambda Twist P3P adapter validator, build and run
`absolute_pose_lambdatwist_benchmark`, and parse the family benchmark stdout
into `verification.json`.

Benchmark artifacts can be audited manually before future comparison work:

```powershell
py -m orchestrator.benchmarking.audit_benchmark_pair `
  --baseline-run results/runs/<baseline_run_id> `
  --candidate-run results/runs/<candidate_run_id>
```

The audit writes `benchmark_artifact_audit.json` into the candidate run
directory and checks whether the baseline and candidate metrics are safe to
compare. It does not rank candidates, choose a winner, or promote code.

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

## Not Implemented Yet

The experiment runner still does not implement:

- candidate comparison
- best candidate selection
- promotion of candidates into the main source tree
- full closed-loop optimization with ranking
