# Algorithm / Solver Support

## `solver_id`

`solver_id` is the project-level identifier for a solver algorithm. It is
used consistently across:

- Experiment configs (`solver_id` field).
- Baseline runs (`--solver` flag on the CLI).
- The solver registry (`get_solver_descriptor(solver_id)`).
- Closed-loop experiment runner (verification stage dispatches by
  descriptor).

## Benchmark Backends

The project supports two benchmark backends:

| Backend | Model | Used by |
|---|---|---|
| `absolute_pose` | Generated C++ benchmark with adapter validation | `lambdatwist_p3p` |
| `poselib_native` | PoseLib's own benchmark infrastructure with `--solver` selection and machine-readable JSON output | All `poselib_*` solvers |

The backend controls which CMake targets are built, which parser reads the
benchmark stdout, and whether adapter validation runs before the benchmark.

## Solver Manifests

Each solver is declared in a per-solver JSON manifest:

```
cpp/bench/absolute_pose/solvers/lambdatwist_p3p.json
cpp/bench/poselib_native/solvers/poselib_p3p.json
cpp/bench/poselib_native/solvers/poselib_relpose_5pt.json
...
```

Manifests are discovered automatically at import time by the solver
registry. There are currently **38 manifests** (1 `absolute_pose` +
37 `poselib_native`).

### Key Manifest Fields

| Field | Description |
|---|---|
| `solver_id` | Unique project-level identifier. |
| `family` | `"absolute_pose"` or `"poselib_native"`. |
| `display_name` | Human-readable label for UIs. |
| `benchmark_backend` | Backend name (must match family for poselib_native). |
| `benchmark_target` | CMake target for the benchmark executable. |
| `benchmark_solver_key` | PoseLib solver name passed via `--solver`. |
| `benchmark_kind` | Category: `absolute_pose`, `relative_pose`, etc. |
| `default_target_file` | Repo-relative path to the solver's primary source file. |
| `default_allowed_files` | Repo-relative paths the LLM is allowed to modify. |
| `targets` | CMake target names (benchmark, adapter, validator). |

### `absolute_pose` Manifest Extras

For the generated `absolute_pose` backend (`runner_mode`:
`"generated_absolute_pose"`), manifests additionally contain:

- `adapter_dir`, `adapter_class`, `adapter_namespace`, `adapter_header`,
  `adapter_sources` — adapter wiring.
- `benchmark_options` — number of problems, tolerance, fov, etc.
- `validator_options` — validator-specific parameters.
- `extra_libs` — extra CMake libraries to link.
- `targets.adapter_validator` — required validator binary.

## PoseLib Native Benchmark

The `poselib_native` backend uses:

- Copied PoseLib sources under `cpp/external/poselib/`.
- Existing PoseLib benchmark logic under `cpp/external/poselib/benchmark/`.
- A project-owned `poselib_solver_benchmark` CMake target that wraps the
  PoseLib benchmark with:
  - `--solver <key>` to select one solver.
  - Machine-readable JSON benchmark output on stdout.
- No adapter validation step (adapter_validator is `None` for poselib_native
  descriptors).

One experiment runs exactly one selected solver. The same `poselib_solver_benchmark`
binary is built once; the solver is chosen at runtime via `--solver`.

## Supported PoseLib Solver Groups

The project ships manifests for every PoseLib minimal-solver benchmark
case. Key groups:

- **Absolute pose**: `poselib_p3p`, `poselib_p3p_lambdatwist`,
  `poselib_p4pf`, `poselib_p5pfr`, `poselib_p6lp`,
  `poselib_p5lp_radial`, etc.
- **Generalized absolute pose**: `poselib_gp3p`, `poselib_gp4ps`,
  `poselib_gp4ps_degenerate`.
- **Upright absolute pose**: `poselib_up2p`, `poselib_up4pl`,
  `poselib_up1p1ll`, `poselib_up1p2pl`, `poselib_ugp2p`,
  `poselib_ugp3ps`, `poselib_ugp4pl`.
- **Point/line pose solvers**: `poselib_p2p2pl`, `poselib_p3p1llf`,
  `poselib_p2p2llf`, `poselib_p1p3llf`, `poselib_p4llf`,
  `poselib_p2p1ll`, `poselib_p1p2ll`, `poselib_p3ll`.
- **Relative pose**: `poselib_relpose_5pt`, `poselib_relpose_8pt`,
  `poselib_relpose_8pt_100pts`, `poselib_shared_focal_relpose_6pt`.
- **Generalized relative pose**: `poselib_gen_relpose_5p1pt`,
  `poselib_gen_relpose_6pt`, `poselib_gen_relpose_upright_4pt`.
- **Upright relative pose**: `poselib_relpose_upright_3pt`,
  `poselib_relpose_upright_planar_2pt`,
  `poselib_relpose_upright_planar_3pt`.
- **Monodepth relative pose**: `poselib_monodepth_relpose_3pt`,
  `poselib_monodepth_shared_focal_relpose_3pt`,
  `poselib_monodepth_varying_focal_relpose_3pt`.
- **Homography**: `poselib_homography_4pt`,
  `poselib_homography_4pt_cheirality`.

## Examples

| solver_id | Backend | Category |
|---|---|---|
| `lambdatwist_p3p` | absolute_pose | Absolute pose |
| `poselib_p3p` | poselib_native | Absolute pose |
| `poselib_gp3p` | poselib_native | Generalized absolute pose |
| `poselib_relpose_5pt` | poselib_native | Relative pose |
| `poselib_homography_4pt` | poselib_native | Homography |

## Commands

```powershell
# Default solver (lambdatwist_p3p)
py -m orchestrator.cli.app baseline run

# PoseLib P3P
py -m orchestrator.cli.app baseline run --solver poselib_p3p

# PoseLib relative pose 5-pt
py -m orchestrator.cli.app baseline run --solver poselib_relpose_5pt

# PoseLib homography 4-pt
py -m orchestrator.cli.app baseline run --solver poselib_homography_4pt
```

## What the LLM Optimizes

The LLM receives only the solver's own source files:

- When `target_file` and `optimization_scope.allowed_files` are not
  explicitly configured, the solver descriptor's `default_target_file` and
  `default_allowed_files` are used.
- For `poselib_p3p`, this means only
  `cpp/external/poselib/PoseLib/solvers/p3p.cc` by default.
- The LLM does **not** receive:
  - All PoseLib sources at once.
  - Benchmark files, adapter code, CMake files, or test files.
  - Any source outside the configured allowed files.
