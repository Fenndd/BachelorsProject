"""Unit tests for optimization scope enforcement and path validation."""

from __future__ import annotations

import unittest

from orchestrator.patching.scope_validation import (
    normalize_repo_path,
    validate_allowed_files_list,
    validate_patch_scope,
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


class ValidatePatchScopeTests(unittest.TestCase):
    """Tests for validate_patch_scope function from scope_validation module."""

    def setUp(self) -> None:
        self.allowed = ["cpp/external/lambdatwist/p3p.cc"]
        self.target = ["cpp/external/lambdatwist/p3p.cc"]
        self.patched = ["cpp/external/lambdatwist/p3p.cc"]

    def test_scope_pass(self) -> None:
        validate_patch_scope(self.target, self.patched, self.allowed)

    def test_target_outside_allowed_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_patch_scope(
                target_files=["cpp/bench/some_bench.cpp"],
                patched_files=[],
                allowed_files=self.allowed,
            )
        self.assertIn("outside allowed optimization scope", str(ctx.exception))

    def test_patched_outside_allowed_rejected(self) -> None:
        """patched file is in target_files but not in allowed_files."""
        with self.assertRaises(ValueError) as ctx:
            validate_patch_scope(
                target_files=["cpp/external/lambdatwist/p3p.cc", "cpp/bench/bench.cpp"],
                patched_files=["cpp/bench/bench.cpp"],
                allowed_files=["cpp/external/lambdatwist/p3p.cc"],
            )
        self.assertIn("outside allowed optimization scope", str(ctx.exception))

    def test_patched_outside_candidate_target_files_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_patch_scope(
                target_files=["cpp/external/lambdatwist/p3p.cc"],
                patched_files=["cpp/external/lambdatwist/other.cc"],
                allowed_files=["cpp/external/lambdatwist/p3p.cc"],
            )
        self.assertIn("not listed in", str(ctx.exception))

    def test_benchmark_file_not_allowed(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            validate_patch_scope(
                target_files=["cpp/bench/bench_p3p.cpp"],
                patched_files=[],
                allowed_files=self.allowed,
            )
        self.assertIn("outside allowed optimization scope", str(ctx.exception))

    def test_cmakelists_not_allowed(self) -> None:
        """patched CMakeLists.txt is in target_files but not in allowed_files."""
        with self.assertRaises(ValueError) as ctx:
            validate_patch_scope(
                target_files=["cpp/external/lambdatwist/p3p.cc", "cpp/CMakeLists.txt"],
                patched_files=["cpp/CMakeLists.txt"],
                allowed_files=["cpp/external/lambdatwist/p3p.cc"],
            )
        self.assertIn("outside allowed optimization scope", str(ctx.exception))

    def test_empty_patched_list_does_not_fail(self) -> None:
        validate_patch_scope(self.target, [], self.allowed)


class ExperimentConfigOptimizationScopeTests(unittest.TestCase):
    """Tests for optimization scope loading from config JSON."""

    def test_missing_scope_defaults_to_target_file(self) -> None:
        config = load_experiment_config(
            "configs/experiments/mock_p3p_basic.json"
        )
        self.assertIsInstance(config.optimization_scope, OptimizationScopeConfig)
        self.assertIn(
            "cpp/external/lambdatwist/p3p.cc",
            config.optimization_scope.allowed_files,
        )

    def test_scope_with_explicit_allowed_files(self) -> None:
        config = load_experiment_config(
            "configs/experiments/deepseek_flash_p3p_basic.json"
        )
        self.assertEqual(
            config.optimization_scope.allowed_files,
            ["cpp/external/lambdatwist/p3p.cc"],
        )


if __name__ == "__main__":
    unittest.main()
