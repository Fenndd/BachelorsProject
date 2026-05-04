# Absolute Pose Benchmark Family

## Scope

The new project-owned benchmark family lives under:

`cpp/bench/families/geometric_pose_solvers/absolute_pose_solvers/`

It is the future benchmark direction for calibrated absolute pose solvers. The current concrete scope is intentionally narrow:

- calibrated point-to-point absolute pose cases
- one concrete adapter: Lambda Twist P3P
- deterministic synthetic case generation
- correctness validation via best reprojection error across all returned poses
- median runtime measurement over pre-generated cases

## Pose Convention

All core benchmark code and adapters use the canonical pose convention:

`X_cam = R * X_world + t`

`R` is stored as a row-major 3x3 rotation matrix and `t` is a 3D translation vector.

## Structure

- `core/` contains generic absolute pose data types, solver interface, deterministic case generation, validation, metrics, and benchmark timing logic.
- `adapters/lambdatwist_p3p/` contains the only current concrete solver adapter and is the only new benchmark-family code that depends on Lambda Twist.
- `runners/` contains executable benchmark entry points.

## Old vs. New Benchmark

`cpp/bench/baseline_benchmark.cpp` remains as the original minimal fixed-input compatibility benchmark and is not removed.

`absolute_pose_lambdatwist_benchmark` uses the new family architecture: it generates many deterministic synthetic cases before timing, validates every case outside the timed section, and reports stable key-value summary metrics.

## Not Implemented Yet

- JSON metrics output
- Python benchmark parsing
- candidate benchmark execution
- comparator and best-candidate selection
- candidate promotion
- additional absolute pose solvers
- other solver families such as relative pose, homography, triangulation, PnP, EPnP, or UPnP
