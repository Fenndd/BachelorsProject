from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

import orchestrator.control.config_builder_options as options
import orchestrator.tui.views.config_builder_view as config_builder
from orchestrator.experiments.experiment_config import ExperimentConfigError
from orchestrator.tui.views.config_builder_view import ConfigBuilderView


class _FakeLog:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, message: str) -> None:
        self.lines.append(message)

    def clear(self) -> None:
        self.lines.clear()


class _FakeTextArea:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def clear(self) -> None:
        self.text = ""

    def insert(self, value: str) -> None:
        self.text += value


def _make_screen(monkeypatch, tmp_path: Path, overrides: dict[str, object] | None = None) -> tuple[ConfigBuilderView, _FakeLog]:
    paths = SimpleNamespace(
        repo_root=tmp_path,
        configs=tmp_path / "configs",
        experiments_config=tmp_path / "configs" / "experiments",
        cpp=tmp_path / "cpp",
    )
    monkeypatch.setattr(config_builder, "get_project_paths", lambda: paths)
    screen = ConfigBuilderView()
    log = _FakeLog()
    values: dict[str, object] = {
        "experiment_name": SimpleNamespace(value="test_exp"),
        "description": SimpleNamespace(value=""),
        "algorithm": SimpleNamespace(value="lambdatwist_p3p"),
        "target_file": SimpleNamespace(value="cpp/external/lambdatwist/p3p.cc"),
        "baseline_run_sel": SimpleNamespace(value="__custom__"),
        "baseline_run_dir": SimpleNamespace(value="results/runs/baseline"),
        "iterations": SimpleNamespace(value="1"),
        "max_source_chars": SimpleNamespace(value="120000"),
        "llm_config": SimpleNamespace(value="configs/llm_mock.json"),
        "additional_context": _FakeTextArea(""),
        "reporting_html": SimpleNamespace(value=True),
        "reporting_pdf": SimpleNamespace(value=False),
        "reporting_renderer": SimpleNamespace(value="auto"),
        "reporting_fail_on_error": SimpleNamespace(value=False),
        "gt_found_max_drop_points": SimpleNamespace(value=""),
        "llm_provider_override": SimpleNamespace(value=""),
        "llm_model_override": SimpleNamespace(value=""),
        "llm_max_tokens_override": SimpleNamespace(value=""),
        "thinking_enabled": SimpleNamespace(value=False),
        "thinking_effort": SimpleNamespace(value=""),
        "config-builder-status": log,
        "config-builder-summary": SimpleNamespace(update=lambda _text: None),
    }
    if overrides:
        for key, value in overrides.items():
            if key in values and hasattr(values[key], "value"):
                values[key].value = value  # type: ignore[attr-defined]
            elif key in values and hasattr(values[key], "text"):
                values[key].text = str(value)  # type: ignore[attr-defined]
            else:
                values[key] = SimpleNamespace(value=value)

    def query_one(selector, *_args, **_kwargs):
        return values[selector.lstrip("#")]

    monkeypatch.setattr(screen, "query_one", query_one)
    return screen, log


def test_view_lives_in_views_package_and_screen_is_thin() -> None:
    view_source = Path(config_builder.__file__).read_text(encoding="utf-8")
    screen_source = Path("orchestrator/tui/screens/config_builder_screen.py").read_text(encoding="utf-8")

    assert "class ConfigBuilderView(Widget)" in view_source
    assert "class ConfigBuilderView" not in screen_source
    assert "yield Header()" in screen_source
    assert "yield Footer()" in screen_source


def test_builder_visible_structure_and_removed_controls() -> None:
    source = Path(config_builder.__file__).read_text(encoding="utf-8")

    for label in ("Basic experiment", "LLM", "Advanced"):
        assert label in source
    for label in ("Clear Form", "Validate", "Save to local/", "Load Template", "Load Local"):
        assert label in source
    assert "allowed_files" not in source
    assert "variant_id" not in source
    assert "Save & Run" not in source
    assert "btn-back" not in source
    assert "build-errors" not in source
    assert "config-builder-status" in source


def test_invalid_payload_does_not_save(monkeypatch, tmp_path: Path) -> None:
    screen, log = _make_screen(monkeypatch, tmp_path, {"experiment_name": ""})

    assert screen._save_to_local() is None
    local_dir = tmp_path / "configs" / "experiments" / "local"
    assert not list(local_dir.glob("*.json")) if local_dir.exists() else True
    assert any("Validation failed" in line for line in log.lines)


