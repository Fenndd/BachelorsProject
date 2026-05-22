from __future__ import annotations

import json
import pytest
from datetime import datetime
from pathlib import Path

pytestmark = pytest.mark.unit

from orchestrator.storage.run_storage import RunStorage


def test_build_run_id_sanitizes_scenario_name() -> None:
    storage = RunStorage()
    run_id = storage.build_run_id("My Complex Scenario!", started_at=datetime(2026, 1, 15, 12, 30, 0))

    assert run_id.startswith("2026-01-15_12-30-00_")
    assert "my_complex_scenario" in run_id
    assert "!" not in run_id
    assert " " not in run_id


def test_build_run_id_uses_current_time_by_default() -> None:
    storage = RunStorage()
    before = datetime.now()
    run_id = storage.build_run_id("test")
    after = datetime.now()

    parts = run_id.split("_", 2)
    timestamp_str = parts[0] + "_" + parts[1]

    parsed = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")

    assert before.replace(microsecond=0) <= parsed <= after


def test_create_run_directory_creates_logs_subdir(tmp_path: Path) -> None:
    results = tmp_path / "results"
    storage = RunStorage(results_root=results)

    run_dir = storage.create_run_directory("unit test")

    assert run_dir.exists()
    assert (run_dir / "logs").exists()
    assert run_dir.relative_to(results).parts[0] == "runs"


def test_create_run_directory_uses_provided_run_id(tmp_path: Path) -> None:
    results = tmp_path / "results"
    storage = RunStorage(results_root=results)

    run_dir = storage.create_run_directory("test", run_id="my_custom_run")

    assert run_dir.name == "my_custom_run"
    assert (run_dir / "logs").exists()


def test_save_metadata_writes_valid_utf8_json(tmp_path: Path) -> None:
    storage = RunStorage(results_root=tmp_path / "results")
    run_dir = storage.create_run_directory("test")
    payload = {"key": "val\u00fc\u00f1"}

    saved = storage.save_metadata(run_dir, payload)

    assert saved.name == "metadata.json"
    loaded = json.loads(saved.read_text(encoding="utf-8"))
    assert loaded == payload


def test_save_status_writes_valid_utf8_json(tmp_path: Path) -> None:
    storage = RunStorage(results_root=tmp_path / "results")
    run_dir = storage.create_run_directory("test")
    payload = {"status": "success"}

    saved = storage.save_status(run_dir, payload)

    assert saved.name == "status.json"
    loaded = json.loads(saved.read_text(encoding="utf-8"))
    assert loaded == payload


def test_save_metrics_writes_valid_utf8_json(tmp_path: Path) -> None:
    storage = RunStorage(results_root=tmp_path / "results")
    run_dir = storage.create_run_directory("test")
    payload = {"runtime_ns": 12345}

    saved = storage.save_metrics(run_dir, payload)

    assert saved.name == "metrics.json"
    loaded = json.loads(saved.read_text(encoding="utf-8"))
    assert loaded == payload


def test_save_log_writes_under_logs_directory(tmp_path: Path) -> None:
    storage = RunStorage(results_root=tmp_path / "results")
    run_dir = storage.create_run_directory("test")

    log_path = storage.save_log(
        run_dir,
        step_name="build",
        command=["cmake", "--build", "."],
        cwd=run_dir,
        exit_code=0,
        stdout="Build complete\n",
        stderr="",
    )

    assert log_path.parent.name == "logs"
    assert log_path.name == "build.log"
    content = log_path.read_text(encoding="utf-8")
    assert "STEP" in content
    assert "build" in content
    assert "COMMAND" in content
    assert "cmake --build ." in content
    assert "EXIT_CODE" in content
    assert "0" in content
    assert "STDOUT" in content
    assert "Build complete" in content


def test_save_log_sanitizes_step_name(tmp_path: Path) -> None:
    storage = RunStorage(results_root=tmp_path / "results")
    run_dir = storage.create_run_directory("test")

    log_path = storage.save_log(
        run_dir,
        step_name="Build & Run!",
        command="make",
        cwd=run_dir,
        exit_code=None,
        stdout="",
        stderr="",
    )

    assert "!" not in log_path.name
    assert "&" not in log_path.name


def test_append_index_record_appends_jsonl(tmp_path: Path) -> None:
    results = tmp_path / "results"
    storage = RunStorage(results_root=results)

    storage.append_index_record({"run_id": "r1", "status": "success"})
    storage.append_index_record({"run_id": "r2", "status": "failed"})

    index_path = results / "index.jsonl"
    lines = index_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"run_id": "r1", "status": "success"}
    assert json.loads(lines[1]) == {"run_id": "r2", "status": "failed"}


def test_append_index_record_creates_parent_dir(tmp_path: Path) -> None:
    results = tmp_path / "results"
    storage = RunStorage(results_root=results)

    storage.append_index_record({"run_id": "r1"})

    assert (results / "index.jsonl").exists()


def test_create_run_directory_raises_on_duplicate(tmp_path: Path) -> None:
    results = tmp_path / "results"
    storage = RunStorage(results_root=results)

    storage.create_run_directory("test", run_id="my_run")

    with pytest.raises(FileExistsError):
        storage.create_run_directory("test", run_id="my_run")


def test_save_summary_writes_utf8_text(tmp_path: Path) -> None:
    storage = RunStorage(results_root=tmp_path / "results")
    run_dir = storage.create_run_directory("test")
    text = "r\u00e9sum\u00e9 \u2013 test \u2603"

    saved = storage.save_summary(run_dir, text)

    assert saved.name == "summary.txt"
    loaded = saved.read_text(encoding="utf-8")
    assert loaded == text


def test_sanitize_name_falls_back_to_run(tmp_path: Path) -> None:
    storage = RunStorage(results_root=tmp_path / "results")

    assert storage._sanitize_name("!!!") == "run"
    assert storage._sanitize_name("--") == "run"
    assert storage._sanitize_name("_-_") == "run"
    assert storage._sanitize_name("??") == "run"


def test_append_index_record_preserves_unicode(tmp_path: Path) -> None:
    results = tmp_path / "results"
    storage = RunStorage(results_root=results)

    storage.append_index_record({"name": "na\u00efve", "emoji": "caf\u00e9"})

    index_path = results / "index.jsonl"
    lines = index_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["name"] == "na\u00efve"
    assert record["emoji"] == "caf\u00e9"
