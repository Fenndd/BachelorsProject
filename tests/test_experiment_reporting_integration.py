from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.experiments import run_experiment
from orchestrator.experiments.experiment_config import (
    ExperimentConfigError,
    load_experiment_config,
)


TARGET_FILE = "cpp/external/lambdatwist/p3p.cc"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _benchmark_payload() -> dict[str, Any]:
    return {
        "benchmark": {
            "family": "absolute_pose_solvers",
            "solver": "lambdatwist_p3p",
            "parse_success": True,
            "parsed_success_rate": 1.0,
            "parsed_mean_best_reprojection_error": 1.0e-12,
            "parsed_max_best_reprojection_error": 2.0e-12,
            "parsed_runtime_ns_per_case_median": 1000.0,
            "parsed_correctness_passed": True,
        }
    }


def _base_config_payload(
    root: Path,
    *,
    reporting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "experiment_name": "reporting integration test",
        "target_file": TARGET_FILE,
        "pipeline": {
            "generate_candidate": True,
            "materialize_candidate": True,
            "verify_candidate": True,
        },
        "candidate_generation": {"max_source_chars": 1000},
        "candidate_format": {
            "type": "line_range_edits",
            "source_presentation": "line_numbered",
            "require_original_verification": True,
            "allow_exact_search_fallback": True,
        },
        "closed_loop": {"enabled": True},
        "selection": {
            "enabled": False,
            "baseline_run_dir": str(root / "results" / "runs" / "baseline"),
        },
        "llm_config": "configs/llm_mock_candidate.json",
        "iterations": 1,
    }
    if reporting is not None:
        payload["reporting"] = reporting
    return payload


def _write_config(root: Path, payload: dict[str, Any]) -> Path:
    config_path = root / "config.json"
    _write_json(config_path, payload)
    return config_path


def _load_config(root: Path, payload: dict[str, Any]):
    return load_experiment_config(_write_config(root, payload))


def _create_repo_layout(root: Path) -> None:
    target_path = root / TARGET_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("baseline\n", encoding="utf-8")
    _write_json(root / "results" / "runs" / "baseline" / "metrics.json", _benchmark_payload())