def test_generated_payload_uses_flat_schema(monkeypatch, tmp_path: Path) -> None:
    screen, _log = _make_screen(monkeypatch, tmp_path)

    payload = screen._build_payload()

    assert payload["llm_config"] == "configs/llm_mock.json"
    assert payload["iterations"] == 1
    assert "additional_context" in payload
    assert "variants" not in payload
    assert "variant_id" not in json.dumps(payload)
    assert "optimization_scope" not in payload


def test_reporting_disabled_writes_enabled_false(monkeypatch, tmp_path: Path) -> None:
    screen, _log = _make_screen(monkeypatch, tmp_path, {"reporting_html": False, "reporting_pdf": False})

    payload = screen._build_payload()

    assert payload["reporting"]["enabled"] is False
    assert payload["reporting"]["formats"] == ["html"]


def test_selection_empty_writes_null(monkeypatch, tmp_path: Path) -> None:
    screen, _log = _make_screen(monkeypatch, tmp_path, {"gt_found_max_drop_points": ""})

    payload = screen._build_payload()

    assert payload["selection"]["gt_found_max_drop_points"] is None


def test_selection_numeric_writes_float(monkeypatch, tmp_path: Path) -> None:
    screen, _log = _make_screen(monkeypatch, tmp_path, {"gt_found_max_drop_points": "2.5"})

    payload = screen._build_payload()
    assert payload["selection"]["gt_found_max_drop_points"] == 2.5


@pytest.mark.parametrize("value", ["-1", "not-a-number", "nan", "inf", "-inf"])
def test_invalid_selection_value_is_rejected(monkeypatch, tmp_path: Path, value: str) -> None:
    screen, _log = _make_screen(monkeypatch, tmp_path, {"gt_found_max_drop_points": value})

    with pytest.raises(ExperimentConfigError):
        screen._build_payload()
    assert screen._save_to_local() is None


def _write_run(root: Path, name: str, *, status: str, solver: str | None, candidate: bool = False) -> None:
    run_dir = root / "results" / "runs" / name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(json.dumps({"overall_status": status}), encoding="utf-8")
    (run_dir / "metadata.json").write_text(
        json.dumps({"scenario": "llm_candidate" if candidate else "baseline", "solver_id": solver}),
        encoding="utf-8",
    )
    benchmark = {} if solver is None else {"solver": solver}
    (run_dir / "metrics.json").write_text(json.dumps({"benchmark": benchmark}), encoding="utf-8")
    if candidate:
        (run_dir / "candidate.json").write_text("{}\n", encoding="utf-8")


def test_baseline_filtering_excludes_failed_candidate_and_mismatched(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path
    (root / ".git").mkdir()
    _write_run(root, "good_lambdatwist", status="success", solver="lambdatwist_p3p")
    _write_run(root, "failed_lambdatwist", status="failed", solver="lambdatwist_p3p")
    _write_run(root, "candidate_lambdatwist", status="success", solver="lambdatwist_p3p", candidate=True)
    _write_run(root, "poselib_baseline", status="success", solver="poselib_p3p")

    monkeypatch.setattr(options, "get_project_paths", lambda: SimpleNamespace(repo_root=root))
    discovered = options.discover_baseline_runs("lambdatwist_p3p")
    labels = [label for label, _value in discovered]

    assert any("good_lambdatwist" in label for label in labels)
    assert not any("failed_lambdatwist" in label for label in labels)
    assert not any("candidate_lambdatwist" in label for label in labels)
    assert not any("poselib_baseline" in label for label in labels)


def test_max_tokens_empty_omits_override(monkeypatch, tmp_path: Path) -> None:
    screen, _log = _make_screen(monkeypatch, tmp_path, {"llm_max_tokens_override": ""})
    assert screen._build_payload()["llm_overrides"] is None


def test_max_tokens_valid_integer_written(monkeypatch, tmp_path: Path) -> None:
    screen, _log = _make_screen(monkeypatch, tmp_path, {"llm_max_tokens_override": "4096"})
    assert screen._build_payload()["llm_overrides"]["max_tokens"] == 4096


@pytest.mark.parametrize("bad_value", ["0", "-1", "1.5", "abc"])
def test_invalid_max_tokens_rejected_save_prevented(monkeypatch, tmp_path: Path, bad_value: str) -> None:
    screen, _log = _make_screen(monkeypatch, tmp_path, {"llm_max_tokens_override": bad_value})
    with pytest.raises(ExperimentConfigError):
        screen._build_payload()
    assert screen._save_to_local() is None
