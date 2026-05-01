# Result Storage Format

## Purpose

The `results/` directory is reserved for persistent outputs produced by experiment runs. It is intended to keep enough information to inspect what was executed, whether it succeeded, which environment was used, and which raw logs or metrics were produced.

The baseline CLI writes one detailed run directory per execution and appends one compact record to the global JSON Lines index.

## One Run

One run represents a single execution of one experiment scenario. For the current baseline phase, a run is one complete attempt to configure CMake, build the baseline targets, execute the smoke test, execute the runner, and execute the benchmark.

Each run should be stored in its own directory under `results/runs/<run_id>/`. The directory should be self-contained and should not depend on other run directories for interpretation.

## Run ID Format

The recommended `run_id` format is:

```text
YYYY-MM-DD_HH-MM-SS_<scenario>
```

Example:

```text
2026-05-01_23-40-12_baseline
```

The timestamp should use local time unless a later implementation explicitly standardizes on UTC. The `<scenario>` suffix should be short, lowercase, and descriptive, for example `baseline`.

## Directory Layout

```text
results/
├─ index.jsonl
└─ runs/
   └─ <run_id>/
      ├─ metadata.json
      ├─ status.json
      ├─ metrics.json
      ├─ logs/
      │  ├─ configure_cmake.log
      │  ├─ build_baseline_smoke_test.log
      │  ├─ build_baseline_runner.log
      │  ├─ build_baseline_benchmark.log
      │  ├─ run_baseline_smoke_test.log
      │  ├─ run_baseline_runner.log
      │  └─ run_baseline_benchmark.log
      └─ summary.txt
```

## `index.jsonl`

`results/index.jsonl` is a global append-only index for quick listing of runs. It uses JSON Lines format: each line is one complete JSON object, and each baseline CLI execution appends exactly one new line.

The index should contain compact summary fields such as run id, scenario, case study, baseline, overall status, failed step, timestamps, repository state, success flags, benchmark raw-output availability, benchmark runtime placeholder, and the run directory path.

Example line:

```json
{"run_id":"2026-05-01_23-40-12_baseline","scenario":"baseline","case_study":"p3p_solver","baseline":"lambda_twist","overall_status":"success","failed_step":null,"started_at":"2026-05-01T23:40:12+02:00","finished_at":"2026-05-01T23:41:03+02:00","git_commit":"abc1234","git_branch":"main","dirty_worktree":false,"build_success":true,"smoke_test_success":true,"runner_success":true,"benchmark_success":true,"benchmark_raw_output_available":true,"benchmark_runtime_ms":null,"run_dir":"results/runs/2026-05-01_23-40-12_baseline"}
```

The index is intentionally compact. Per-run folders remain the source of detailed logs and artifacts.

## `metadata.json`

`metadata.json` should describe the run identity, repository state, and execution environment. It should be written once the run starts and updated with `finished_at` when the run ends.

Recommended fields:

```json
{
  "run_id": "2026-05-01_23-40-12_baseline",
  "scenario": "baseline",
  "case_study": "p3p",
  "baseline": "lambda_twist",
  "started_at": "2026-05-01T23:40:12+02:00",
  "finished_at": "2026-05-01T23:41:03+02:00",
  "repository": {
    "git_commit": "abc1234",
    "git_branch": "main",
    "dirty_worktree": false
  },
  "environment": {
    "python_version": "3.12.0",
    "platform": "Windows-10-10.0.26100-SP0",
    "cmake_exe": "cmake",
    "cmake_generator": "MinGW Makefiles",
    "cxx_compiler": "C:\\path\\to\\g++.exe",
    "eigen3_include_dir": "C:\\path\\to\\eigen"
  }
}
```

The exact values should come from the Python orchestrator, Git, platform inspection, and environment variables used by the baseline flow.

## `status.json`

`status.json` should describe whether the run succeeded and which step failed if the run did not complete successfully.

Recommended fields:

```json
{
  "overall_status": "success",
  "failed_step": null,
  "error_message": null,
  "steps": [
    {
      "name": "configure_cmake",
      "status": "success",
      "exit_code": 0,
      "duration_seconds": 1.42
    },
    {
      "name": "build_baseline_smoke_test",
      "status": "success",
      "exit_code": 0,
      "duration_seconds": 2.31
    }
  ]
}
```

