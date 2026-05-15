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
    "candidate_runtime_by_iteration": "candidate_runtime_by_iteration.svg",
    "runtime_reduction_by_iteration": "runtime_reduction_by_iteration.svg",
    "correctness_metrics": "correctness_metrics.svg",
    "status_breakdown": "status_breakdown.svg",
    "candidate_funnel": "candidate_funnel.svg",
    "phase_timings": "phase_timings.svg",
    "llm_tokens_by_iteration": "llm_tokens_by_iteration.svg",
    "llm_latency_by_iteration": "llm_latency_by_iteration.svg",
    "failure_reason_breakdown": "failure_reason_breakdown.svg",
    "diff_stats_by_iteration": "diff_stats_by_iteration.svg",
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
    _plot_candidate_runtime_by_iteration(
        data,
        output_dir / PLOT_FILENAMES["candidate_runtime_by_iteration"],
    )
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
    _plot_phase_timings(data, output_dir / PLOT_FILENAMES["phase_timings"])
    _plot_llm_tokens(data, output_dir / PLOT_FILENAMES["llm_tokens_by_iteration"])
    _plot_llm_latency(data, output_dir / PLOT_FILENAMES["llm_latency_by_iteration"])
    _plot_failure_reason_breakdown(
        data,
        output_dir / PLOT_FILENAMES["failure_reason_breakdown"],
    )
    _plot_diff_stats_by_iteration(
        data,
        output_dir / PLOT_FILENAMES["diff_stats_by_iteration"],
    )

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
    """Step plot of current-best runtime over iterations (including baseline as iter 0)."""

    baseline_rt = _number_or_none(
        _dict_value(data.get("baseline_metrics")).get("runtime_ns_per_case_median")
    )

    # Build (iteration, runtime) step sequence using only promoted iterations
    iterations = sorted(
        (it for it in _iterations(data) if _is_number(it.get("iteration"))),
        key=lambda it: it["iteration"],
    )

    current_best = baseline_rt
    step_points: list[tuple[int, float]] = []
    if baseline_rt is not None:
        step_points.append((0, baseline_rt))

    for it in iterations:
        if it.get("promoted") is True:
            rt = _number_or_none(it.get("runtime_ns_per_case_median"))
            if rt is not None:
                current_best = rt
        if current_best is not None:
            step_points.append((int(it["iteration"]), current_best))

    if not step_points:
        _save_placeholder(output_path, "Current best runtime data unavailable")
        return

    x_values, y_values = zip(*step_points)
    fig, ax = _new_figure()
    ax.step(x_values, y_values, where="post", color="#246b8f", linewidth=2)
    ax.scatter(x_values, y_values, color="#246b8f", zorder=3)
    ax.set_title("Current Best Runtime Progress")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Current best median runtime (ns/case)")
    ax.grid(True, alpha=0.3)
    _save(fig, output_path)


