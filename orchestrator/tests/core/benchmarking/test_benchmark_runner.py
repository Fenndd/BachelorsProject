"""Tests for benchmark runner helpers."""

from __future__ import annotations

import pytest
import sys

pytestmark = pytest.mark.unit
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator.core.benchmarking.benchmark_runner import (
    build_benchmark_run_command,
    build_cmake_build_command,
    configure_cmake_command,
    find_executable,
    format_command,
    write_step_log,
)
from orchestrator.core.benchmarking.solver_registry import get_solver_descriptor


class FormatCommandTests(unittest.TestCase):
    def test_simple_command(self) -> None:
        self.assertEqual(format_command(["cmake", "--version"]), "cmake --version")

    def test_command_with_spaces(self) -> None:
        result = format_command(["cmake", "--build", "my build dir"])
        self.assertIn('"my build dir"', result)

    def test_empty_command(self) -> None:
        self.assertEqual(format_command([]), "")


class BuildCmakeBuildCommandTests(unittest.TestCase):
    def test_default_args(self) -> None:
        cmd = build_cmake_build_command("cmake", Path("/build"), "my_target", "Release")
        self.assertEqual(cmd[0], "cmake")
        self.assertEqual(cmd[1], "--build")
        self.assertIn("--target", cmd)
        self.assertIn("my_target", cmd)
        self.assertIn("--config", cmd)
        self.assertIn("Release", cmd)


class BuildBenchmarkRunCommandTests(unittest.TestCase):
    def test_absolute_pose_runs_executable_without_args(self) -> None:
        descriptor = get_solver_descriptor("lambdatwist_p3p")
        cmd = build_benchmark_run_command(Path("/tmp/benchmark"), descriptor)
        self.assertEqual(cmd, [str(Path("/tmp/benchmark"))])

    def test_poselib_native_selects_solver_and_json(self) -> None:
        descriptor = get_solver_descriptor("poselib_p3p")
        cmd = build_benchmark_run_command(Path("/tmp/poselib_solver_benchmark"), descriptor)
        self.assertEqual(
            cmd,
            [str(Path("/tmp/poselib_solver_benchmark")), "--solver", "p3p", "--json"],
        )


class ConfigureCmakeCommandTests(unittest.TestCase):
    def test_minimal_args(self) -> None:
        cmd = configure_cmake_command(
            source_dir=Path("/src"),
            build_dir=Path("/build"),
            eigen_include_dir="/eigen",
        )
        self.assertIn("-S", cmd)
        self.assertIn("-B", cmd)
        self.assertIn("-DEIGEN3_INCLUDE_DIR=/eigen", cmd)
        self.assertIn("-DCMAKE_BUILD_TYPE=Release", cmd)

    def test_full_args(self) -> None:
        cmd = configure_cmake_command(
            source_dir=Path("/src"),
            build_dir=Path("/build"),
            eigen_include_dir="/eigen",
            cmake_generator="Ninja",
            cmake_cxx_compiler="/usr/bin/g++",
            cmake_make_program="/usr/bin/make",
            cmake_build_type="Debug",
            cmake_exe="/custom/cmake",
        )
        self.assertIn("/custom/cmake", cmd)
        self.assertIn("-G", cmd)
        self.assertIn("Ninja", cmd)
        self.assertIn("-DCMAKE_CXX_COMPILER=/usr/bin/g++", cmd)
        self.assertIn("-DCMAKE_MAKE_PROGRAM=/usr/bin/make", cmd)
        self.assertIn("-DCMAKE_BUILD_TYPE=Debug", cmd)


class FindExecutableTests(unittest.TestCase):
    def test_finds_exe_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir)
            exe = build_dir / "sub" / "my_target.exe"
            exe.parent.mkdir(parents=True)
            exe.write_text("dummy")

            with mock.patch.object(sys, "platform", "win32" if sys.platform != "win32" else "win32"):
                with mock.patch("orchestrator.core.benchmarking.benchmark_runner.platform") as mock_plat:
                    mock_plat.system.return_value = "Windows"
                    result = find_executable(build_dir, "my_target")
                    self.assertEqual(result.name, "my_target.exe")

    def test_finds_exe_on_linux(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir)
            exe = build_dir / "sub" / "my_target"
            exe.parent.mkdir(parents=True)
            exe.write_text("dummy")

            with mock.patch("orchestrator.core.benchmarking.benchmark_runner.platform") as mock_plat:
                mock_plat.system.return_value = "Linux"
                result = find_executable(build_dir, "my_target")
                self.assertEqual(result.name, "my_target")

    def test_raises_when_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            build_dir = Path(tmpdir)
            with self.assertRaises(FileNotFoundError):
                find_executable(build_dir, "nonexistent_target")


class WriteStepLogTests(unittest.TestCase):
    def test_writes_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            write_step_log(
                log_path,
                "test_step",
                ["cmd", "arg"],
                Path("/cwd"),
                0,
                "output",
                "",
            )
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("STEP: test_step", content)
            self.assertIn('COMMAND: cmd arg', content)
            self.assertIn("STDOUT:", content)
            self.assertIn("output", content)
            self.assertIn("EXIT_CODE: 0", content)


if __name__ == "__main__":
    unittest.main()
