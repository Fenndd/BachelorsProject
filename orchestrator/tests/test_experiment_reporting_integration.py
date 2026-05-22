from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

import json
from pathlib import Path
from typing import Any

import pytest

from orchestrator.experiments import run_experiment
from orchestrator.experiments import experiment_environment as env
from orchestrator.experiments import experiment_artifacts as artifacts
from orchestrator.experiments import experiment_planner as planner
from orchestrator.experiments import iteration_runner
from orchestrator.experiments.experiment_config import (
    ExperimentConfigError,
    load_experiment_config,
)


from orchestrator.tests.conftest import TARGET_FILE, write_json, make_benchmark_payload


def _base_config_payload(
    root: Path,
    *,
    reporting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "experiment_name": "reporting integration test",
        "target_file": TARGET_FILE,
        "baseline_run_dir": str(root / "results" / "runs" / "baseline"),
        "candidate_generation": {"max_source_chars": 1000},
        "variants": [
            {
                "variant_id": "default",
                "llm_config": "configs/llm_mock_candidate.json",
                "iterations": 1,
            }
        ],
    }
    if reporting is not None:
        payload["reporting"] = reporting
    return payload


def _write_config(root: Path, payload: dict[str, Any]) -> Path:
    config_path = root / "config.json"
    write_json(config_path, payload)
    return config_path


def _load_config(root: Path, payload: dict[str, Any]):
    return load_experiment_config(_write_config(root, payload))


def _create_repo_layout(root: Path) -> None:
    target_path = root / TARGET_FILE
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("baseline\n", encoding="utf-8")
    write_json(root / "results" / "runs" / "baseline" / "metrics.json", make_benchmark_payload())


def _patch_runner_roots(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(env, "REPO_ROOT", root)
    monkeypatch.setattr(env, "RESULTS_ROOT", root / "results")
    monkeypatch.setattr(env, "EXPERIMENTS_ROOT", root / "results" / "experiments")
    monkeypatch.setattr(env, "WORKSPACE_ROOT", root / "workspace")
    monkeypatch.setattr(
        planner,
        "_resolve_variant_llm_config",
        lambda variant: {"provider": "mock", "model": "mock"},
    )
    monkeypatch.setattr(artifacts, "run_final_selection_report", _fake_final_selection_report)


def _fake_final_selection_report(**kwargs: Any) -> Path:
    experiment_dir = Path(kwargs["experiment_dir"])
    final_best_is_baseline = kwargs.get("final_best_is_baseline", True)
    report_path = experiment_dir / "final_selection_report.json"
    write_json(
        report_path,
        {
            "report_type": "single_run_final_selection_report",
            "metric_source": "single_run_final_best_vs_original_baseline",
            "final_best_is_baseline": final_best_is_baseline,
            "status": "skipped" if final_best_is_baseline else "completed",
            "comparison": {
                "speedup": 1.0,
                "runtime_reduction_percent": 0.0,
                "baseline_runtime_ns_per_problem_median": 100.0,
                "final_runtime_ns_per_problem_median": 100.0,
                "candidate_runtime_lower": False,
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
        write_json(candidate_dir / "status.json", {"overall_status": "success"})
        write_json(
            candidate_dir / "candidate.json",
            {
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

    monkeypatch.setattr(iteration_runner, "_run_stage", fake_run_stage)


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


def test_final_selection_report_runs_after_finalization_before_reporting(
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
    original_finalize = artifacts.finalize_closed_loop_artifacts
    original_reporting = artifacts._run_final_reporting
    original_write_metadata = env._write_experiment_metadata

    def wrapped_finalize(*args: Any, **kwargs: Any):
        call_order.append("finalize")
        return original_finalize(*args, **kwargs)

    def wrapped_selection(**kwargs: Any) -> Path:
        call_order.append("validation")
        return _fake_final_selection_report(**kwargs)

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

    monkeypatch.setattr(artifacts, "finalize_closed_loop_artifacts", wrapped_finalize)
    monkeypatch.setattr(artifacts, "run_final_selection_report", wrapped_selection)
    monkeypatch.setattr(artifacts, "_run_final_reporting", wrapped_reporting)
    monkeypatch.setattr(env, "_write_experiment_metadata", wrapped_write_metadata)

    exit_code = run_experiment._run_experiment(config, payload)

    assert exit_code == 0
    assert call_order == ["finalize", "validation", "reporting"]
    assert metadata_final_order == [["finalize", "validation"]]
    experiment_dir = next((root / "results" / "experiments").iterdir())
    status = json.loads((experiment_dir / "experiment_status.json").read_text(encoding="utf-8"))
    metadata = json.loads((experiment_dir / "experiment_metadata.json").read_text(encoding="utf-8"))
    raw_config = json.loads((experiment_dir / "experiment_config_snapshot.json").read_text(encoding="utf-8"))
    effective_config = json.loads((experiment_dir / "experiment_config_effective.json").read_text(encoding="utf-8"))
    assert metadata["finished_at"] == status["finished_at"]
    assert metadata["total_duration_seconds"] is not None
    assert f"Finished at: {status['finished_at']}" in (experiment_dir / "summary.txt").read_text(
        encoding="utf-8"
    )
    assert status["closed_loop"]["final_selection_report_path"].endswith(
        "final_selection_report.json"
    )
    assert "final_validation" not in raw_config
    assert "final_validation" not in effective_config
    assert status["closed_loop"]["final_selection_speedup_vs_original_baseline"] == 1.0
    assert status["closed_loop"]["final_selection_runtime_reduction_percent"] == 0.0
    closed_loop_summary = json.loads((experiment_dir / "closed_loop_summary.json").read_text(encoding="utf-8"))
    assert closed_loop_summary["final_selection_speedup_vs_original_baseline"] == 1.0
    assert closed_loop_summary["final_selection_runtime_reduction_percent"] == 0.0


def test_closed_loop_status_warns_when_final_selection_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    _create_repo_layout(root)
    _patch_runner_roots(monkeypatch, root)
    _patch_noop_closed_loop_stage(monkeypatch, root)

    def failed_selection(**kwargs: Any) -> Path:
        experiment_dir = Path(kwargs["experiment_dir"])
        report_path = experiment_dir / "final_selection_report.json"
        write_json(
            report_path,
            {
                "report_type": "single_run_final_selection_report",
                "status": "failed",
                "failed_step": "benchmark",
                "error_message": "benchmark binary not found",
                "comparison": {
                    "speedup": None,
                    "runtime_reduction_percent": None,
                },
            },
        )
        return report_path

    monkeypatch.setattr(artifacts, "run_final_selection_report", failed_selection)
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

    monkeypatch.setattr(artifacts, "generate_basic_report",
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

    monkeypatch.setattr(artifacts, "generate_basic_report",
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

    monkeypatch.setattr(artifacts, "generate_basic_report",
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

    monkeypatch.setattr(artifacts, "generate_basic_report",
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

    monkeypatch.setattr(artifacts, "generate_basic_report",
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
    reporting_status = artifacts._run_final_reporting(experiment_dir, _load_config(
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
