"""Read-only result artifact discovery for the control layer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .project_paths import get_project_paths, resolve_project_path


ResultKind = Literal["run", "experiment"]


@dataclass(frozen=True)
class ResultArtifactMap:
    directory: Path
    summary_txt: Path | None
    metadata_json: Path | None
    status_json: Path | None
    metrics_json: Path | None
    experiment_status_json: Path | None
    experiment_config_snapshot_json: Path | None
    experiment_config_effective_json: Path | None
    closed_loop_summary_json: Path | None
    closed_loop_iterations_jsonl: Path | None
    final_optimized_source_dir: Path | None
    final_optimized_source_diff: Path | None
    report_dir: Path | None
    report_pdf: Path | None
    report_html: Path | None


@dataclass(frozen=True)
class ResultItem:
    kind: ResultKind
    name: str
    path: Path
    modified_time: float
    status: str | None
    started_at: str | None
    finished_at: str | None
    summary_text: str | None
    final_speedup_vs_baseline: float | None
    final_runtime_reduction_percent: float | None
    final_best_iteration: int | None
    accepted_improvements: int | None
    artifacts: ResultArtifactMap
    read_errors: list[str]


def _existing(path: Path) -> Path | None:
    return path if path.exists() else None


def _read_json(path: Path, read_errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        read_errors.append(f"{path.name}: {exc}")
        return None
    if not isinstance(payload, dict):
        read_errors.append(f"{path.name}: expected JSON object")
        return None
    return payload


def _read_text(path: Path, read_errors: list[str]) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        read_errors.append(f"{path.name}: {exc}")
        return None


def _float_value(payload: dict[str, Any] | None, key: str) -> float | None:
    if payload is None:
        return None
    value = payload.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _first_float(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def _int_value(payload: dict[str, Any] | None, key: str) -> int | None:
    if payload is None:
        return None
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _str_value(payload: dict[str, Any] | None, key: str) -> str | None:
    if payload is None:
        return None
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _find_report_html(report_dir: Path) -> Path | None:
    if not report_dir.is_dir():
        return None
    for name in ("report.html", "index.html"):
        candidate = report_dir / name
        if candidate.is_file():
            return candidate
    html_files = sorted(report_dir.glob("*.html"))
    return html_files[0] if html_files else None


def _find_report_pdf(report_dir: Path) -> Path | None:
    if not report_dir.is_dir():
        return None
    for name in ("report.pdf",):
        candidate = report_dir / name
        if candidate.is_file():
            return candidate
    pdf_files = sorted(report_dir.glob("*.pdf"))
    return pdf_files[0] if pdf_files else None


def _run_artifacts(path: Path) -> ResultArtifactMap:
    return ResultArtifactMap(
        directory=path,
        summary_txt=_existing(path / "summary.txt"),
        metadata_json=_existing(path / "metadata.json"),
        status_json=_existing(path / "status.json"),
        metrics_json=_existing(path / "metrics.json"),
        experiment_status_json=None,
        experiment_config_snapshot_json=None,
        experiment_config_effective_json=None,
        closed_loop_summary_json=None,
        closed_loop_iterations_jsonl=None,
        final_optimized_source_dir=None,
        final_optimized_source_diff=None,
        report_dir=None,
        report_pdf=None,
        report_html=None,
    )


def _experiment_artifacts(path: Path) -> ResultArtifactMap:
    report_dir = _existing(path / "report")
    return ResultArtifactMap(
        directory=path,
        summary_txt=_existing(path / "summary.txt"),
        metadata_json=None,
        status_json=None,
        metrics_json=None,
        experiment_status_json=_existing(path / "experiment_status.json"),
        experiment_config_snapshot_json=_existing(path / "experiment_config_snapshot.json"),
        experiment_config_effective_json=_existing(path / "experiment_config_effective.json"),
        closed_loop_summary_json=_existing(path / "closed_loop_summary.json"),
        closed_loop_iterations_jsonl=_existing(path / "closed_loop_iterations.jsonl"),
        final_optimized_source_dir=_existing(path / "final_optimized_source"),
        final_optimized_source_diff=_existing(path / "final_optimized_source.diff"),
        report_dir=report_dir,
        report_pdf=_find_report_pdf(report_dir) if report_dir is not None else None,
        report_html=_find_report_html(report_dir) if report_dir is not None else None,
    )


def _read_run_item(path: Path) -> ResultItem:
    read_errors: list[str] = []
    artifacts = _run_artifacts(path)
    metadata = _read_json(path / "metadata.json", read_errors)
    status_payload = _read_json(path / "status.json", read_errors)
    _read_json(path / "metrics.json", read_errors)
    return ResultItem(
        kind="run",
        name=path.name,
        path=path,
        modified_time=path.stat().st_mtime,
        status=_str_value(status_payload, "overall_status"),
        started_at=_str_value(metadata, "started_at"),
        finished_at=_str_value(metadata, "finished_at"),
        summary_text=_read_text(path / "summary.txt", read_errors),
        final_speedup_vs_baseline=None,
        final_runtime_reduction_percent=None,
        final_best_iteration=None,
        accepted_improvements=None,
        artifacts=artifacts,
        read_errors=read_errors,
    )


def _read_experiment_item(path: Path) -> ResultItem:
    read_errors: list[str] = []
    artifacts = _experiment_artifacts(path)
    experiment_status = _read_json(path / "experiment_status.json", read_errors)
    closed_loop_summary = _read_json(path / "closed_loop_summary.json", read_errors)
    closed_loop = (
        experiment_status.get("closed_loop")
        if isinstance(experiment_status, dict) and isinstance(experiment_status.get("closed_loop"), dict)
        else {}
    )
    return ResultItem(
        kind="experiment",
        name=path.name,
        path=path,
        modified_time=path.stat().st_mtime,
        status=_str_value(experiment_status, "overall_status"),
        started_at=_str_value(experiment_status, "started_at") or _str_value(closed_loop_summary, "created_at"),
        finished_at=_str_value(experiment_status, "finished_at") or _str_value(closed_loop_summary, "finished_at"),
        summary_text=_read_text(path / "summary.txt", read_errors),
        final_speedup_vs_baseline=_first_float(
            _float_value(closed_loop_summary, "final_validation_median_speedup"),
            _float_value(closed_loop, "final_validation_median_speedup"),
        ),
        final_runtime_reduction_percent=_first_float(
            _float_value(closed_loop_summary, "final_validation_median_runtime_reduction_percent"),
            _float_value(closed_loop, "final_validation_median_runtime_reduction_percent"),
        ),
        final_best_iteration=(
            _int_value(closed_loop_summary, "final_best_iteration")
            or _int_value(closed_loop, "final_best_iteration")
        ),
        accepted_improvements=(
            _int_value(closed_loop, "accepted_improvements")
            or (
                closed_loop_summary.get("status_counts", {}).get("accepted_improvement")
                if isinstance(closed_loop_summary, dict)
                and isinstance(closed_loop_summary.get("status_counts"), dict)
                and isinstance(closed_loop_summary["status_counts"].get("accepted_improvement"), int)
                else None
            )
        ),
        artifacts=artifacts,
        read_errors=read_errors,
    )


def list_run_items(repo_root: Path | None = None) -> list[ResultItem]:
    paths = get_project_paths(repo_root)
    if not paths.result_runs.is_dir():
        return []
    return sorted(
        [_read_run_item(path) for path in paths.result_runs.iterdir() if path.is_dir()],
        key=lambda item: item.modified_time,
        reverse=True,
    )


def list_experiment_items(repo_root: Path | None = None) -> list[ResultItem]:
    paths = get_project_paths(repo_root)
    if not paths.result_experiments.is_dir():
        return []
    return sorted(
        [_read_experiment_item(path) for path in paths.result_experiments.iterdir() if path.is_dir()],
        key=lambda item: item.modified_time,
        reverse=True,
    )


def list_result_items(repo_root: Path | None = None) -> list[ResultItem]:
    return sorted(
        [*list_run_items(repo_root), *list_experiment_items(repo_root)],
        key=lambda item: item.modified_time,
        reverse=True,
    )


def get_latest_result(repo_root: Path | None = None) -> ResultItem | None:
    items = list_result_items(repo_root)
    return items[0] if items else None


def _item_for_path(path: Path, repo_root: Path | None = None) -> ResultItem | None:
    paths = get_project_paths(repo_root)
    resolved = path.resolve()
    try:
        resolved.relative_to(paths.result_runs.resolve())
        if resolved.is_dir():
            return _read_run_item(resolved)
    except ValueError:
        pass
    try:
        resolved.relative_to(paths.result_experiments.resolve())
        if resolved.is_dir():
            return _read_experiment_item(resolved)
    except ValueError:
        pass
    return None


def resolve_result_selector(selector: str, repo_root: Path | None = None) -> ResultItem | None:
    if selector == "latest":
        return get_latest_result(repo_root)

    direct_path = Path(selector)
    candidates: list[ResultItem] = []
    if direct_path.exists():
        item = _item_for_path(direct_path, repo_root)
        if item is not None:
            return item
    else:
        resolved = resolve_project_path(direct_path, repo_root)
        if resolved.exists():
            item = _item_for_path(resolved, repo_root)
            if item is not None:
                return item

    for item in list_result_items(repo_root):
        if item.name == selector:
            candidates.append(item)
    if len(candidates) == 1:
        return candidates[0]
    return None
