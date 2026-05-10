"""Closed-loop optimization data contracts and artifact helpers.

This module defines closed-loop paths, serializable state records, JSON/JSONL
artifact helpers, and status counting. It deliberately does not run generation,
materialization, verification, or candidate promotion.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class IterationStatus(str, Enum):
    """Closed-loop outcome status for one optimization iteration."""

    ACCEPTED_IMPROVEMENT = "accepted_improvement"
    VALID_NOT_IMPROVED = "valid_not_improved"
    REJECTED = "rejected"
    MATERIALIZATION_FAILED = "materialization_failed"
    VERIFICATION_FAILED = "verification_failed"
    NO_OP = "no_op"
    GENERATION_FAILED = "generation_failed"


@dataclass(frozen=True)
class ClosedLoopPaths:
    """Filesystem layout for closed-loop state and final artifacts."""

    workspace_root: Path
    results_root: Path
    experiment_id: str
    current_best_source_dir: Path
    current_best_state_path: Path
    final_optimized_source_dir: Path
    final_optimized_source_diff_path: Path
    closed_loop_summary_path: Path
    closed_loop_iterations_path: Path

    @classmethod
    def from_roots(
        cls,
        workspace_root: Path | str,
        results_root: Path | str,
        experiment_id: str,
    ) -> "ClosedLoopPaths":
        """Build the agreed closed-loop artifact paths from repository roots."""

        workspace_path = Path(workspace_root)
        results_path = Path(results_root)
        workspace_experiment_dir = workspace_path / "experiments" / experiment_id
        results_experiment_dir = results_path / "experiments" / experiment_id

        return cls(
            workspace_root=workspace_path,
            results_root=results_path,
            experiment_id=experiment_id,
            current_best_source_dir=workspace_experiment_dir / "current_best_source",
            current_best_state_path=workspace_experiment_dir / "current_best_state.json",
            final_optimized_source_dir=results_experiment_dir / "final_optimized_source",
            final_optimized_source_diff_path=results_experiment_dir
            / "final_optimized_source.diff",
            closed_loop_summary_path=results_experiment_dir / "closed_loop_summary.json",
            closed_loop_iterations_path=results_experiment_dir
            / "closed_loop_iterations.jsonl",
        )


@dataclass
class CurrentBestState:
    """Mutable experiment-local pointer to the current best accepted source."""

    experiment_id: str
    target_file: str
    original_baseline_run_dir: Path
    original_baseline_metrics_path: Path
    current_best_iteration: int
    current_best_is_baseline: bool
    current_best_source_dir: Path
    current_best_run_dir: Path
    current_best_metrics_path: Path
    accepted_improvements: int
    updated_at: str

    def __post_init__(self) -> None:
        if self.current_best_iteration < 0:
            raise ValueError("current_best_iteration must be non-negative")
        if self.accepted_improvements < 0:
            raise ValueError("accepted_improvements must be non-negative")
        if self.current_best_iteration == 0 and not self.current_best_is_baseline:
            raise ValueError(
                "current_best_is_baseline must be true when current_best_iteration is 0"
            )
        if self.current_best_iteration > 0 and self.current_best_is_baseline:
            raise ValueError(
                "current_best_is_baseline must be false when current_best_iteration is greater than 0"
            )
        if self.current_best_is_baseline and self.accepted_improvements != 0:
            raise ValueError(
                "accepted_improvements must be 0 when current best is the baseline"
            )
        if self.current_best_iteration > 0 and self.accepted_improvements < 1:
            raise ValueError(
                "accepted_improvements must be at least 1 when current_best_iteration is greater than 0"
            )


@dataclass
class ClosedLoopIterationRecord:
    """One compact JSONL-compatible closed-loop iteration record."""

    experiment_id: str
    iteration: int
    status: IterationStatus
    base_source_kind: str
    reference_best_iteration_before: int
    reference_best_run_dir: Path | None = None
    candidate_run_dir: Path | None = None
    candidate_summary: dict[str, Any] | str | None = None
    candidate_rationale: str | None = None
    candidate_expected_effect: str | None = None
    candidate_risk_level: str | None = None
    decision_vs_current_best: dict[str, Any] | str | None = None
    decision_vs_original_baseline: dict[str, Any] | str | None = None
    speedup_vs_current_best: float | None = None
    speedup_vs_original_baseline: float | None = None
    current_best_updated: bool = False
    current_best_iteration_after: int | None = None
    failure_stage: str | None = None
    failure_reason: str | None = None
    materialization_match_summary: dict[str, Any] | None = None
    history_included: bool = False
    history_guidance: str | None = None
    created_at: str | None = None


@dataclass
class ClosedLoopSummary:
    """Final closed-loop experiment summary artifact."""

    experiment_id: str
    target_file: str
    total_iterations: int
    completed_iterations: int
    original_baseline_run_dir: Path
    original_baseline_metrics_path: Path
    final_best_iteration: int
    final_best_candidate_run_dir: Path | None
    final_optimized_source_dir: Path
    final_optimized_source_diff_path: Path
    final_speedup_vs_original_baseline: float | None
    final_runtime_reduction_percent: float | None
    iterations_after_final_best: int
    status_counts: dict[str, int]
    created_at: str
    finished_at: str


def to_plain_dict(value: Any) -> Any:
    """Recursively convert dataclasses, Paths, and Enums into JSON values."""

    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_plain_dict(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, tuple):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_plain_dict(item) for key, item in value.items()}
    return value


def write_current_best_state(path: Path | str, state: CurrentBestState) -> Path:
    """Write current_best_state.json as human-readable UTF-8 JSON."""

    output_path = Path(path)
    _write_json(output_path, to_plain_dict(state))
    return output_path


def read_current_best_state(path: Path | str) -> CurrentBestState:
    """Read current_best_state.json and reconstruct path-valued fields."""

    input_path = Path(path)
    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in: {input_path}")

    return CurrentBestState(
        experiment_id=_required_string(payload, "experiment_id"),
        target_file=_required_string(payload, "target_file"),
        original_baseline_run_dir=Path(
            _required_string(payload, "original_baseline_run_dir")
        ),
        original_baseline_metrics_path=Path(
            _required_string(payload, "original_baseline_metrics_path")
        ),
        current_best_iteration=_required_int(payload, "current_best_iteration"),
        current_best_is_baseline=_required_bool(payload, "current_best_is_baseline"),
        current_best_source_dir=Path(_required_string(payload, "current_best_source_dir")),
        current_best_run_dir=Path(_required_string(payload, "current_best_run_dir")),
        current_best_metrics_path=Path(
            _required_string(payload, "current_best_metrics_path")
        ),
        accepted_improvements=_required_int(payload, "accepted_improvements"),
        updated_at=_required_string(payload, "updated_at"),
    )


def write_closed_loop_summary(path: Path | str, summary: ClosedLoopSummary) -> Path:
    """Write closed_loop_summary.json as human-readable UTF-8 JSON."""

    output_path = Path(path)
    _write_json(output_path, to_plain_dict(summary))
    return output_path


def append_closed_loop_iteration_record(
    path: Path | str,
    record: ClosedLoopIterationRecord,
) -> Path:
    """Append one compact JSON object to closed_loop_iterations.jsonl."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as output_file:
        output_file.write(
            json.dumps(to_plain_dict(record), ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
    return output_path


def count_iteration_statuses(
    records: Iterable[ClosedLoopIterationRecord | dict[str, Any]],
) -> dict[str, int]:
    """Count iteration statuses, including every known status with zero default."""

    counts = {status.value: 0 for status in IterationStatus}
    for record in records:
        raw_status = record.status if isinstance(record, ClosedLoopIterationRecord) else record.get("status")
        status_value = raw_status.value if isinstance(raw_status, IterationStatus) else raw_status
        if status_value in counts:
            counts[status_value] += 1
    return counts


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _required_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Field '{field_name}' must be a non-empty string.")
    return value


def _required_int(payload: dict[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"Field '{field_name}' must be an integer.")
    return value


def _required_bool(payload: dict[str, Any], field_name: str) -> bool:
    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"Field '{field_name}' must be a boolean.")
    return value