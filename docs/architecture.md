# Architecture

This project uses C++ for the algorithmic layer and Python for command-line automation.

The current implemented path is intentionally minimal:

1. CMake configures the C++ project.
2. The Lambda Twist baseline target and project-owned executables are built.
3. A smoke test, runner, and simple benchmark execute from the Python CLI entry point.

The C++ baseline boundary is:

- `cpp/external/lambdatwist/`: imported third-party Lambda Twist source.
- `lambdatwist_baseline`: project CMake target wrapping the imported solver.
- `baseline_runner`, `baseline_smoke_test`, and `baseline_benchmark`: project-owned executable entry points.

The Python entry point is `orchestrator/cli/main.py`.
It is early baseline automation, not a full experiment orchestration system.

Future experiment runs are expected to use `workspace/` for temporary artifacts and `results/` for persistent outputs.
Result storage, experiment management, reporting, and LLM-driven optimization are not implemented yet.