Suggested status values are `success`, `failed`, and `skipped`. If a step fails, later steps that are not executed are marked as `skipped`.

Each step status should contain:

- `name`: stable machine-readable step name.
- `status`: step result, for example `success`, `failed`, or `skipped`.
- `exit_code`: process exit code, or `null` if the step did not run.
- `duration_seconds`: wall-clock duration, or `null` if the step did not run.

## `metrics.json`

`metrics.json` should contain structured results that are useful for later comparison. For the current baseline phase, the file should stay intentionally small.

Recommended fields:

```json
{
  "build_success": true,
  "smoke_test_success": true,
  "runner_success": true,
  "benchmark_success": true,
  "benchmark": {
    "raw_output_available": true,
    "parsed_runtime_ms": null
  },
  "correctness": {
    "basic_smoke_test_passed": true
  }
}
```

`benchmark.parsed_runtime_ms` may be `null` for now because benchmark output parsing is not part of the current baseline storage preparation step.

## `logs/`

The `logs/` directory should contain one log file per command step. Each log file should include:

- Step name.
- Command.
- Working directory.
- Exit code.
- Standard output.
- Standard error.

The log file names should match the stable step names used in `status.json` so humans and tools can connect status entries to raw command output.

## `summary.txt`

`summary.txt` should be a short human-readable summary of the run. It should help a reader quickly understand what scenario ran, whether it succeeded, which step failed if applicable, and where to look next.

Example:

```text
Run: 2026-05-01_23-40-12_baseline
Scenario: baseline
Case study: p3p
Baseline: lambda_twist
Status: success
Started: 2026-05-01T23:40:12+02:00
Finished: 2026-05-01T23:41:03+02:00

All baseline configure, build, smoke test, runner, and benchmark steps completed successfully.
Benchmark raw output is available in logs/run_baseline_benchmark.log.
Parsed benchmark runtime is not available yet.
```

## Successful Run Example

```text
results/
└─ runs/
   └─ 2026-05-01_23-40-12_baseline/
      ├─ metadata.json
      ├─ status.json
      ├─ metrics.json
      ├─ logs/
      │  ├─ configure_cmake.log
      │  ├─ build_baseline_smoke_test.log
      │  ├─ build_baseline_runner.log
      │  ├─ build_baseline_benchmark.log
      │  ├─ run_baseline_smoke_test.log
      │  ├─ run_baseline_runner.log
      │  └─ run_baseline_benchmark.log
      └─ summary.txt
```

In a successful baseline run, `status.json` should have `overall_status` set to `success`, every step should have `status` set to `success`, and the basic success fields in `metrics.json` should be `true`.

## Failed Run `status.json` Example

```json
{
  "overall_status": "failed",
  "failed_step": "build_baseline_benchmark",
  "error_message": "CMake build failed for target baseline_benchmark.",
  "steps": [
    {
      "name": "configure_cmake",
      "status": "success",
      "exit_code": 0,
      "duration_seconds": 1.39
    },
    {
      "name": "build_baseline_smoke_test",
      "status": "success",
      "exit_code": 0,
      "duration_seconds": 2.22
    },
    {
      "name": "build_baseline_runner",
      "status": "success",
      "exit_code": 0,
      "duration_seconds": 2.04
    },
    {
      "name": "build_baseline_benchmark",
      "status": "failed",
      "exit_code": 1,
      "duration_seconds": 0.88
    },
    {
      "name": "run_baseline_smoke_test",
      "status": "skipped",
      "exit_code": null,
      "duration_seconds": null
    },
    {
      "name": "run_baseline_runner",
      "status": "skipped",
      "exit_code": null,
      "duration_seconds": null
    },
    {
      "name": "run_baseline_benchmark",
      "status": "skipped",
      "exit_code": null,
      "duration_seconds": null
    }
  ]
}
```

## Not Implemented Yet

The current repository intentionally leaves the following work for later steps:

- Benchmark output parsing.
- Patch application and LLM-generated optimized variants.
- Comparison between baseline and optimized runs.
- Best candidate selection.
- Advanced reporting and experiment analysis.
