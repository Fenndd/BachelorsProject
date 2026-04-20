# Architecture

This project uses C++ for the algorithmic layer and Python CLI components for experiment orchestration.
Runs are executed in an isolated `workspace/` directory to keep temporary data separated from source code.
Persistent outputs are written to `results/` so they can be analyzed and reported later.

Current scope: repository scaffold and environment preparation only.
