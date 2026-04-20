# Development Environment Targets

This document defines the intended environment for the scaffold stage.

## Toolchain Targets

- Python: target `3.11` (or newer compatible patch release)
- CMake: minimum `3.20`
- C++ standard: `C++20`

## Expected Compiler Examples

- GCC `13+`
- Clang `16+`
- MSVC (Visual Studio 2022 toolset, `19.3x+`)

## Dependency Note

Eigen will be required in the next stage for baseline integration work around Lambda Twist.

Actual dependency integration and build wiring are intentionally postponed until the baseline integration stage.
