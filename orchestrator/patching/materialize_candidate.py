"""Materialize a generated candidate patch into an isolated workspace copy.

This command never modifies the main project source tree. It copies the current
source root into workspace/candidates/<candidate_run_id>/ and applies the
candidate diff only inside that workspace copy.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKSPACE_ROOT = "workspace/candidates"
DEFAULT_SOURCE_ROOT = "cpp"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply a candidate diff inside an isolated workspace copy."
    )
    parser.add_argument(
        "--candidate-run",
        required=True,
        help="Path to a candidate run directory containing candidate.json and candidate.diff.",
    )
    parser.add_argument(
        "--workspace-root",
        default=DEFAULT_WORKSPACE_ROOT,
        help="Root directory for materialized candidate workspaces.",
    )
    parser.add_argument(
        "--source-root",
        default=DEFAULT_SOURCE_ROOT,
        help="Project source root to copy into the candidate workspace.",
    )
    parser.add_argument("--git-exe", default="git", help="git executable to use.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete an existing candidate workspace before recreating it.",
    )
    return parser.parse_args(argv)


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _step_status(
    name: str,
    status: str,
    exit_code: int | None,
    duration_seconds: float | None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "exit_code": exit_code,
        "duration_seconds": duration_seconds,
    }


def _skipped_step(name: str) -> dict[str, Any]:
    return _step_status(name, "skipped", None, None)


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in {"build", "CMakeFiles", "Testing"}:
            ignored.add(name)
        elif fnmatch.fnmatch(name, "cmake-build-*"):
            ignored.add(name)
    return ignored


def _ensure_deletable_workspace(workspace_path: Path, workspace_root: Path) -> None:
    workspace_path = workspace_path.resolve()
    workspace_root = workspace_root.resolve()
    if workspace_path == workspace_root or workspace_root not in workspace_path.parents:
        raise ValueError(
            f"Refusing to delete workspace outside workspace root: {workspace_path}"
        )


def _run_git_apply(
    git_exe: str, workspace_path: Path, patch_path: Path, check_only: bool
) -> tuple[list[str], int | None, str, str, float, str | None]:
    command = [git_exe, "apply"]
    if check_only:
        command.append("--check")
    command.append(str(patch_path))

    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            check=False,
            env=_workspace_git_environment(workspace_path),
        )
    except FileNotFoundError:
        duration = round(time.perf_counter() - started, 3)
        return command, None, "", f"git executable not found: {git_exe}", duration, (
            f"git executable not found: {git_exe}"
        )

    duration = round(time.perf_counter() - started, 3)
    error_message = None
    if result.returncode != 0:
        error_message = (
            f"{'git apply --check' if check_only else 'git apply'} failed "
            f"with exit code {result.returncode}."
        )
    return command, result.returncode, result.stdout, result.stderr, duration, error_message


def _workspace_git_environment(workspace_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("GIT_DIR", None)
    environment.pop("GIT_WORK_TREE", None)
    environment["GIT_CEILING_DIRECTORIES"] = str(workspace_path.parent)
    return environment


def _build_materialization(
    overall_status: str,
    failed_step: str | None,
    error_message: str | None,
    candidate_run_id: str,
    workspace_path: Path,
    source_root: str,
    patch_path: Path,
    started_at: datetime,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "overall_status": overall_status,
        "failed_step": failed_step,
        "error_message": error_message,
        "candidate_run_id": candidate_run_id,
        "workspace_path": _display_path(workspace_path),
        "source_root": source_root,
        "patch_file": _display_path(patch_path),
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "steps": steps,
    }


def _format_command(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def _write_log(
    log_path: Path,
    candidate_run_id: str,
    candidate_run_dir: Path,
    workspace_path: Path,
    source_root: str,
    patch_path: Path,
    commands: list[dict[str, Any]],
    materialization: dict[str, Any],
) -> Path:
    lines = [
        f"Candidate run id: {candidate_run_id}",
        f"Candidate run directory: {candidate_run_dir}",
        f"Workspace path: {workspace_path}",
        f"Source root: {source_root}",
        f"Patch file path: {patch_path}",
        "",
        "Commands:",
    ]

    if not commands:
        lines.append("(none)")

    for command_info in commands:
        lines.extend(
            [
                _format_command(command_info["command"]),
                f"exit_code: {command_info['exit_code']}",
                "stdout:",
                command_info["stdout"],
                "stderr:",
                command_info["stderr"],
                "",
            ]
        )

    lines.extend(
        [
            f"Final status: {materialization['overall_status']}",
            f"Failed step: {materialization['failed_step'] or 'none'}",
            f"Error message: {materialization['error_message'] or 'none'}",
            "",
        ]
    )
    log_path.write_text("\n".join(lines), encoding="utf-8")
    return log_path


def _fail(
    candidate_run_dir: Path,
    candidate_run_id: str,
    workspace_path: Path,
    source_root_text: str,
    patch_path: Path,
    started_at: datetime,
    failed_step: str,
    error_message: str,
    steps: list[dict[str, Any]],
    commands: list[dict[str, Any]],
) -> int:
    materialization = _build_materialization(
        "failed",
        failed_step,
        error_message,
        candidate_run_id,
        workspace_path,
        source_root_text,
        patch_path,
        started_at,
        steps,
    )
    _write_json(candidate_run_dir / "materialization.json", materialization)
    _write_log(
        candidate_run_dir / "apply_candidate.log",
        candidate_run_id,
        candidate_run_dir,
        workspace_path,
        source_root_text,
        patch_path,
        commands,
        materialization,
    )
    print(f"Final status: failed")
    print(f"ERROR: {error_message}", file=sys.stderr)
    print(f"Logs saved to: {candidate_run_dir / 'apply_candidate.log'}")
    return 1


def _skip_noop_candidate(
    candidate_run_dir: Path,
    candidate_run_id: str,
    workspace_path: Path,
    source_root_text: str,
    patch_path: Path,
    started_at: datetime,
) -> int:
    steps = [
        _skipped_step("copy_source_tree"),
        _skipped_step("git_apply_check"),
        _skipped_step("git_apply"),
    ]
    materialization = _build_materialization(
        "skipped",
        None,
        None,
        candidate_run_id,
        workspace_path,
        source_root_text,
        patch_path,
        started_at,
        steps,
    )
    _write_json(candidate_run_dir / "materialization.json", materialization)
    _write_log(
        candidate_run_dir / "apply_candidate.log",
        candidate_run_id,
        candidate_run_dir,
        workspace_path,
        source_root_text,
        patch_path,
        [],
        materialization,
    )
    print("Final status: skipped")
    print("No patch to materialize: candidate expected_effect is 'none'.")
    print(f"Logs saved to: {candidate_run_dir / 'apply_candidate.log'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    started_at = datetime.now().astimezone()
    candidate_run_dir = _resolve_path(args.candidate_run)
    candidate_run_id = candidate_run_dir.name
    workspace_root = _resolve_path(args.workspace_root)
    workspace_path = workspace_root / candidate_run_id
    source_root_path = _resolve_path(args.source_root)
    workspace_source_path = workspace_path / source_root_path.name
    candidate_json_path = candidate_run_dir / "candidate.json"
    patch_path = (candidate_run_dir / "candidate.diff").resolve()

    print(f"Candidate run id: {candidate_run_id}")
    print(f"Workspace path: {workspace_path}")
    print(f"Patch file path: {patch_path}")

    steps: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []

    if not candidate_run_dir.exists() or not candidate_run_dir.is_dir():
        print("Final status: failed")
        print(
            f"ERROR: Candidate run directory not found: {candidate_run_dir}",
            file=sys.stderr,
        )
        return 1

    try:
        if not candidate_json_path.exists():
            raise FileNotFoundError(f"candidate.json not found: {candidate_json_path}")
        if not patch_path.exists():
            raise FileNotFoundError(f"candidate.diff not found: {patch_path}")
        if not source_root_path.exists() or not source_root_path.is_dir():
            raise FileNotFoundError(f"Source root not found: {source_root_path}")

        candidate_data = json.loads(candidate_json_path.read_text(encoding="utf-8-sig"))
        if not isinstance(candidate_data, dict):
            raise ValueError(f"candidate.json must contain a JSON object: {candidate_json_path}")
        patch_text = patch_path.read_text(encoding="utf-8")
        if not patch_text.strip():
            if candidate_data.get("expected_effect") == "none":
                return _skip_noop_candidate(
                    candidate_run_dir,
                    candidate_run_id,
                    workspace_path,
                    args.source_root,
                    patch_path,
                    started_at,
                )
            raise ValueError(f"candidate.diff is empty: {patch_path}")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        steps.extend(
            [
                _step_status("copy_source_tree", "failed", None, None),
                _skipped_step("git_apply_check"),
                _skipped_step("git_apply"),
            ]
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            args.source_root,
            patch_path,
            started_at,
            "copy_source_tree",
            str(exc),
            steps,
            commands,
        )

    copy_started = time.perf_counter()
    try:
        if workspace_path.exists():
            if not args.overwrite:
                raise FileExistsError(
                    f"Candidate workspace already exists: {workspace_path}. "
                    "Use --overwrite to recreate it."
                )
            _ensure_deletable_workspace(workspace_path, workspace_root)
            shutil.rmtree(workspace_path)

        workspace_path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_root_path, workspace_source_path, ignore=_copy_ignore)
        copy_duration = round(time.perf_counter() - copy_started, 3)
        steps.append(_step_status("copy_source_tree", "success", None, copy_duration))
    except (OSError, ValueError) as exc:
        copy_duration = round(time.perf_counter() - copy_started, 3)
        steps.extend(
            [
                _step_status("copy_source_tree", "failed", None, copy_duration),
                _skipped_step("git_apply_check"),
                _skipped_step("git_apply"),
            ]
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            args.source_root,
            patch_path,
            started_at,
            "copy_source_tree",
            str(exc),
            steps,
            commands,
        )

    command, exit_code, stdout, stderr, duration, error_message = _run_git_apply(
        args.git_exe, workspace_path, patch_path, check_only=True
    )
    commands.append(
        {"command": command, "exit_code": exit_code, "stdout": stdout, "stderr": stderr}
    )
    if error_message:
        steps.extend(
            [
                _step_status("git_apply_check", "failed", exit_code, duration),
                _skipped_step("git_apply"),
            ]
        )
        detail = stderr.strip() or stdout.strip() or error_message
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            args.source_root,
            patch_path,
            started_at,
            "git_apply_check",
            detail,
            steps,
            commands,
        )
    steps.append(_step_status("git_apply_check", "success", exit_code, duration))

    command, exit_code, stdout, stderr, duration, error_message = _run_git_apply(
        args.git_exe, workspace_path, patch_path, check_only=False
    )
    commands.append(
        {"command": command, "exit_code": exit_code, "stdout": stdout, "stderr": stderr}
    )
    if error_message:
        steps.append(_step_status("git_apply", "failed", exit_code, duration))
        detail = stderr.strip() or stdout.strip() or error_message
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_path,
            args.source_root,
            patch_path,
            started_at,
            "git_apply",
            detail,
            steps,
            commands,
        )
    steps.append(_step_status("git_apply", "success", exit_code, duration))

    materialization = _build_materialization(
        "success",
        None,
        None,
        candidate_run_id,
        workspace_path,
        args.source_root,
        patch_path,
        started_at,
        steps,
    )
    _write_json(candidate_run_dir / "materialization.json", materialization)
    _write_log(
        candidate_run_dir / "apply_candidate.log",
        candidate_run_id,
        candidate_run_dir,
        workspace_path,
        args.source_root,
        patch_path,
        commands,
        materialization,
    )

    print("Final status: success")
    print("Candidate was materialized in workspace only.")
    print(f"Workspace path: {workspace_path}")
    print(f"Artifact log: {candidate_run_dir / 'apply_candidate.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