def _plot_candidate_runtime_by_iteration(data: dict[str, Any], output_path: Path) -> None:
    """Scatter plot of candidate runtime per iteration with baseline and final-best lines."""

    points = [
        (int(it["iteration"]), _number_or_none(it.get("runtime_ns_per_case_median")))
        for it in _iterations(data)
        if _is_number(it.get("iteration"))
        and _number_or_none(it.get("runtime_ns_per_case_median")) is not None
    ]

    if not points:
        _save_placeholder(output_path, "Candidate runtime data unavailable")
        return

    x_values, y_values = zip(*points)
    fig, ax = _new_figure()
    ax.plot(x_values, y_values, color="#aaaaaa", linewidth=0.8, zorder=1)
    ax.scatter(x_values, y_values, color="#246b8f", zorder=2, label="candidate")

    baseline_rt = _number_or_none(
        _dict_value(data.get("baseline_metrics")).get("runtime_ns_per_case_median")
    )
    if baseline_rt is not None:
        ax.axhline(baseline_rt, color="#e07b39", linewidth=1.2, linestyle="--", label="baseline")

    final_best_rt = _number_or_none(
        _dict_value(data.get("final_best_candidate")).get("runtime_ns_per_case_median")
    )
    if final_best_rt is not None:
        ax.axhline(
            final_best_rt, color="#4f8f46", linewidth=1.2, linestyle=":", label="final best"
        )

    ax.set_title("Candidate Runtime by Iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Median runtime (ns/case)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)
    _save(fig, output_path)


def _plot_runtime_reduction(data: dict[str, Any], output_path: Path) -> None:
    """Bar chart of speedup vs baseline per iteration, coloured by promotion status."""

    points = [
        (
            int(it["iteration"]),
            _number_or_none(it.get("speedup_vs_baseline")),
            it.get("promoted") is True,
        )
        for it in _iterations(data)
        if _is_number(it.get("iteration"))
        and _number_or_none(it.get("speedup_vs_baseline")) is not None
    ]

    if not points:
        _save_placeholder(output_path, "Runtime data unavailable")
        return

    x_values = [p[0] for p in points]
    y_values = [p[1] for p in points]
    colors = ["#4f8f46" if p[2] else "#7a9fbf" for p in points]

    fig, ax = _new_figure()
    ax.bar(x_values, y_values, color=colors)
    ax.axhline(1.0, color="#555555", linewidth=1, linestyle="--", label="baseline (1.0)")
    ax.set_title("Runtime Reduction by Iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Speedup vs baseline")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=9)
    _save(fig, output_path)


def _plot_correctness_metrics(data: dict[str, Any], output_path: Path) -> None:
    points = [
        (it.get("iteration"), 1 if it.get("correctness_passed") else 0)
        for it in _iterations(data)
        if _is_number(it.get("iteration"))
        and isinstance(it.get("correctness_passed"), bool)
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


def _plot_phase_timings(data: dict[str, Any], output_path: Path) -> None:
    phases = [
        ("generation_seconds", "Generation", "#246b8f"),
        ("materialization_seconds", "Materialization", "#7a9fbf"),
        ("verification_seconds", "Verification", "#4f8f46"),
        ("benchmark_seconds", "Benchmark", "#e07b39"),
    ]
    rows: list[tuple[int, dict[str, float]]] = []
    for iteration in _iterations(data):
        if not _is_number(iteration.get("iteration")):
            continue
        timings = _dict_value(iteration.get("phase_timings"))
        values = {
            key: value
            for key, _, _ in phases
            if (value := _number_or_none(timings.get(key))) is not None
        }
        if values:
            rows.append((int(iteration["iteration"]), values))

    if not rows:
        _save_placeholder(output_path, "Phase timing data unavailable")
        return

    x_values = [row[0] for row in rows]
    bottoms = [0.0 for _ in rows]
    fig, ax = _new_figure(width=9.0)
    for key, label, color in phases:
        y_values = [row[1].get(key, 0.0) for row in rows]
        if any(value != 0.0 for value in y_values):
            ax.bar(x_values, y_values, bottom=bottoms, label=label, color=color)
        bottoms = [bottom + value for bottom, value in zip(bottoms, y_values)]

    ax.set_title("Phase Timings by Iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Seconds")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=9)
    _save(fig, output_path)


def _plot_llm_tokens(data: dict[str, Any], output_path: Path) -> None:
    points = [
        (int(iteration["iteration"]), int(tokens))
        for iteration in _iterations(data)
        if _is_number(iteration.get("iteration"))
        and (tokens := _number_or_none(_dict_value(iteration.get("llm_usage")).get("total_tokens")))
        is not None
    ]
    if not points:
        _save_placeholder(output_path, "LLM token usage data unavailable")
        return

    x_values, y_values = zip(*points)
    fig, ax = _new_figure()
    ax.bar(x_values, y_values, color="#6d5a9c")
    ax.set_title("LLM Token Usage by Iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Total tokens")
    ax.grid(True, axis="y", alpha=0.3)
    _save(fig, output_path)


