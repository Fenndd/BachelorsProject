# Architecture Overview

## Intent

The project is designed as a modular research framework for automated optimization of 3D vision C++ algorithms with LLM assistance.

## High-Level Components

- `cpp/`: algorithm implementations, headers, and future performance-focused tests/benchmarks.
- `orchestrator/`: Python CLI-centered orchestration layer for running and coordinating experiments.
- `configs/`: configuration inputs for experiments, model selection, and defaults.
- `workspace/`: isolated execution directory used during experiment runs.
- `results/`: persisted artifacts, metrics, logs, and reports from completed runs.
- `docs/`: architecture decisions, roadmap, and research notes.

## Separation Principle

Execution workspace and result storage are intentionally separated to keep runs reproducible and artifact management clean.

## Current State

This document describes the initial scaffold architecture only.  
No business logic, pipeline implementation, API integration, or production-ready experiment flow is included yet.
