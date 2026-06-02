# Algorithm / Solver Support

## `solver_id`

`solver_id` is the project-level identifier for a solver algorithm. It is
used consistently across:

- Experiment configs (`solver_id` field).
- Baseline runs (`--solver` flag on the CLI).
- The solver registry (`get_solver_descriptor(solver_id)`).
- Closed-loop experiment runner (verification stage dispatches by
  descriptor).

## Benchmark Backend

The project supports one benchmark backend:

| Backend | Model | Used by |
|---|---|---|
| `poselib_native` | PoseLib's own benchmark infrastructure with `--solver` selection and machine-readable JSON output | All `poselib_*` solvers |

The backend controls which CMake targets are built, which parser reads the
benchmark stdout, and which solver key is passed at runtime.

## Solver Manifests

Each solver is declared in a per-solver JSON manifest:

```
cpp/bench/poselib_native/solvers/poselib_p3p_lambdatwist.json
cpp/bench/poselib_native/solvers/poselib_p3p.json
cpp/bench/poselib_native/solvers/poselib_relpose_5pt.json
...
```

Manifests are discovered automatically at import time by the solver
registry. All registered manifests use the `poselib_native` family.

### Key Manifest Fields

| Field | Description |
|---|---|
| `solver_id` | Unique project-level identifier. |
| `family` | `"poselib_native"`. |
| `display_name` | Human-readable label for UIs. |
| `benchmark_backend` | Backend name (must match family for poselib_native). |
| `benchmark_target` | CMake target for the benchmark executable. |
| `benchmark_solver_key` | PoseLib solver name passed via `--solver`. |
| `benchmark_kind` | Category: `absolute_pose`, `relative_pose`, etc. |
| `default_target_file` | Repo-relative path to the solver's primary source file. |
| `default_allowed_files` | Repo-relative paths allowed for downstream validation. |
| `targets` | CMake target names. PoseLib-native manifests use `poselib_solver_benchmark`. |

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

The project ships manifests for PoseLib minimal-solver benchmark cases. Key groups:

- **Absolute pose**: `p3p`, `p3p_lambdatwist`, `p4pf`, `p5pfr`, `p5lp_radial`, `p6lp`, etc.
- **Generalized absolute pose**: `gp3p`, `gp4ps`, etc.
- **Upright absolute pose**: `up2p`, `up4pl`, `ugp2p`, `ugp3ps`, etc.
- **Point/line pose solvers**: `p2p2pl`, `p3p1llf`, `p2p2llf`, etc.
- **Relative pose**: `relpose_5pt`, `relpose_8pt`, `shared_focal_relpose_6pt`, etc.
- **Generalized relative pose**: `gen_relpose_5p1pt`, `gen_relpose_6pt`, `gen_relpose_upright_4pt`.
- **Upright relative pose**: `relpose_upright_3pt`, `relpose_upright_planar_2pt`, `relpose_upright_planar_3pt`.
- **Monodepth relative pose**: `monodepth_relpose_3pt`, `monodepth_shared_focal_relpose_3pt`, `monodepth_varying_focal_relpose_3pt`.
- **Homography**: `homography_4pt`, `homography_4pt_cheirality`.

## Examples

| solver_id | Backend | Category |
|---|---|---|
| `poselib_p3p_lambdatwist` | poselib_native | Absolute pose |
| `poselib_p3p` | poselib_native | Absolute pose |
| `poselib_gp3p` | poselib_native | Generalized absolute pose |
| `poselib_relpose_5pt` | poselib_native | Relative pose |
| `poselib_homography_4pt` | poselib_native | Homography |

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
