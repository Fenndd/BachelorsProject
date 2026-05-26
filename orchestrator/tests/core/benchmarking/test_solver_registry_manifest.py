"""Tests for solver registry manifest discovery and validation.

Verifies that every manifest under cpp/bench/*/solvers/*.json is valid,
has a unique solver_id, and produces a working descriptor. Also checks
that poselib_native and generated_absolute_pose manifests carry the
expected fields.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from orchestrator.core.benchmarking.solver_registry import (
    SolverBenchmarkDescriptor,
    default_solver_descriptor,
    get_solver_descriptor,
    list_solver_descriptors,
)
from orchestrator.paths import get_project_paths


def _repo_root() -> Path:
    return get_project_paths().repo_root


def _all_manifest_paths() -> list[Path]:
    root = _repo_root()
    manifest_dir = root / "cpp" / "bench"
    return sorted(manifest_dir.glob("*/solvers/*.json"))


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TestManifestDiscovery:
    def test_at_least_one_manifest_exists(self) -> None:
        manifests = _all_manifest_paths()
        assert len(manifests) >= 1, "No solver manifests found"

    def test_lambdatwist_manifest_exists(self) -> None:
        paths = _all_manifest_paths()
        names = {p.stem for p in paths}
        assert "lambdatwist_p3p" in names, "lambdatwist_p3p manifest missing"

    def test_poselib_p3p_manifest_exists(self) -> None:
        paths = _all_manifest_paths()
        names = {p.stem for p in paths}
        assert "poselib_p3p" in names, "poselib_p3p manifest missing"


class TestEveryManifestValidJson:
    def test_every_manifest_is_valid_json_object(self) -> None:
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            assert isinstance(data, dict), f"{path} is not a JSON object"


class TestEveryManifestHasSolverId:
    def test_every_manifest_has_solver_id(self) -> None:
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            sid = data.get("solver_id")
            assert isinstance(sid, str) and sid, (
                f"{path} missing or invalid solver_id"
            )


class TestAllSolverIdsUnique:
    def test_all_solver_ids_are_unique(self) -> None:
        seen: dict[str, Path] = {}
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            sid = data["solver_id"]
            assert sid not in seen, (
                f"Duplicate solver_id {sid!r} in {path} (already in {seen[sid]})"
            )
            seen[sid] = path


class TestEverySolverIdRetrievable:
    def test_every_solver_id_retrievable_via_get_solver_descriptor(self) -> None:
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            sid = data["solver_id"]
            desc = get_solver_descriptor(sid)
            assert isinstance(desc, SolverBenchmarkDescriptor)
            assert desc.solver_id == sid


class TestPoselibNativeManifests:
    def test_poselib_manifests_have_correct_backend(self) -> None:
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            if data.get("family") != "poselib_native":
                continue
            assert data.get("benchmark_backend") == "poselib_native", (
                f"{path} should have benchmark_backend=poselib_native"
            )

    def test_poselib_manifests_have_benchmark_target(self) -> None:
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            if data.get("family") != "poselib_native":
                continue
            bt = data.get("benchmark_target")
            assert bt == "poselib_solver_benchmark", (
                f"{path} unexpected benchmark_target: {bt!r}"
            )

    def test_poselib_manifests_have_solver_key(self) -> None:
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            if data.get("family") != "poselib_native":
                continue
            key = data.get("benchmark_solver_key")
            assert isinstance(key, str) and key, (
                f"{path} missing or empty benchmark_solver_key"
            )

    def test_poselib_manifests_default_target_file_exists(self) -> None:
        root = _repo_root()
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            if data.get("family") != "poselib_native":
                continue
            dtf = data.get("default_target_file")
            assert isinstance(dtf, str) and dtf, (
                f"{path} missing default_target_file"
            )
            target = root / dtf
            assert target.exists(), (
                f"{path} default_target_file does not exist: {dtf}"
            )

    def test_poselib_manifests_default_allowed_files_exist(self) -> None:
        root = _repo_root()
        for path in _all_manifest_paths():
            data = _load_manifest(path)
            if data.get("family") != "poselib_native":
                continue
            daf = data.get("default_allowed_files")
            assert isinstance(daf, list) and daf, (
                f"{path} missing or empty default_allowed_files"
            )
            for idx, file_path in enumerate(daf):
                assert isinstance(file_path, str) and file_path, (
                    f"{path} default_allowed_files[{idx}] is not a non-empty string"
                )
                target = root / file_path
                assert target.exists(), (
                    f"{path} default_allowed_files[{idx}] does not exist: {file_path}"
                )


class TestGeneratedAbsolutePoseManifest:
    def test_lambdatwist_has_runner_mode(self) -> None:
        path = _repo_root() / "cpp/bench/absolute_pose/solvers/lambdatwist_p3p.json"
        data = _load_manifest(path)
        assert data.get("runner_mode") == "generated_absolute_pose"

    def test_lambdatwist_descriptor_has_adapter_validator(self) -> None:
        desc = get_solver_descriptor("lambdatwist_p3p")
        assert desc.adapter_validator_target is not None, (
            "lambdatwist_p3p descriptor missing adapter_validator_target"
        )
        assert desc.adapter_validator_target == "absolute_pose_lambdatwist_adapter_validator"

    def test_lambdatwist_runtime_unit_is_ns(self) -> None:
        desc = get_solver_descriptor("lambdatwist_p3p")
        assert desc.runtime_unit == "ns"


class TestListIncludesKeySolvers:
    def test_list_includes_lambdatwist_p3p(self) -> None:
        ids = {d.solver_id for d in list_solver_descriptors()}
        assert "lambdatwist_p3p" in ids

    def test_list_includes_poselib_p3p(self) -> None:
        ids = {d.solver_id for d in list_solver_descriptors()}
        assert "poselib_p3p" in ids

    def test_list_includes_poselib_relpose_5pt(self) -> None:
        ids = {d.solver_id for d in list_solver_descriptors()}
        assert "poselib_relpose_5pt" in ids

    def test_list_includes_poselib_homography_4pt(self) -> None:
        ids = {d.solver_id for d in list_solver_descriptors()}
        assert "poselib_homography_4pt" in ids

    def test_list_includes_poselib_gp3p(self) -> None:
        ids = {d.solver_id for d in list_solver_descriptors()}
        assert "poselib_gp3p" in ids
