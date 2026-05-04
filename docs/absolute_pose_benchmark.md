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

The benchmark runner prints stable snake_case key-value lines such as `solver_name`, `num_cases`, `success_rate`, `runtime_ns_per_case_median`, and `correctness_passed`. The Python baseline CLI parses these values into `metrics.json`, `summary.txt`, and compact `index.jsonl` fields. Candidate verification reuses the same parser and stores parsed values in each candidate run's `verification.json`.

## Adapter Validation

`absolute_pose_lambdatwist_adapter_validator` is a benchmark-preparation executable that checks whether the Lambda Twist P3P adapter is trustworthy before it is used as part of fixed evaluation.

The validator currently covers the only implemented adapter, Lambda Twist P3P. It checks adapter metadata, deterministic synthetic case solving, finite pose output, rotation matrix sanity, and reprojection correctness using the best returned pose across all P3P solutions. The maximum reprojection error is printed as a diagnostic; the hard reprojection gate uses success rate and mean best reprojection error.

Exit code `0` means the adapter is accepted. Exit code `1` means the adapter is rejected and should not be used for fixed benchmark evaluation until investigated.

Python orchestration, candidate comparison, best-candidate selection, and candidate promotion are not part of adapter validation yet.

## Candidate Verification

`py -m orchestrator.execution.verify_candidate --candidate-run <candidate_run_dir>` runs the benchmark-family path inside the materialized candidate workspace only. It configures and builds the isolated C++ copy, runs `baseline_smoke_test`, runs `absolute_pose_lambdatwist_adapter_validator`, runs `absolute_pose_lambdatwist_benchmark`, and parses the benchmark stdout into structured verification metrics. This step is deterministic and does not call an LLM.

Candidate verification builds default to **Release** for runtime metric accuracy. The build type is controlled by the `CMAKE_BUILD_TYPE` environment variable (default `Release`) or the optional `--cmake-build-type` CLI argument to `verify_candidate`. The selected build type is recorded in `verification.json`.

## Benchmark Artifact Audit

`py -m orchestrator.benchmarking.audit_benchmark_pair --baseline-run <baseline_run_dir> --candidate-run <candidate_run_dir>` checks whether one baseline benchmark artifact and one candidate verification artifact are valid and comparable.

The audit verifies that both artifacts parsed successfully, use the same benchmark family and solver, use the same number of cases, expose nanosecond runtime metrics, and include correctness/reprojection fields. It writes `benchmark_artifact_audit.json` into the candidate run directory.

The audit only answers whether later comparison is safe. It does not decide whether the candidate is faster, better, accepted, rejected, or promotable.

## Build Type

Benchmark and verification builds default to **Release** (optimized). Debug builds produce misleading runtime metrics and should not be used for performance comparisons.

The build type is controlled by:
- Environment variable: `CMAKE_BUILD_TYPE` (default: `Release`)
- CLI argument: `--cmake-build-type <value>` (on `verify_candidate`)

The selected build type is:
- Passed to CMake configure as `-DCMAKE_BUILD_TYPE=<value>`
- Passed to `cmake --build` as `--config <value>`
- Recorded in `verification.json`
- Mentioned in `verification_summary.txt`

The benchmark artifact audit checks that baseline and candidate artifacts have the same build type. A mismatch triggers `build_type_mismatch`. Missing build type in older artifacts triggers `build_type_not_recorded` as a warning for backward compatibility.

## Not Implemented Yet

- JSON metrics output
- comparator and best-candidate selection
- candidate promotion
- additional absolute pose solvers
- other solver families such as relative pose, homography, triangulation, PnP, EPnP, or UPnP