def _patch_runner_roots(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(run_experiment, "REPO_ROOT", root)
    monkeypatch.setattr(run_experiment, "RESULTS_ROOT", root / "results")
    monkeypatch.setattr(
        run_experiment,
        "EXPERIMENTS_ROOT",
        root / "results" / "experiments",
    )
    monkeypatch.setattr(run_experiment, "WORKSPACE_ROOT", root / "workspace")
    monkeypatch.setattr(
        run_experiment,
        "_resolve_variant_llm_config",
        lambda variant: {"provider": "mock", "model": "mock"},
    )
    monkeypatch.setattr(run_experiment, "run_final_validation", _fake_final_validation)


def _fake_final_validation(**kwargs: Any) -> Path:
    experiment_dir = Path(kwargs["experiment_dir"])
    report_path = experiment_dir / "val" / "final_validation_report.json"
    _write_json(
        report_path,
        {
            "schema_version": "final_validation.v1",
            "enabled": kwargs.get("enabled", True),
            "status": "completed",
            "benchmark_repetitions": kwargs.get("benchmark_repetitions", 5),
            "baseline": {"runs": [], "summary": {"successful_runs": 1, "failed_runs": 0, "median_runtime_ns_per_case": 100.0, "all_correctness_passed": True}},
            "final": {"runs": [], "summary": {"successful_runs": 1, "failed_runs": 0, "median_runtime_ns_per_case": 100.0, "all_correctness_passed": True}},
            "comparison": {
                "median_speedup": 1.0,
                "median_runtime_reduction_percent": 0.0,
            },
        },
    )
    return report_path


def _patch_noop_closed_loop_stage(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    def fake_run_stage(
        experiment_dir: Path,
        global_iteration: int,
        variant_id: str,
        variant_iteration: int,
        stage_name: str,
        command: list[str],
    ) -> dict[str, Any]:
        if stage_name != "generate_candidate":
            raise AssertionError(f"Unexpected stage for no-op candidate: {stage_name}")
        candidate_dir = root / "results" / "runs" / f"candidate_{variant_iteration}"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        _write_json(candidate_dir / "status.json", {"overall_status": "success"})
        _write_json(
            candidate_dir / "candidate.json",
            {
                "candidate_type": "line_range_edits",
                "summary": "no-op candidate",
                "rationale": "test",
                "risk_level": "low",
                "expected_effect": "none",
                "target_files": [TARGET_FILE],
                "edits": [],
                "requires_manual_review": False,
            },
        )
        return {
            "exit_code": 0,
            "stdout": f"CANDIDATE_RUN_DIR={candidate_dir}\n",
            "stderr": "",
            "duration_seconds": 0.1,
        }

    monkeypatch.setattr(run_experiment, "_run_stage", fake_run_stage)


def _run_noop_closed_loop_experiment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    reporting: dict[str, Any] | None,
) -> Path:
    root = tmp_path / "repo"
    _create_repo_layout(root)
    _patch_runner_roots(monkeypatch, root)
    _patch_noop_closed_loop_stage(monkeypatch, root)
    payload = _base_config_payload(root, reporting=reporting)
    config = load_experiment_config(_write_config(root, payload))

    exit_code = run_experiment._run_experiment(config, payload)

    assert exit_code == 0
    return next((root / "results" / "experiments").iterdir())


def test_reporting_config_defaults_when_block_absent(tmp_path: Path) -> None:
    config = _load_config(tmp_path, _base_config_payload(tmp_path))

    assert config.reporting.enabled is False
    assert config.reporting.formats == ["html", "pdf"]
    assert config.reporting.renderer == "auto"
    assert config.reporting.fail_on_error is False


def test_final_validation_runs_after_finalization_before_reporting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    _create_repo_layout(root)
    _patch_runner_roots(monkeypatch, root)
    _patch_noop_closed_loop_stage(monkeypatch, root)
    payload = _base_config_payload(root, reporting=None)
    config = load_experiment_config(_write_config(root, payload))
    call_order: list[str] = []
    metadata_final_order: list[list[str]] = []
    original_finalize = run_experiment.finalize_closed_loop_artifacts
    original_reporting = run_experiment._run_final_reporting
    original_write_metadata = run_experiment._write_experiment_metadata

    def wrapped_finalize(*args: Any, **kwargs: Any):
        call_order.append("finalize")
        return original_finalize(*args, **kwargs)

    def wrapped_validation(**kwargs: Any) -> Path:
        call_order.append("validation")
        return _fake_final_validation(**kwargs)

    def wrapped_reporting(*args: Any, **kwargs: Any) -> dict[str, Any]:
        call_order.append("reporting")
        return original_reporting(*args, **kwargs)

    def wrapped_write_metadata(*args: Any, **kwargs: Any) -> Path:
        finished_at = kwargs.get("finished_at") if kwargs else None
        if finished_at is None and len(args) >= 3:
            finished_at = args[2]
        if finished_at is not None:
            metadata_final_order.append(list(call_order))
        return original_write_metadata(*args, **kwargs)

    monkeypatch.setattr(run_experiment, "finalize_closed_loop_artifacts", wrapped_finalize)
    monkeypatch.setattr(run_experiment, "run_final_validation", wrapped_validation)
    monkeypatch.setattr(run_experiment, "_run_final_reporting", wrapped_reporting)
    monkeypatch.setattr(run_experiment, "_write_experiment_metadata", wrapped_write_metadata)

    exit_code = run_experiment._run_experiment(config, payload)

    assert exit_code == 0
    assert call_order == ["finalize", "validation", "reporting", "reporting"]
    assert metadata_final_order == [["finalize", "validation", "reporting"]]
    experiment_dir = next((root / "results" / "experiments").iterdir())
    status = json.loads((experiment_dir / "experiment_status.json").read_text(encoding="utf-8"))
    metadata = json.loads((experiment_dir / "experiment_metadata.json").read_text(encoding="utf-8"))
    assert metadata["finished_at"] == status["finished_at"]
    assert metadata["total_duration_seconds"] is not None
    assert f"Finished at: {status['finished_at']}" in (experiment_dir / "summary.txt").read_text(
        encoding="utf-8"
    )
    assert status["closed_loop"]["final_validation_report_path"].endswith(
        "val/final_validation_report.json"
    )


def test_closed_loop_status_warns_when_final_validation_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    _create_repo_layout(root)
    _patch_runner_roots(monkeypatch, root)
    _patch_noop_closed_loop_stage(monkeypatch, root)

    def incomplete_validation(**kwargs: Any) -> Path:
        experiment_dir = Path(kwargs["experiment_dir"])
        report_path = experiment_dir / "val" / "final_validation_report.json"
        _write_json(
            report_path,
            {
                "schema_version": "final_validation.v1",
                "enabled": True,
                "status": "incomplete",
                "benchmark_repetitions": 5,
                "baseline": {"runs": [], "summary": {"successful_runs": 0, "failed_runs": 0}},
                "final": {"runs": [], "summary": {"successful_runs": 0, "failed_runs": 0}},
                "comparison": {
                    "median_speedup": None,
                    "median_runtime_reduction_percent": None,
                },
            },
        )
        return report_path

    monkeypatch.setattr(run_experiment, "run_final_validation", incomplete_validation)
    payload = _base_config_payload(root, reporting=None)
    config = load_experiment_config(_write_config(root, payload))

    exit_code = run_experiment._run_experiment(config, payload)

    assert exit_code == 0
    experiment_dir = next((root / "results" / "experiments").iterdir())
    status = json.loads((experiment_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert status["overall_status"] == "completed_with_warnings"


def test_valid_reporting_config_loads_and_deduplicates_formats(tmp_path: Path) -> None:
    config = _load_config(
        tmp_path,
        _base_config_payload(
            tmp_path,
            reporting={
                "enabled": True,
                "formats": ["html", "pdf", "html"],
                "renderer": "playwright",
                "fail_on_error": True,
            },
        ),
    )

    assert config.reporting.enabled is True
    assert config.reporting.formats == ["html", "pdf"]
    assert config.reporting.renderer == "playwright"
    assert config.reporting.fail_on_error is True


@pytest.mark.parametrize(
    "reporting, expected",
    [
        (
            {
                "enabled": True,
                "formats": ["docx"],
                "renderer": "auto",
                "fail_on_error": False,
            },
            "formats",
        ),
        (
            {
                "enabled": True,
                "formats": ["html"],
                "renderer": "wkhtmltopdf",
                "fail_on_error": False,
            },
            "renderer",
        ),
        (
            {
                "enabled": "true",
                "formats": ["html"],
                "renderer": "auto",
                "fail_on_error": False,
            },
            "enabled",
        ),
        (
            {
                "enabled": True,
                "formats": ["html"],
                "renderer": "auto",
                "fail_on_error": "false",
            },
            "fail_on_error",
        ),
    ],
)
def test_invalid_reporting_config_raises(
    tmp_path: Path,
    reporting: dict[str, Any],
    expected: str,
) -> None:
    with pytest.raises(ExperimentConfigError, match=expected):
        _load_config(tmp_path, _base_config_payload(tmp_path, reporting=reporting))


def test_enabled_reporting_runs_after_final_closed_loop_artifacts_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Path, tuple[str, ...], str]] = []

    def fake_generate_basic_report(
        experiment_dir: Path,
        *,
        formats: tuple[str, ...],
        renderer: str,
    ) -> dict[str, Path]:
        assert (experiment_dir / "closed_loop_summary.json").is_file()
        assert (experiment_dir / "closed_loop_iterations.jsonl").is_file()
        assert (experiment_dir / "final_optimized_source").is_dir()
        assert (experiment_dir / "final_optimized_source.diff").is_file()
        assert (experiment_dir / "closed_loop_selection_report.json").is_file()
        report_dir = experiment_dir / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_data = report_dir / "report_data.json"
        html = report_dir / "report.html"
        report_data.write_text("{}\n", encoding="utf-8")
        html.write_text("<html></html>", encoding="utf-8")
        calls.append((experiment_dir, formats, renderer))
        return {"report_data": report_data, "html": html}

    monkeypatch.setattr(
        run_experiment,
        "generate_basic_report",
        fake_generate_basic_report,
    )

    experiment_dir = _run_noop_closed_loop_experiment(
        tmp_path,
        monkeypatch,
        reporting={
            "enabled": True,
            "formats": ["html"],
            "renderer": "auto",
            "fail_on_error": False,
        },
    )

    assert calls == [
        (experiment_dir, ("html",), "auto"),
        (experiment_dir, ("html",), "auto"),
    ]
    status = json.loads((experiment_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert status["reporting"]["status"] == "completed"
    assert status["reporting"]["report_data_path"].endswith("report/report_data.json")
    assert status["reporting"]["report_html_path"].endswith("report/report.html")
    assert status["reporting"]["report_pdf_path"] is None
    summary = (experiment_dir / "summary.txt").read_text(encoding="utf-8")
    assert "Reporting:" in summary
    assert "status: completed" in summary


def test_final_report_includes_final_experiment_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    experiment_dir = _run_noop_closed_loop_experiment(
        tmp_path,
        monkeypatch,
        reporting={
            "enabled": True,
            "formats": ["html"],
            "renderer": "auto",
            "fail_on_error": False,
        },
    )

    status = json.loads((experiment_dir / "experiment_status.json").read_text(encoding="utf-8"))
    report_data = json.loads(
        (experiment_dir / "report" / "report_data.json").read_text(encoding="utf-8")
    )
    html = (experiment_dir / "report" / "report.html").read_text(encoding="utf-8")

    assert experiment_dir.name.isdigit()
    assert experiment_dir == experiment_dir.parent / status["experiment_id"]
    assert status["experiment_name"] == "reporting integration test"
    assert report_data["experiment"]["experiment_id"] == status["experiment_id"]
    assert report_data["experiment"]["experiment_name"] == "reporting integration test"
    assert report_data["experiment_metadata"]["finished_at"] == status["finished_at"]
    assert report_data["experiment_metadata"]["total_duration_seconds"] is not None
    assert status["finished_at"] in html


def test_disabled_reporting_does_not_call_generator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generate_basic_report(*args: object, **kwargs: object) -> dict[str, Path]:
        raise AssertionError("reporting generator should not be called")

    monkeypatch.setattr(
        run_experiment,
        "generate_basic_report",
        fail_generate_basic_report,
    )

    experiment_dir = _run_noop_closed_loop_experiment(
        tmp_path,
        monkeypatch,
        reporting=None,
    )

    status = json.loads((experiment_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert status["reporting"] == {
        "enabled": False,
        "status": "disabled",
        "formats": ["html", "pdf"],
        "renderer": "auto",
        "report_data_path": None,
        "report_html_path": None,
        "report_pdf_path": None,
        "error": None,
    }
    assert "Reporting:\n  enabled: false" in (
        experiment_dir / "summary.txt"
    ).read_text(encoding="utf-8")


def test_reporting_failure_is_recorded_when_not_fail_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generate_basic_report(*args: object, **kwargs: object) -> dict[str, Path]:
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(
        run_experiment,
        "generate_basic_report",
        fail_generate_basic_report,
    )

    experiment_dir = _run_noop_closed_loop_experiment(
        tmp_path,
        monkeypatch,
        reporting={
            "enabled": True,
            "formats": ["html", "pdf"],
            "renderer": "auto",
            "fail_on_error": False,
        },
    )

    status = json.loads((experiment_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert status["reporting"]["status"] == "failed"
    assert status["reporting"]["error"] == "renderer unavailable"
    assert "status: failed" in (experiment_dir / "summary.txt").read_text(
        encoding="utf-8"
    )


def test_reporting_failure_propagates_when_fail_on_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generate_basic_report(*args: object, **kwargs: object) -> dict[str, Path]:
        raise RuntimeError("hard reporting failure")

    monkeypatch.setattr(
        run_experiment,
        "generate_basic_report",
        fail_generate_basic_report,
    )

    with pytest.raises(RuntimeError, match="hard reporting failure"):
        _run_noop_closed_loop_experiment(
            tmp_path,
            monkeypatch,
            reporting={
                "enabled": True,
                "formats": ["html"],
                "renderer": "auto",
                "fail_on_error": True,
            },
        )


def test_reporting_integration_preserves_closed_loop_inputs_and_writes_under_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_generate_basic_report(
        experiment_dir: Path,
        *,
        formats: tuple[str, ...],
        renderer: str,
    ) -> dict[str, Path]:
        report_dir = experiment_dir / "report"
        plots_dir = report_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        report_data = report_dir / "report_data.json"
        html = report_dir / "report.html"
        plot = plots_dir / "runtime_progress.svg"
        report_data.write_text("{}\n", encoding="utf-8")
        html.write_text("<html></html>", encoding="utf-8")
        plot.write_text("<svg></svg>", encoding="utf-8")
        return {"report_data": report_data, "html": html}

    monkeypatch.setattr(
        run_experiment,
        "generate_basic_report",
        fake_generate_basic_report,
    )

    experiment_dir = _run_noop_closed_loop_experiment(
        tmp_path,
        monkeypatch,
        reporting={
            "enabled": True,
            "formats": ["html"],
            "renderer": "auto",
            "fail_on_error": False,
        },
    )
    summary_path = experiment_dir / "closed_loop_summary.json"
    iterations_path = experiment_dir / "closed_loop_iterations.jsonl"
    summary_before = summary_path.read_text(encoding="utf-8")
    iterations_before = iterations_path.read_text(encoding="utf-8")

    # Re-run only the reporting integration helper to verify it does not touch
    # persisted closed-loop inputs.
    reporting_status = run_experiment._run_final_reporting(experiment_dir, _load_config(
        tmp_path / "config_root",
        _base_config_payload(
            tmp_path / "config_root",
            reporting={
                "enabled": True,
                "formats": ["html"],
                "renderer": "auto",
                "fail_on_error": False,
            },
        ),
    ))

    assert reporting_status["status"] == "completed"
    assert summary_path.read_text(encoding="utf-8") == summary_before
    assert iterations_path.read_text(encoding="utf-8") == iterations_before
    for path in (experiment_dir / "report").rglob("*"):
        if path.is_file():
            assert path.relative_to(experiment_dir).parts[0] == "report"
