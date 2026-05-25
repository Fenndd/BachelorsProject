"""Tests for parallel experiment storage isolation invariants.

Verifies that two experiments with different IDs do not mix paths or state
in results/runs, workspace/candidates, workspace/experiments, or the
current_best_state and closed_loop_iterations artifacts.

This test does not run real experiments or require C++ builds. It exercises
ClosedLoopPaths, CurrentBestState, and the iteration-path helpers to verify
that storage-scoped identifiers keep experiments fully isolated.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

import json
from datetime import datetime
from pathlib import Path

from orchestrator.experiments.closed_loop_state import (
    ClosedLoopIterationRecord,
    ClosedLoopPaths,
    CurrentBestState,
    IterationStatus,
    append_closed_loop_iteration_record,
    read_current_best_state,
    to_plain_dict,
    write_current_best_state,
)
from orchestrator.experiments.iteration_runner import format_iteration_dir


_EXP_1 = "exp_001"
_EXP_2 = "exp_002"

_TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


def _make_state(experiment_id: str, ws_root: Path, results_root: Path) -> CurrentBestState:
    cbp = ClosedLoopPaths.from_roots(ws_root, results_root, experiment_id)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return CurrentBestState(
        experiment_id=experiment_id,
        target_file=_TARGET_FILE,
        original_baseline_run_dir=results_root / "runs" / "baseline_dir",
        original_baseline_metrics_path=results_root / "runs" / "baseline_dir" / "metrics.json",
        current_best_iteration=0,
        current_best_is_baseline=True,
        current_best_source_dir=cbp.current_best_source_dir,
        current_best_run_dir=results_root / "runs" / "baseline_dir",
        current_best_metrics_path=results_root / "runs" / "baseline_dir" / "metrics.json",
        accepted_improvements=0,
        updated_at=now,
    )


def _make_record(experiment_id: str, iteration: int) -> ClosedLoopIterationRecord:
    return ClosedLoopIterationRecord(
        experiment_id=experiment_id,
        iteration=iteration,
        status=IterationStatus.ACCEPTED_IMPROVEMENT,
        base_source_kind="baseline",
        reference_best_iteration_before=0,
    )


class TestExperimentIdIsolation:
    def test_different_experiment_ids(self) -> None:
        assert _EXP_1 != _EXP_2

    def test_candidate_runs_root_isolation(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        paths1 = ClosedLoopPaths.from_roots(ws, results, _EXP_1)
        paths2 = ClosedLoopPaths.from_roots(ws, results, _EXP_2)

        run1 = paths1.candidate_runs_root / format_iteration_dir(1)
        run2 = paths2.candidate_runs_root / format_iteration_dir(1)

        assert str(_EXP_1) in str(run1)
        assert str(_EXP_2) in str(run2)
        assert _EXP_1 not in str(run2.parts[-1])
        assert _EXP_2 not in str(run1.parts[-1])
        assert str(run1) != str(run2)

    def test_candidate_workspaces_root_isolation(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        paths1 = ClosedLoopPaths.from_roots(ws, results, _EXP_1)
        paths2 = ClosedLoopPaths.from_roots(ws, results, _EXP_2)

        w1 = paths1.candidate_workspaces_root / format_iteration_dir(1)
        w2 = paths2.candidate_workspaces_root / format_iteration_dir(1)

        assert str(_EXP_1) in str(w1)
        assert str(_EXP_2) in str(w2)
        assert str(w1) != str(w2)

    def test_current_best_source_dir_isolation(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        paths1 = ClosedLoopPaths.from_roots(ws, results, _EXP_1)
        paths2 = ClosedLoopPaths.from_roots(ws, results, _EXP_2)

        assert str(_EXP_1) in str(paths1.current_best_source_dir)
        assert str(_EXP_2) in str(paths2.current_best_source_dir)
        assert str(paths1.current_best_source_dir) != str(paths2.current_best_source_dir)


class TestStateNoCrossContamination:
    def test_current_best_state_exp1_does_not_contain_exp2(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        cbp1 = ClosedLoopPaths.from_roots(ws, results, _EXP_1)

        state1 = _make_state(_EXP_1, ws, results)
        write_current_best_state(cbp1.current_best_state_path, state1)

        raw = json.loads(cbp1.current_best_state_path.read_text(encoding="utf-8"))
        raw_text = json.dumps(raw)

        assert _EXP_2 not in raw_text
        assert raw.get("experiment_id") == _EXP_1

    def test_current_best_state_exp2_does_not_contain_exp1(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        cbp2 = ClosedLoopPaths.from_roots(ws, results, _EXP_2)

        state2 = _make_state(_EXP_2, ws, results)
        write_current_best_state(cbp2.current_best_state_path, state2)

        raw = json.loads(cbp2.current_best_state_path.read_text(encoding="utf-8"))
        raw_text = json.dumps(raw)

        assert _EXP_1 not in raw_text
        assert raw.get("experiment_id") == _EXP_2

    def test_current_best_state_roundtrip_preserves_experiment_id(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        cbp = ClosedLoopPaths.from_roots(ws, results, _EXP_1)

        state = _make_state(_EXP_1, ws, results)
        write_current_best_state(cbp.current_best_state_path, state)

        loaded = read_current_best_state(cbp.current_best_state_path)
        assert loaded.experiment_id == _EXP_1
        assert _EXP_2 not in loaded.experiment_id


class TestIterationsNoCrossContamination:
    def test_closed_loop_iterations_exp1_does_not_contain_exp2(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        cbp1 = ClosedLoopPaths.from_roots(ws, results, _EXP_1)

        record1 = _make_record(_EXP_1, 1)
        append_closed_loop_iteration_record(cbp1.closed_loop_iterations_path, record1)

        raw_text = cbp1.closed_loop_iterations_path.read_text(encoding="utf-8")
        assert "experiment_id" in raw_text
        assert _EXP_1 in raw_text
        assert _EXP_2 not in raw_text

    def test_closed_loop_iterations_exp2_does_not_contain_exp1(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        cbp2 = ClosedLoopPaths.from_roots(ws, results, _EXP_2)

        record2 = _make_record(_EXP_2, 1)
        append_closed_loop_iteration_record(cbp2.closed_loop_iterations_path, record2)

        raw_text = cbp2.closed_loop_iterations_path.read_text(encoding="utf-8")
        assert _EXP_2 in raw_text
        assert _EXP_1 not in raw_text

    def test_both_experiments_have_separate_iteration_files(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        results = tmp_path / "results"
        cbp1 = ClosedLoopPaths.from_roots(ws, results, _EXP_1)
        cbp2 = ClosedLoopPaths.from_roots(ws, results, _EXP_2)

        append_closed_loop_iteration_record(cbp1.closed_loop_iterations_path, _make_record(_EXP_1, 1))
        append_closed_loop_iteration_record(cbp2.closed_loop_iterations_path, _make_record(_EXP_2, 1))

        assert cbp1.closed_loop_iterations_path != cbp2.closed_loop_iterations_path
        assert cbp1.closed_loop_iterations_path.exists()
        assert cbp2.closed_loop_iterations_path.exists()

        text1 = cbp1.closed_loop_iterations_path.read_text(encoding="utf-8")
        text2 = cbp2.closed_loop_iterations_path.read_text(encoding="utf-8")
        assert _EXP_1 in text1
        assert _EXP_2 not in text1
        assert _EXP_2 in text2
        assert _EXP_1 not in text2
