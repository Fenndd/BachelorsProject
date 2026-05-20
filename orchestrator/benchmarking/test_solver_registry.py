"""Tests for the solver descriptor registry."""

from __future__ import annotations

import unittest

from orchestrator.benchmarking.solver_registry import (
    SolverBenchmarkDescriptor,
    default_solver_descriptor,
    get_solver_descriptor,
    list_solver_descriptors,
)


class SolverRegistryTests(unittest.TestCase):
    def test_default_descriptor_is_lambdatwist_p3p(self) -> None:
        desc = default_solver_descriptor()
        self.assertIsInstance(desc, SolverBenchmarkDescriptor)
        self.assertEqual(desc.solver_id, "lambdatwist_p3p")
        self.assertEqual(desc.family, "absolute_pose_solvers")
        self.assertEqual(desc.benchmark_target, "absolute_pose_lambdatwist_benchmark")
        self.assertEqual(desc.adapter_validator_target, "absolute_pose_lambdatwist_adapter_validator")
        self.assertEqual(desc.runtime_unit, "ns")
        self.assertEqual(desc.runtime_metric_key, "parsed_runtime_ns_per_problem_median")

    def test_get_solver_descriptor_returns_lambdatwist(self) -> None:
        desc = get_solver_descriptor("lambdatwist_p3p")
        self.assertEqual(desc.solver_id, "lambdatwist_p3p")

    def test_unknown_solver_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            get_solver_descriptor("nonexistent_solver")
        self.assertIn("nonexistent_solver", str(ctx.exception))
        self.assertIn("lambdatwist_p3p", str(ctx.exception))

    def test_list_solver_descriptors_returns_non_empty_list(self) -> None:
        descriptors = list_solver_descriptors()
        self.assertIsInstance(descriptors, list)
        self.assertGreaterEqual(len(descriptors), 1)
        ids = {d.solver_id for d in descriptors}
        self.assertIn("lambdatwist_p3p", ids)

    def test_descriptor_is_frozen(self) -> None:
        desc = default_solver_descriptor()
        with self.assertRaises(Exception):
            desc.solver_id = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
