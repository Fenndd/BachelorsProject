"""Build static SVG figures from normalized report data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt

from orchestrator.reporting.report_data import ReportData, to_report_dict


PLOT_FILENAMES = {
    "runtime_progress": "runtime_progress.svg",
    "runtime_reduction_by_iteration": "runtime_reduction_by_iteration.svg",
    "correctness_metrics": "correctness_metrics.svg",
    "status_breakdown": "status_breakdown.svg",
    "candidate_funnel": "candidate_funnel.svg",
}


def build_report_figures(
    report_data: ReportData | dict[str, Any],
    plots_dir: Path | str,
) -> dict[str, str]:
    """Generate report SVG plots and return HTML-friendly relative paths."""

    data = _as_report_dict(report_data)
    output_dir = Path(plots_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _plot_runtime_progress(data, output_dir / PLOT_FILENAMES["runtime_progress"])
    _plot_runtime_reduction(
        data,
        output_dir / PLOT_FILENAMES["runtime_reduction_by_iteration"],
    )
    _plot_correctness_metrics(
        data,
        output_dir / PLOT_FILENAMES["correctness_metrics"],
    )
    _plot_status_breakdown(data, output_dir / PLOT_FILENAMES["status_breakdown"])
    _plot_candidate_funnel(data, output_dir / PLOT_FILENAMES["candidate_funnel"])

    return {
        key: str(Path(output_dir.name) / filename).replace("\\", "/")
        for key, filename in PLOT_FILENAMES.items()
    }


def _as_report_dict(report_data: ReportData | dict[str, Any]) -> dict[str, Any]:
    payload = to_report_dict(report_data)
    if not isinstance(payload, dict):
        raise TypeError("report_data must be a ReportData instance or dictionary")
    return payload


def _plot_runtime_progress(data: dict[str, Any], output_path: Path) -> None:
    points = [
        (iteration.get("iteration"), iteration.get("runtime_ns_per_case_median"))
        for iteration in _iterations(data)
        if _is_number(iteration.get("iteration"))
        and _is_number(iteration.get("runtime_ns_per_case_median"))
    ]
    if not points:
        _save_placeholder(output_path, "Runtime data unavailable")
        return

    x_values, y_values = zip(*points)
    fig, ax = _new_figure()
    ax.plot(x_values, y_values, marker="o", color="#246b8f", linewidth=2)
    ax.set_title("Runtime Progress")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Median runtime (ns/case)")
    ax.grid(True, alpha=0.3)
    _save(fig, output_path)


def _plot_runtime_reduction(data: dict[str, Any], output_path: Path) -> None:
    points = [
        (iteration.get("iteration"), iteration.get("speedup_vs_baseline"))
        for iteration in _iterations(data)
        if _is_number(iteration.get("iteration"))
        and _is_number(iteration.get("speedup_vs_baseline"))
    ]
    if not points:
        _save_placeholder(output_path, "Runtime data unavailable")
        return

    x_values, y_values = zip(*points)
    fig, ax = _new_figure()
    ax.bar(x_values, y_values, color="#4f8f46")
    ax.axhline(1.0, color="#555555", linewidth=1, linestyle="--")
    ax.set_title("Runtime Reduction by Iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Speedup vs baseline")
    ax.grid(True, axis="y", alpha=0.3)
    _save(fig, output_path)


def _plot_correctness_metrics(data: dict[str, Any], output_path: Path) -> None:
    points = [
        (iteration.get("iteration"), 1 if iteration.get("correctness_passed") else 0)
        for iteration in _iterations(data)
        if _is_number(iteration.get("iteration"))
        and isinstance(iteration.get("correctness_passed"), bool)
    ]
    if not points:
        _save_placeholder(output_path, "Correctness data unavailable")
        return

    x_values, y_values = zip(*points)
    fig, ax = _new_figure()
    ax.step(x_values, y_values, where="mid", color="#6d5a9c", linewidth=2)
    ax.scatter(x_values, y_values, color="#6d5a9c")
    ax.set_title("Correctness and Accuracy Safety")
    ax.set_xlabel("Iteration")
    ax.set_yticks([0, 1], labels=["Fail", "Pass"])
    ax.set_ylim(-0.2, 1.2)
    ax.grid(True, axis="y", alpha=0.3)
    _save(fig, output_path)


def _plot_status_breakdown(data: dict[str, Any], output_path: Path) -> None:
    counts = _status_counts(data)
    if not counts:
        _save_placeholder(output_path, "Status data unavailable")
        return

    labels = list(counts)
    values = [counts[label] for label in labels]
    fig, ax = _new_figure(width=9.5)
    ax.bar(labels, values, color="#8a6d3b")
    ax.set_title("Status Breakdown")
    ax.set_ylabel("Iterations")
    ax.tick_params(axis="x", labelrotation=35)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    _save(fig, output_path)


def _plot_candidate_funnel(data: dict[str, Any], output_path: Path) -> None:
    values = _candidate_funnel_values(data)
    labels = list(values)
    counts = [values[label] for label in labels]

    fig, ax = _new_figure(width=9.5)
    ax.bar(labels, counts, color="#2f6f6d")
    ax.set_title("Candidate Funnel")
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", labelrotation=25)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    _save(fig, output_path)


def _candidate_funnel_values(data: dict[str, Any]) -> dict[str, int]:
    experiment = _dict_value(data.get("experiment"))
    final_result = _dict_value(data.get("final_result"))
    counts = _status_counts(data)
    iterations = _iterations(data)

    return {
        "Planned iterations": _int_or_zero(experiment.get("total_iterations")),
        "Generated candidates": sum(
            1 for item in iterations if item.get("status") != "generation_failed"
        ),
        "Materialized candidates": sum(
            1
            for item in iterations
            if item.get("status")
            not in {"generation_failed", "materialization_failed"}
        ),
        "Verified candidates": sum(
            counts.get(status, 0)
            for status in ("accepted_improvement", "valid_not_improved", "rejected")
        ),
        "Accepted improvements": counts.get("accepted_improvement", 0),
        "Final best": 1
        if _int_or_zero(final_result.get("final_best_iteration")) > 0
        else 0,
    }


def _save_placeholder(output_path: Path, message: str) -> None:
    fig, ax = _new_figure()
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=14)
    ax.set_axis_off()
    _save(fig, output_path)


def _new_figure(width: float = 7.5, height: float = 4.2) -> tuple[Any, Any]:
    return plt.subplots(figsize=(width, height))


def _save(fig: Any, output_path: Path) -> None:
    fig.savefig(output_path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _iterations(data: dict[str, Any]) -> list[dict[str, Any]]:
    iterations = data.get("iterations")
    if not isinstance(iterations, list):
        return []
    return [item for item in iterations if isinstance(item, dict)]


def _status_counts(data: dict[str, Any]) -> dict[str, int]:
    raw_counts = data.get("status_counts")
    if not isinstance(raw_counts, dict):
        return {}
    return {
        str(status): value
        for status, value in raw_counts.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


__all__ = ["build_report_figures"]