def _plot_llm_latency(data: dict[str, Any], output_path: Path) -> None:
    points = [
        (int(iteration["iteration"]), latency)
        for iteration in _iterations(data)
        if _is_number(iteration.get("iteration"))
        and (latency := _number_or_none(_dict_value(iteration.get("llm_usage")).get("api_latency_seconds")))
        is not None
    ]
    if not points:
        _save_placeholder(output_path, "LLM latency data unavailable")
        return

    x_values, y_values = zip(*points)
    fig, ax = _new_figure()
    ax.plot(x_values, y_values, color="#2f6f6d", linewidth=1.5)
    ax.scatter(x_values, y_values, color="#2f6f6d")
    ax.set_title("LLM API Latency by Iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Latency (seconds)")
    ax.grid(True, alpha=0.3)
    _save(fig, output_path)


def _plot_failure_reason_breakdown(data: dict[str, Any], output_path: Path) -> None:
    rows = sorted(
        [
            (str(item.get("code")), count)
            for item in _reason_code_counts(data)
            if (count := _int_or_none(item.get("count"))) is not None and count > 0
        ],
        key=lambda item: (-item[1], item[0]),
    )
    if not rows:
        _save_placeholder(output_path, "Failure reason data unavailable")
        return

    labels, values = zip(*rows)
    height = min(9.5, max(3.2, 0.42 * len(rows) + 1.4))
    fig, ax = _new_figure(width=9.5, height=height)
    y_positions = range(len(labels))
    ax.barh(y_positions, values, color="#8a6d3b")
    ax.set_yticks(list(y_positions), labels=labels)
    ax.invert_yaxis()
    ax.set_title("Outcome Reason Breakdown")
    ax.set_xlabel("Count")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    _save(fig, output_path)


def _plot_diff_stats_by_iteration(data: dict[str, Any], output_path: Path) -> None:
    points: list[tuple[int, int]] = []
    for iteration in _iterations(data):
        if not _is_number(iteration.get("iteration")):
            continue
        diff_stats = _dict_value(iteration.get("diff_stats"))
        lines_added = _int_or_none(diff_stats.get("lines_added"))
        lines_removed = _int_or_none(diff_stats.get("lines_removed"))
        if lines_added is None and lines_removed is None:
            continue
        points.append((int(iteration["iteration"]), (lines_added or 0) + (lines_removed or 0)))

    if not points:
        _save_placeholder(output_path, "Diff statistics unavailable")
        return

    x_values, y_values = zip(*points)
    fig, ax = _new_figure()
    ax.bar(x_values, y_values, color="#9b5f6d")
    ax.set_title("Diff Size by Iteration")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Changed lines")
    ax.grid(True, axis="y", alpha=0.3)
    _save(fig, output_path)


def _candidate_funnel_values(data: dict[str, Any]) -> dict[str, int]:
    experiment = _dict_value(data.get("experiment"))
    final_result = _dict_value(data.get("final_result"))
    counts = _status_counts(data)
    iterations = _iterations(data)

    _SKIP_GENERATED = {"generation_failed"}
    _SKIP_MATERIALIZED = {"generation_failed", "materialization_failed", "no_op"}

    verified_count = sum(
        1
        for it in iterations
        if _number_or_none(it.get("runtime_ns_per_case_median")) is not None
        or isinstance(it.get("correctness_passed"), bool)
    )
    correct_count = sum(
        1 for it in iterations if it.get("correctness_passed") is True
    )

    return {
        "Planned iterations": _int_or_zero(experiment.get("total_iterations")),
        "Generated candidates": sum(
            1 for it in iterations if it.get("status") not in _SKIP_GENERATED
        ),
        "Materialized candidates": sum(
            1 for it in iterations if it.get("status") not in _SKIP_MATERIALIZED
        ),
        "Verified candidates": verified_count,
        "Correct candidates": correct_count,
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


def _reason_code_counts(data: dict[str, Any]) -> list[dict[str, Any]]:
    counts = data.get("reason_code_counts")
    if not isinstance(counts, list):
        return []
    return [item for item in counts if isinstance(item, dict)]


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


__all__ = ["build_report_figures"]
