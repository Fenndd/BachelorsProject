"""Tests for the solver descriptor registry."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import unittest

from orchestrator.core.benchmarking.solver_registry import (
    SolverBenchmarkDescriptor,
    default_solver_descriptor,
    get_solver_descriptor,
    list_solver_descriptors,
)


class SolverRegistryTests(unittest.TestCase):
    def test_default_descriptor_is_poselib_p3p_lambdatwist(self) -> None:
        desc = default_solver_descriptor()
        self.assertIsInstance(desc, SolverBenchmarkDescriptor)
        self.assertEqual(desc.solver_id, "poselib_p3p_lambdatwist")
        self.assertEqual(desc.family, "poselib_native")
        self.assertEqual(desc.benchmark_target, "poselib_solver_benchmark")
        self.assertIsNone(desc.adapter_validator_target)
        self.assertEqual(desc.runtime_unit, "ns")
        self.assertEqual(desc.runtime_metric_key, "parsed_runtime_ns_per_problem_median")

    def test_get_solver_descriptor_returns_poselib_lambdatwist(self) -> None:
        desc = get_solver_descriptor("poselib_p3p_lambdatwist")
        self.assertEqual(desc.solver_id, "poselib_p3p_lambdatwist")
        self.assertEqual(desc.benchmark_backend, "poselib_native")
        self.assertEqual(desc.family, "poselib_native")

    def test_old_lambdatwist_solver_id_is_not_registered(self) -> None:
        with self.assertRaises(KeyError):
            get_solver_descriptor("lambdatwist_p3p")

    def test_poselib_p3p_descriptor(self) -> None:
        desc = get_solver_descriptor("poselib_p3p")
        self.assertEqual(desc.solver_id, "poselib_p3p")
        self.assertEqual(desc.family, "poselib_native")
        self.assertEqual(desc.benchmark_backend, "poselib_native")
        self.assertEqual(desc.benchmark_target, "poselib_solver_benchmark")
        self.assertEqual(desc.benchmark_solver_key, "p3p")
        self.assertEqual(
            desc.default_target_file,
            "cpp/external/poselib/PoseLib/solvers/p3p.cc",
        )
        self.assertEqual(
            desc.default_allowed_files,
            ("cpp/external/poselib/PoseLib/solvers/p3p.cc",),
        )

    def test_all_required_poselib_solver_ids_are_loaded(self) -> None:
        required = {
            "poselib_p3p",
            "poselib_p3p_lambdatwist",
            "poselib_gp3p",
            "poselib_gp4ps",
            "poselib_gp4ps_degenerate",
            "poselib_p4pf",
            "poselib_p5pfr",
            "poselib_p2p2pl",
            "poselib_p6lp",
            "poselib_p5lp_radial",
            "poselib_p3p1llf",
            "poselib_p2p2llf",
            "poselib_p1p3llf",
            "poselib_p4llf",
            "poselib_p2p1ll",
            "poselib_p1p2ll",
            "poselib_p3ll",
            "poselib_up2p",
            "poselib_up1p1ll",
            "poselib_ugp2p",
            "poselib_ugp3ps",
            "poselib_up1p2pl",
            "poselib_up4pl",
            "poselib_ugp4pl",
            "poselib_relpose_upright_3pt",
            "poselib_gen_relpose_upright_4pt",
            "poselib_relpose_8pt",
            "poselib_relpose_8pt_100pts",
            "poselib_relpose_5pt",
            "poselib_monodepth_relpose_3pt",
            "poselib_shared_focal_relpose_6pt",
            "poselib_monodepth_shared_focal_relpose_3pt",
            "poselib_monodepth_varying_focal_relpose_3pt",
            "poselib_relpose_upright_planar_2pt",
            "poselib_relpose_upright_planar_3pt",
            "poselib_gen_relpose_5p1pt",
            "poselib_gen_relpose_6pt",
            "poselib_homography_4pt",
            "poselib_homography_4pt_cheirality",
        }
        ids = {descriptor.solver_id for descriptor in list_solver_descriptors()}
        self.assertTrue(required.issubset(ids))

    def test_unknown_solver_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            get_solver_descriptor("nonexistent_solver")
        self.assertIn("nonexistent_solver", str(ctx.exception))
        self.assertIn("poselib_p3p_lambdatwist", str(ctx.exception))

    def test_list_solver_descriptors_returns_non_empty_list(self) -> None:
        descriptors = list_solver_descriptors()
        self.assertIsInstance(descriptors, list)
        self.assertGreaterEqual(len(descriptors), 1)
        ids = {d.solver_id for d in descriptors}
        self.assertIn("poselib_p3p_lambdatwist", ids)

    def test_all_descriptors_are_poselib_native(self) -> None:
        for desc in list_solver_descriptors():
            self.assertEqual(desc.family, "poselib_native")
            self.assertEqual(desc.benchmark_backend, "poselib_native")

    def test_descriptor_is_frozen(self) -> None:
        desc = default_solver_descriptor()
        with self.assertRaises(Exception):
            desc.solver_id = "other"  # type: ignore[misc]

    def test_default_solver_missing_raises_clear_error(self) -> None:
        from orchestrator.core.benchmarking import solver_registry

        original_cache = solver_registry._descriptors_cache
        solver_registry._descriptors_cache = {}
        try:
            with self.assertRaises(RuntimeError) as ctx:
                solver_registry.default_solver_descriptor()
            self.assertIn("poselib_p3p_lambdatwist", str(ctx.exception))
            self.assertIn("not registered", str(ctx.exception))
        finally:
            solver_registry._descriptors_cache = original_cache

    def test_require_string_rejects_missing_key(self) -> None:
        from pathlib import Path

        from orchestrator.core.benchmarking.solver_registry import (
            _require_string,
        )

        with self.assertRaises(ValueError) as ctx:
            _require_string({}, "key", Path("test.json"))
        self.assertIn("key", str(ctx.exception))
        self.assertIn("test.json", str(ctx.exception))

    def test_require_string_rejects_empty_string(self) -> None:
        from pathlib import Path

        from orchestrator.core.benchmarking.solver_registry import (
            _require_string,
        )

        with self.assertRaises(ValueError) as ctx:
            _require_string({"key": ""}, "key", Path("test.json"))
        self.assertIn("key", str(ctx.exception))

    def test_require_dict_rejects_non_dict(self) -> None:
        from pathlib import Path

        from orchestrator.core.benchmarking.solver_registry import (
            _require_dict,
        )

        with self.assertRaises(ValueError) as ctx:
            _require_dict({"key": "not_a_dict"}, "key", Path("test.json"))
        self.assertIn("key", str(ctx.exception))
        self.assertIn("JSON object", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
