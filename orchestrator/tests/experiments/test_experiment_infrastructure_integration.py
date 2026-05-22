from __future__ import annotations

import sys
from pathlib import Path

from orchestrator import paths as project_paths
from orchestrator.experiments import experiment_environment as env
from orchestrator.experiments import iteration_runner
from orchestrator.experiments import run_experiment


def test_experiment_environment_roots_use_canonical_project_paths() -> None:
    paths = project_paths.get_project_paths()

    assert env.REPO_ROOT == paths.repo_root
    assert env.RESULTS_ROOT == paths.results
    assert env.EXPERIMENTS_ROOT == paths.result_experiments
    assert env.WORKSPACE_ROOT == paths.workspace


def test_run_stage_preserves_return_shape_and_stage_log(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "results" / "experiments" / "1"
    command = [
        sys.executable,
        "-c",
        "import sys; print('stage stdout'); print('stage stderr', file=sys.stderr)",
    ]

    result = iteration_runner._run_stage(
        experiment_dir,
        7,
        "variant_a",
        3,
        "generate_candidate",
        command,
    )

    assert set(result) == {"exit_code", "stdout", "stderr", "duration_seconds"}
    assert result["exit_code"] == 0
    assert "stage stdout" in result["stdout"]
    assert "stage stderr" in result["stderr"]
    assert isinstance(result["duration_seconds"], float)

    log_path = experiment_dir / "logs" / "iteration_007_generate_candidate.log"
    assert log_path.exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert "GLOBAL_ITERATION: 7" in log_text
    assert "VARIANT_ID: variant_a" in log_text
    assert "VARIANT_ITERATION: 3" in log_text
    assert "STAGE: generate_candidate" in log_text
    assert "EXIT_CODE: 0" in log_text
    assert "stage stdout" in log_text
    assert "stage stderr" in log_text


def test_experiment_json_file_object_reads_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "payload.json"
    path.write_text('\ufeff{"answer": 42}\n', encoding="utf-8")

    assert env._read_json_file_object(path, "payload") == {"answer": 42}


def test_parse_candidate_run_dir_from_generation_stdout(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    original_repo_root = run_experiment.REPO_ROOT
    monkeypatch.setattr(run_experiment, "REPO_ROOT", tmp_path)
    candidate_run = tmp_path / "results" / "runs" / "candidate_001"
    candidate_run.mkdir(parents=True)
    env._write_json(candidate_run / "candidate.json", {"summary": "ok"})

    try:
        stdout = f"before\nCANDIDATE_RUN_DIR={candidate_run}\nafter\n"
        assert run_experiment._parse_candidate_run_dir(stdout) == str(candidate_run)
    finally:
        monkeypatch.setattr(run_experiment, "REPO_ROOT", original_repo_root)
