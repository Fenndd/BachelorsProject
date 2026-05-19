# Absolute Pose Benchmark Family

## Scope

The project-owned absolute-pose benchmark lives under:

`cpp/bench/families/geometric_pose_solvers/absolute_pose_solvers/`

The current concrete scope is intentionally narrow: Lambda Twist P3P only. The
`lambdatwist_p3p` runner follows the PoseLib `p3p_lambdatwist` benchmark
protocol for calibrated absolute pose. It does not use pixels, intrinsics, or
reprojection-error metrics.

## Protocol

The benchmark uses the pose convention `X_cam = R * X_world + t`.

For the runner:

- `num_problems = 100000`
- `camera_fov = 75`
- `n_point_point = 3`
- `n_point_line = 0`
- `tolerance = 1e-6`
- `timed_iterations = 10`

Problem generation creates normalized bearing vectors `x_point_` and 3D world
points `X_point_` once before timing. The Lambda Twist adapter passes those
vectors directly to `lambdatwist::p3p`.

Correctness uses the calibrated bearing constraint from PoseLib. For each
returned pose, every point correspondence must satisfy the normalized bearing
constraint within tolerance. The benchmark also computes pose error against the
ground-truth pose and counts a problem as GT-found when the best pose error is
below tolerance.

## Output

The benchmark prints stable key-value lines:

- `solver_name`
- `num_problems`
- `total_solutions`
- `solutions_per_problem`
- `valid_solutions`
- `valid_solutions_percent`
- `gt_found`
- `gt_found_percent`
- `runtime_ns_total_median`
- `runtime_ns_per_problem_median`
- `tolerance`
- `camera_fov`
- `n_point_point`
- `n_point_line`
- `timed_iterations`
- `runtime_unit`
- `correctness_passed`

`correctness_passed` is true when there is at least one problem, at least 99%
of problems find the ground-truth pose, at least one returned solution is valid,
and median runtime per problem is positive.

## Validation And Artifacts

`absolute_pose_lambdatwist_adapter_validator` runs the same protocol on 1000
problems and exits 0 only if metadata checks, finite/rotation output checks, and
benchmark-style correctness checks pass.

The Python parser stores normalized fields such as
`parsed_num_problems`, `parsed_gt_found_percent`,
`parsed_valid_solutions_percent`, and
`parsed_runtime_ns_per_problem_median`. Old reprojection fields are no longer
part of this benchmark protocol.
