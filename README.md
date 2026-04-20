# LLM-Assisted Optimization of 3D Vision C++ Algorithms

This repository contains the initial project scaffold for a bachelor's thesis on automated optimization of computational efficiency in 3D vision C++ algorithms using LLMs.

## Project Goal

Build an extensible research framework where:
- the algorithmic core is implemented in C++,
- experiments are orchestrated via a Python CLI,
- runs are executed in an isolated workspace,
- outputs are stored in a separate results area.

The first minimal case study is a P3P solver.

## Repository Structure

- `cpp/` — C++ source, headers, tests, benchmarks, and external dependencies.
- `orchestrator/` — Python package for experiment orchestration components.
- `configs/` — experiment, model, and default configuration placeholders.
- `workspace/` — isolated working directory for experiment runs.
- `results/` — stored experiment outputs and artifacts.
- `docs/` — architecture notes and development roadmap.
- `scripts/` — helper utility scripts (non-core logic).

## Status

This is an **initial scaffold only**.  
Business logic, real pipelines, API integrations, and actual tests/benchmarks are intentionally not implemented yet.
