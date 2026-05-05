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

- `core/` contains generic absolute pose data types, solver interface, deterministic case generation, validation, metrics, benchmark timing logic, and the shared `correctness_policy_passed()` helper.
- `adapters/lambdatwist_p3p/` contains the only current concrete solver adapter and is the only new benchmark-family code that depends on Lambda Twist.
- `runners/` contains executable benchmark entry points.

## Correctness Policy

The `correctness_policy_passed()` function in `absolute_pose_types.hpp` / `absolute_pose_benchmark.cpp` is the single shared gate used by both the family benchmark runner and the adapter validator. It accepts `AbsolutePoseBenchmarkMetrics` and `BenchmarkOptions` and returns `true` when all configured acceptance criteria are met:

- `num_cases > 0`
- `success_rate >= options.min_success_rate` (default: 0.99)
- `mean_best_reprojection_error <= options.reprojection_error_threshold` (default: 1e-6)
- If `options.require_all_cases_valid`: also `valid_cases == num_cases`
- If `options.use_max_reprojection_error_as_hard_gate`: also `max_best_reprojection_error <= options.reprojection_error_threshold`

The benchmark runner uses `correctness_policy_passed()` to set the `correctness_passed` field in its output. The benchmark executable exit code indicates whether metrics were produced successfully; it returns `0` after successful metric production even when `correctness_passed=false`. The adapter validator uses the same function for its `reprojection_check_passed` gate, ensuring consistent correctness semantics.

`BenchmarkOptions` has been extended with the correctness policy fields (`min_success_rate`, `require_all_cases_valid`, `use_max_reprojection_error_as_hard_gate`) alongside the existing `reprojection_error_threshold`.

## Old vs. New Benchmark

`cpp/bench/baseline_benchmark.cpp` remains as the original minimal fixed-input compatibility benchmark and is not removed.

`absolute_pose_lambdatwist_benchmark` uses the new family architecture: it generates many deterministic synthetic cases before timing, validates every case outside the timed section, and reports stable key-value summary metrics.

The benchmark runner prints stable snake_case key-value lines such as `solver_name`, `num_cases`, `success_rate`, `runtime_ns_per_case_median`, and `correctness_passed`. The Python baseline CLI parses these values as an explicit `parse_absolute_pose_lambdatwist_benchmark` step and stores them in `metrics.json`, `summary.txt`, and compact `index.jsonl` fields.

Benchmark execution success means the executable ran and printed metrics; it does not encode numerical correctness in the process exit code. If the executable succeeds but required stdout fields cannot be parsed, the baseline run fails at the parse step while preserving `parse_success=false`, `missing_fields`, `parse_errors`, and any partially parsed metrics. If parsing succeeds but `correctness_passed=false`, baseline and candidate verification fail at `benchmark_correctness_check` while preserving all parsed benchmark metrics.

Policy-diagnostic lines (`min_success_rate`, `require_all_cases_valid`, `use_max_reprojection_error_as_hard_gate`, `reprojection_error_threshold`, `correctness_passed`) and additional metadata (`warmup_iterations`, `timed_iterations`, `random_seed`, `points_per_case`, `runtime_unit`, `valid_cases`, `total_solutions`) are printed by the benchmark runner for traceability and parsed by the Python parser as optional fields.

## Adapter Validation

`absolute_pose_lambdatwist_adapter_validator` is a benchmark-preparation executable that checks whether the Lambda Twist P3P adapter is trustworthy before it is used as part of fixed evaluation.

The validator currently covers the only implemented adapter, Lambda Twist P3P. It checks adapter metadata, deterministic synthetic case solving, finite pose output, rotation matrix sanity, and reprojection correctness using `correctness_policy_passed()` on the validation metrics. The maximum reprojection error is printed as a diagnostic.

Exit code `0` means the adapter is accepted. Exit code `1` means the adapter is rejected and should not be used for fixed benchmark evaluation until investigated.

Python orchestration, candidate comparison, best-candidate selection, and candidate promotion are not part of adapter validation yet.

## Correctness Policy Unit Test

`absolute_pose_correctness_policy_test` is a standalone C++ test executable that validates `correctness_policy_passed()` behavior with a matrix of metric/option combinations:

- Perfect metrics with default options
- Success rate at threshold (0.99)
- Success rate below threshold
- Mean reprojection error above threshold
- `require_all_cases_valid` with all cases valid
- `require_all_cases_valid` with one invalid case
- `use_max_reprojection_error_as_hard_gate` with max below/above threshold
- Zero cases (always fails)

The test links against `absolute_pose_core` and does not require a solver adapter.

## Candidate Verification

`py -m orchestrator.execution.verify_candidate --candidate-run <candidate_run_dir>` runs the benchmark-family path inside the materialized candidate workspace only. It configures and builds the isolated C++ copy, runs `baseline_smoke_test`, runs `absolute_pose_lambdatwist_adapter_validator`, runs `absolute_pose_lambdatwist_benchmark`, and parses the benchmark stdout into structured verification metrics. Benchmark parse failure fails candidate verification. If parsing succeeds but `correctness_passed=false`, verification fails at `benchmark_correctness_check` while keeping parsed metrics in `verification.json`. This step is deterministic and does not call an LLM.

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