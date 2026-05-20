"""Tests for generate_candidate --allowed-file resolution."""

from __future__ import annotations

import unittest

from orchestrator.core.llm.generate_candidate import (
    CandidateGenerationFailure,
    _resolve_allowed_files,
)


class GenerateCandidateAllowedFilesTests(unittest.TestCase):
    def test_allowed_files_are_normalized_and_deduplicated(self) -> None:
        self.assertEqual(
            _resolve_allowed_files(
                [
                    r"cpp\external\lambdatwist\p3p.cc",
                    "cpp/external/lambdatwist/p3p.cc",
                ],
                "cpp/external/lambdatwist/p3p.cc",
            ),
            ["cpp/external/lambdatwist/p3p.cc"],
        )

    def test_missing_allowed_files_defaults_to_target_file(self) -> None:
        self.assertEqual(
            _resolve_allowed_files(None, "cpp/external/lambdatwist/p3p.cc"),
            ["cpp/external/lambdatwist/p3p.cc"],
        )

    def test_invalid_allowed_file_raises_generation_failure(self) -> None:
        with self.assertRaises(CandidateGenerationFailure) as ctx:
            _resolve_allowed_files(["cpp/../CMakeLists.txt"], "cpp/file.cc")

        self.assertEqual(ctx.exception.failed_step, "parse_args")
        self.assertIn("Invalid --allowed-file", ctx.exception.error_message)


if __name__ == "__main__":
    unittest.main()