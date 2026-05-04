# Architecture

This project uses C++ for the algorithmic layer and Python for command-line automation.

The current baseline path is intentionally minimal:

1. CMake configures the C++ project.
2. The Lambda Twist baseline target and project-owned executables are built.
3. A smoke test, runner, and simple benchmark execute from the Python CLI entry point.

The C++ baseline boundary is:

- `cpp/external/lambdatwist/`: imported third-party Lambda Twist source.
- `lambdatwist_baseline`: project CMake target wrapping the imported solver.
- `baseline_runner`, `baseline_smoke_test`, and `baseline_benchmark`: project-owned executable entry points.

The baseline Python entry point is `orchestrator/cli/main.py`.
It remains early baseline automation, not the LLM optimization entry point.

This split is intentional: baseline reproducibility and LLM optimization
experiments have separate command-line entry points. The baseline CLI should
stay focused on configure/build/run/benchmark of the clean baseline, while
`orchestrator.experiments.run_experiment` is the main entry point for configured
LLM optimization experiments.

The first LLM path is implemented as separate orchestration commands:

- `orchestrator.llm.generate_candidate`: reads one source file, sends a controlled prompt to DeepSeek, parses the response, and stores candidate artifacts.
- `orchestrator.patching.materialize_candidate`: applies a generated candidate diff only inside an isolated `workspace/candidates/<candidate_run_id>/` copy.
- `orchestrator.execution.verify_candidate`: runs a narrow smoke verification for a materialized candidate workspace.
- `orchestrator.experiments.run_experiment`: runs configured candidate-generation iterations with optional materialization and smoke verification.

Experiment runs use `workspace/` for temporary candidate copies and `results/` for persistent outputs. The main `cpp/` source tree is not modified by candidate materialization.

Still not implemented: automatic promotion of candidates into the main source tree, candidate benchmark runs, benchmark runtime parsing, performance comparison, best candidate selection, and full reporting.
