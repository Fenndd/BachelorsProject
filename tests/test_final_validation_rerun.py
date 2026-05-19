from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.control import final_validation_rerun


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_rerun_final_validation_updates_artifacts_without_iterations(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    experiment_dir = repo_root / "results" / "experiments" / "exp_001"
    (experiment_dir / "final_optimized_source" / "cpp").mkdir(parents=True)
    iterations_path = experiment_dir / "closed_loop_iterations.jsonl"
    iterations_path.write_text('{"iteration": 1}\n', encoding="utf-8")
    _write_json(
        experiment_dir / "experiment_config_effective.json",
        {"final_validation": {"enabled": True, "benchmark_repetitions": 3}},
    )
    _write_json(
        experiment_dir / "closed_loop_summary.json",
        {
            "experiment_id": "exp_001",
            "target_file": "cpp/external/lambdatwist/p3p.cc",
            "final_best_iteration": 1,
            "final_optimized_source_dir": "results/experiments/exp_001/final_optimized_source",
            "final_optimized_source_diff_path": "results/experiments/exp_001/final_optimized_source.diff",
            "status_counts": {},
        },
    )
    _write_json(
        experiment_dir / "experiment_status.json",
        {
            "experiment_id": "exp_001",
            "overall_status": "completed_with_warnings",
            "closed_loop": {"enabled": True},
        },
    )
    calls: list[tuple[str, Any]] = []

    def fake_run_final_validation(**kwargs: Any) -> Path:
        calls.append(("validation", kwargs))
        assert kwargs["baseline_source_dir"] == repo_root
        assert kwargs["final_source_dir"] == experiment_dir / "final_optimized_source"
        assert kwargs["enabled"] is True
        assert kwargs["benchmark_repetitions"] == 3
        report_path = experiment_dir / "val" / "final_validation_report.json"
        _write_json(
            report_path,
            {
                "enabled": True,
                "status": "completed",
                "benchmark_repetitions": 3,
                "baseline": {"summary": {"median_runtime_ns_per_problem": 100.0}},
                "final": {"summary": {"median_runtime_ns_per_problem": 80.0}},
                "comparison": {
                    "median_speedup": 1.25,
                    "median_runtime_reduction_percent": 20.0,
                },
            },
        )
        return report_path

    def fake_generate_basic_report(experiment_dir_arg: Path, *, formats: tuple[str, ...], renderer: str = "auto") -> dict[str, Path]:
        calls.append(("report", (experiment_dir_arg, formats, renderer)))
        assert formats == ("html",)
        report_dir = experiment_dir_arg / "report"
        _write_json(report_dir / "report_data.json", {"ok": True})
        html_path = report_dir / "report.html"
        html_path.write_text("<html>refreshed</html>\n", encoding="utf-8")
        return {"report_data": report_dir / "report_data.json", "html": html_path}

    monkeypatch.setattr(final_validation_rerun, "run_final_validation", fake_run_final_validation)
    monkeypatch.setattr(final_validation_rerun, "generate_basic_report", fake_generate_basic_report)

    result = final_validation_rerun.rerun_final_validation_for_experiment("exp_001", repo_root)

    assert result.status == "success"
    assert [call[0] for call in calls] == ["validation", "report"]
    assert iterations_path.read_text(encoding="utf-8") == '{"iteration": 1}\n'
    summary = json.loads((experiment_dir / "closed_loop_summary.json").read_text(encoding="utf-8"))
    assert summary["final_validation_report_path"].endswith("val/final_validation_report.json")
    assert summary["final_validation_median_speedup"] == 1.25
    assert summary["final_validation_median_runtime_reduction_percent"] == 20.0
    status = json.loads((experiment_dir / "experiment_status.json").read_text(encoding="utf-8"))
    assert status["overall_status"] == "completed"
    assert status["closed_loop"]["final_validation_median_speedup"] == 1.25
    assert (experiment_dir / "report" / "report.html").read_text(encoding="utf-8") == "<html>refreshed</html>\n"


def test_rerun_final_validation_uses_snapshot_defaults_when_effective_missing(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)
    experiment_dir = repo_root / "results" / "experiments" / "exp_001"
    (experiment_dir / "final_optimized_source" / "cpp").mkdir(parents=True)
    (experiment_dir / "closed_loop_iterations.jsonl").write_text("", encoding="utf-8")
    _write_json(experiment_dir / "experiment_config_snapshot.json", {"experiment_name": "raw"})
    _write_json(experiment_dir / "closed_loop_summary.json", {"experiment_id": "exp_001"})
    seen: dict[str, Any] = {}

    def fake_run_final_validation(**kwargs: Any) -> Path:
        seen.update(kwargs)
        report_path = experiment_dir / "val" / "final_validation_report.json"
        _write_json(
            report_path,
            {
                "enabled": True,
                "status": "incomplete",
                "benchmark_repetitions": 5,
                "baseline": {"summary": {}},
                "final": {"summary": {}},
                "comparison": {"median_speedup": None, "median_runtime_reduction_percent": None},
            },
        )
        return report_path

    monkeypatch.setattr(final_validation_rerun, "run_final_validation", fake_run_final_validation)
    monkeypatch.setattr(final_validation_rerun, "generate_basic_report", lambda *args, **kwargs: {})

    result = final_validation_rerun.rerun_final_validation_for_experiment(str(experiment_dir), repo_root)

    assert result.status == "success"
    assert seen["enabled"] is True
    assert seen["benchmark_repetitions"] == 5
