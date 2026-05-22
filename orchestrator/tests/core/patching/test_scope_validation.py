"""Unit tests for optimization scope enforcement and path validation."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.core.patching.scope_validation import (
    normalize_repo_path,
    validate_allowed_files_list,
    validate_candidate_scope,
)
from orchestrator.experiments.experiment_config import (
    ExperimentConfigError,
    OptimizationScopeConfig,
    load_experiment_config,
)


class NormalizeRepoPathTests(unittest.TestCase):
    def test_normal_linux_path(self) -> None:
        self.assertEqual(
            normalize_repo_path("cpp/external/lambdatwist/p3p.cc"),
            "cpp/external/lambdatwist/p3p.cc",
        )

    def test_backslash_normalized_to_forward_slash(self) -> None:
        self.assertEqual(
            normalize_repo_path(r"cpp\external\lambdatwist\p3p.cc"),
            "cpp/external/lambdatwist/p3p.cc",
        )

    def test_absolute_path_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_repo_path("/absolute/path/file.cc")

    def test_windows_drive_prefix_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_repo_path("C:/cpp/file.cc")
        with self.assertRaises(ValueError):
            normalize_repo_path("D:file.cc")

    def test_path_with_dotdot_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_repo_path("cpp/../CMakeLists.txt")

    def test_empty_path_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_repo_path("")
        with self.assertRaises(ValueError):
            normalize_repo_path("   ")

    def test_null_byte_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_repo_path("cpp/file\x00.cpp")


class ValidateAllowedFilesListTests(unittest.TestCase):
    def test_non_empty_list_passes(self) -> None:
        result = validate_allowed_files_list(
            ["cpp/external/lambdatwist/p3p.cc"]
        )
        self.assertEqual(result, ["cpp/external/lambdatwist/p3p.cc"])

    def test_multiple_files(self) -> None:
        result = validate_allowed_files_list(
            [
                "cpp/external/lambdatwist/p3p.cc",
                "cpp/external/lambdatwist/p3p.h",
            ]
        )
        self.assertIn("cpp/external/lambdatwist/p3p.cc", result)
        self.assertIn("cpp/external/lambdatwist/p3p.h", result)

    def test_empty_list_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_allowed_files_list([])

    def test_non_string_items_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_allowed_files_list(["valid.cc", 42])

    def test_invalid_path_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_allowed_files_list(["cpp/../CMakeLists.txt"])

    def test_duplicates_deduplicated(self) -> None:
        result = validate_allowed_files_list(
            ["file.cc", "file.cc"]
        )
        self.assertEqual(len(result), 1)


class ValidateCandidateScopeTests(unittest.TestCase):
    """Tests for candidate edit scope validation."""

    def setUp(self) -> None:
        self.allowed = ["cpp/external/lambdatwist/p3p.cc"]
        self.target = ["cpp/external/lambdatwist/p3p.cc"]
        self.changed = ["cpp/external/lambdatwist/p3p.cc"]

    def test_scope_pass(self) -> None:
        validate_candidate_scope(self.target, self.changed, self.allowed)

    def test_target_outside_allowed_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_candidate_scope(
                target_files=["cpp/bench/some_bench.cpp"],
                changed_files=[],
                allowed_files=self.allowed,
            )
        self.assertIn("outside allowed optimization scope", str(ctx.exception))

    def test_patched_outside_allowed_rejected(self) -> None:
        """patched file is in target_files but not in allowed_files."""
        with self.assertRaises(ValueError) as ctx:
            validate_candidate_scope(
                target_files=["cpp/external/lambdatwist/p3p.cc", "cpp/bench/bench.cpp"],
                changed_files=["cpp/bench/bench.cpp"],
                allowed_files=["cpp/external/lambdatwist/p3p.cc"],
            )
        self.assertIn("outside allowed optimization scope", str(ctx.exception))

    def test_patched_outside_candidate_target_files_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_candidate_scope(
                target_files=["cpp/external/lambdatwist/p3p.cc"],
                changed_files=["cpp/external/lambdatwist/other.cc"],
                allowed_files=["cpp/external/lambdatwist/p3p.cc"],
            )
        self.assertIn("not listed in", str(ctx.exception))

    def test_benchmark_file_not_allowed(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_candidate_scope(
                target_files=["cpp/bench/bench_p3p.cpp"],
                changed_files=[],
                allowed_files=self.allowed,
            )
        self.assertIn("outside allowed optimization scope", str(ctx.exception))

    def test_cmakelists_not_allowed(self) -> None:
        """patched CMakeLists.txt is in target_files but not in allowed_files."""
        with self.assertRaises(ValueError) as ctx:
            validate_candidate_scope(
                target_files=["cpp/external/lambdatwist/p3p.cc", "cpp/CMakeLists.txt"],
                changed_files=["cpp/CMakeLists.txt"],
                allowed_files=["cpp/external/lambdatwist/p3p.cc"],
            )
        self.assertIn("outside allowed optimization scope", str(ctx.exception))

    def test_empty_patched_list_does_not_fail(self) -> None:
        validate_candidate_scope(self.target, [], self.allowed)


class ExperimentConfigOptimizationScopeTests(unittest.TestCase):
    """Tests for optimization scope loading from config JSON."""

    def test_missing_scope_defaults_to_target_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(
                _write_experiment_config(Path(tmpdir), optimization_scope=None)
            )
        self.assertIsInstance(config.optimization_scope, OptimizationScopeConfig)
        self.assertIn(
            "cpp/external/lambdatwist/p3p.cc",
            config.optimization_scope.allowed_files,
        )

    def test_scope_with_explicit_allowed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config = load_experiment_config(
                _write_experiment_config(
                    Path(tmpdir),
                    optimization_scope={"allowed_files": ["cpp/external/lambdatwist/p3p.cc"]},
                )
            )
        self.assertEqual(
            config.optimization_scope.allowed_files,
            ["cpp/external/lambdatwist/p3p.cc"],
        )


def _write_experiment_config(root: Path, *, optimization_scope: dict | None) -> Path:
    payload = {
        "experiment_name": "scope_test",
        "description": "Temporary scope test config",
        "target_file": "cpp/external/lambdatwist/p3p.cc",
        "baseline_run_dir": "results/runs/baseline",
        "candidate_generation": {"max_source_chars": 120000},
        "variants": [
            {
                "variant_id": "default",
                "llm_config": "configs/llm_test.json",
                "iterations": 1,
            }
        ],
    }
    if optimization_scope is not None:
        payload["optimization_scope"] = optimization_scope
    path = root / "experiment.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
