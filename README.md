# Automated Optimization of C++ 3D Vision Algorithms Using LLMs

Bachelor thesis project for closed-loop automated optimization of C++ 3D vision minimal
solvers using LLM-generated candidates. The benchmark layer uses the PoseLib-native
backend with solver selection through JSON manifests and the solver registry. Candidate
edits are materialized and verified in isolated workspaces — the main source tree is never
modified automatically.

## Repository Structure

```text
.
|- cpp/            # C++ algorithm layer, tests, benchmark targets, external baselines
|- orchestrator/   # Python baseline, LLM, materialization, verification, selection, experiments
|- configs/        # LLM and experiment configs
|- workspace/      # Isolated candidate and experiment-local current-best workspaces
|- results/        # Persistent baseline, candidate, verification, decision, experiment artifacts
|- docs/           # Project documentation
`- scripts/        # Helper scripts only
```

## How It Works

The baseline CLI and the LLM experiment runner are separate entry points.
`orchestrator/cli/app.py` (Typer) is the control layer — it launches these entry points,
provides diagnostics, results browsing, and a terminal UI.

Closed-loop pipeline: **generate** (LLM) → **materialize** (isolated workspace) →
**verify** (100 repeated benchmarks) → **decide** (pairwise comparison) →
**promote** (into experiment-local current best). See `docs/architecture.md` for details.

## Quick Start

```powershell
copy .env.example .env.local                    # fill in paths and API keys

python -m orchestrator.cli.app doctor           # environment + project health check
python -m orchestrator.cli.app baseline run --solver poselib_p3p_lambdatwist

python -m orchestrator.cli.app experiment list
python -m orchestrator.cli.app experiment run --config configs/experiments/<file>.json --dry-run
python -m orchestrator.cli.app experiment run --config configs/experiments/<file>.json --yes

python -m orchestrator.cli.app results latest
python -m orchestrator.cli.app tui
```

Full command reference: `python -m orchestrator.cli.app --help`.
See `docs/setup.md` for required environment variables and toolchain requirements.

## LLM Candidate Edits

The LLM receives line-numbered source and returns a JSON candidate with `edits[]`.
Each edit contains only `start_line`, `end_line`, `original`, and `replace`. The target
file is set by the experiment config — edits do not carry a `file` field. No-op candidates
use `edits: []`. The materializer verifies each `original` block matches the source before
applying the replacement. See `docs/candidate_edit_formats.md` for the full schema.

## Selection and Reporting

Verified candidates are compared pairwise against the baseline and current best using
repeated-median benchmark metrics. Accepted candidates are promoted into the
experiment-local current best. A final HTML/PDF report is generated at experiment end.
See `docs/result_storage_format.md` for artifact paths and layout.

## External Baseline Code

`cpp/external/poselib/` contains imported third-party source code. Candidate changes are
materialized only in isolated workspace copies.

## Outputs

- `results/` — persistent run and experiment artifacts (metadata, metrics, decisions,
  reports). Grows across runs; not automatically cleaned.
- `workspace/` — isolated candidate and experiment workspaces. Regenerable and gitignored.
  Clean with `python -m orchestrator.cli.app workspace clean-all`.

## Documentation

- `docs/architecture.md` — pipeline components and module boundaries
- `docs/setup.md` — toolchain targets, environment variables
- `docs/algorithms.md` — solver registry, manifests, PoseLib-native benchmark
- `docs/candidate_edit_formats.md` — LLM edit schema
- `docs/result_storage_format.md` — artifact paths and storage layout
