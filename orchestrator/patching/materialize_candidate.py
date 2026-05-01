"""Materialize a generated candidate patch into an isolated workspace copy.

This command never modifies the main project source tree. It copies the current
source root into workspace/candidates/<candidate_run_id>/ and applies the
candidate diff only inside that workspace copy.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path, PurePosixPath
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
    parser.add_argument(
        "--keep-failed-workspace",
        action="store_true",
        help="Keep the candidate workspace if materialization fails.",
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


def _normalize_candidate_path(path_text: str) -> str:
    normalized_text = path_text.strip().replace("\\", "/")
    if not normalized_text:
        raise ValueError("path is empty")
    if "\x00" in normalized_text:
        raise ValueError(f"path contains a null byte: {path_text!r}")
    if normalized_text.startswith("/"):
        raise ValueError(f"path must be relative: {path_text!r}")
    if len(normalized_text) >= 2 and normalized_text[1] == ":":
        raise ValueError(f"path must not include a drive prefix: {path_text!r}")

    path = PurePosixPath(normalized_text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must stay inside the workspace: {path_text!r}")
    if not path.parts:
        raise ValueError("path is empty")
    return path.as_posix()


def _validate_target_files(candidate_data: dict[str, Any]) -> list[str]:
    if "target_files" not in candidate_data:
        raise ValueError("candidate.json is missing required field 'target_files'.")

    target_files = candidate_data["target_files"]
    if not isinstance(target_files, list) or not target_files:
        raise ValueError("candidate.json field 'target_files' must be a non-empty list.")

    normalized_files = []
    seen = set()
    for index, target_file in enumerate(target_files):
        if not isinstance(target_file, str):
            raise ValueError(
                "candidate.json field 'target_files' must contain only strings; "
                f"item {index} is {type(target_file).__name__}."
            )
        normalized_file = _normalize_candidate_path(target_file)
        if normalized_file not in seen:
            normalized_files.append(normalized_file)
            seen.add(normalized_file)

    return normalized_files


def _extract_diff_header_path(header_text: str) -> str:
    path_text = header_text.strip()
    if "\t" in path_text:
        path_text = path_text.split("\t", 1)[0]
    return path_text


def _parse_patched_files(patch_text: str) -> list[str]:
    patched_files = []
    seen = set()
    pending_old_path: str | None = None
    expect_new_header = False

    def add_path(path_text: str) -> None:
        normalized_path = _normalize_candidate_path(path_text)
        if normalized_path not in seen:
            patched_files.append(normalized_path)
            seen.add(normalized_path)

    for line_number, line in enumerate(patch_text.splitlines(), start=1):
        if line.startswith("--- "):
            old_header_path = _extract_diff_header_path(line[4:])
            pending_old_path = None
            expect_new_header = True
            if old_header_path != "/dev/null":
                if not old_header_path.startswith("a/"):
                    raise ValueError(
                        "Invalid old-file diff header in candidate.diff at "
                        f"line {line_number}: {line}"
                    )
                try:
                    pending_old_path = _normalize_candidate_path(old_header_path[2:])
                except ValueError as exc:
                    raise ValueError(
                        "Invalid old-file diff path in candidate.diff at "
                        f"line {line_number}: {exc}"
                    ) from exc
            continue

        if expect_new_header and line.startswith("+++ "):
            new_header_path = _extract_diff_header_path(line[4:])
            expect_new_header = False
            if new_header_path == "/dev/null":
                if pending_old_path is not None:
                    add_path(pending_old_path)
            else:
                if not new_header_path.startswith("b/"):
                    raise ValueError(
                        "Invalid new-file diff header in candidate.diff at "
                        f"line {line_number}: {line}"
                    )
                try:
                    add_path(new_header_path[2:])
                except ValueError as exc:
                    raise ValueError(
                        "Invalid new-file diff path in candidate.diff at "
                        f"line {line_number}: {exc}"
                    ) from exc
            pending_old_path = None

    return patched_files


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError(f"Target path is not a file: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_workspace_target_files(
    workspace_path: Path, target_files: list[str]
) -> dict[str, str | None]:
    return {
        target_file: _file_hash(workspace_path / target_file)
        for target_file in target_files
    }


def _detect_changed_files(
    before_hashes: dict[str, str | None], after_hashes: dict[str, str | None]
) -> list[str]:
    return [
        target_file
        for target_file, before_hash in before_hashes.items()
        if after_hashes.get(target_file) != before_hash
    ]


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
    target_files: list[str],
    patched_files: list[str],
    changed_files: list[str],
    post_apply_verification: str,
    workspace_removed_on_failure: bool,
    keep_failed_workspace: bool,
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
        "target_files": target_files,
        "patched_files": patched_files,
        "changed_files": changed_files,
        "post_apply_verification": post_apply_verification,
        "workspace_removed_on_failure": workspace_removed_on_failure,
        "keep_failed_workspace": keep_failed_workspace,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "steps": steps,
    }


def _format_command(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def _format_log_list(values: list[str]) -> list[str]:
    if not values:
        return ["(none)"]
    return [f"- {value}" for value in values]


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
        "Target files:",
        *_format_log_list(materialization["target_files"]),
        "",
        "Patched files parsed from diff:",
        *_format_log_list(materialization["patched_files"]),
        "",
        "Changed files detected after apply:",
        *_format_log_list(materialization["changed_files"]),
        "",
        f"Post-apply verification: {materialization['post_apply_verification']}",
        f"Workspace removed on failure: {materialization['workspace_removed_on_failure']}",
        f"Keep failed workspace: {materialization['keep_failed_workspace']}",
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
    workspace_root: Path,
    workspace_path: Path,
    source_root_text: str,
    patch_path: Path,
    target_files: list[str],
    patched_files: list[str],
    changed_files: list[str],
    post_apply_verification: str,
    keep_failed_workspace: bool,
    rollback_workspace: bool,
    started_at: datetime,
    failed_step: str,
    error_message: str,
    steps: list[dict[str, Any]],
    commands: list[dict[str, Any]],
) -> int:
    workspace_removed_on_failure = False
    if not keep_failed_workspace and rollback_workspace and workspace_path.exists():
        try:
            _ensure_deletable_workspace(workspace_path, workspace_root)
            shutil.rmtree(workspace_path)
            workspace_removed_on_failure = True
        except (OSError, ValueError) as exc:
            error_message = f"{error_message} Rollback failed: {exc}"

    materialization = _build_materialization(
        "failed",
        failed_step,
        error_message,
        candidate_run_id,
        workspace_path,
        source_root_text,
        patch_path,
        target_files,
        patched_files,
        changed_files,
        post_apply_verification,
        workspace_removed_on_failure,
        keep_failed_workspace,
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
    print("Final status: failed")
    print(f"Failed step: {failed_step}")
    print(f"ERROR: {error_message}", file=sys.stderr)
    print(f"Workspace removed on failure: {workspace_removed_on_failure}")
    print(f"Logs saved to: {candidate_run_dir / 'apply_candidate.log'}")
    return 1


def _skip_noop_candidate(
    candidate_run_dir: Path,
    candidate_run_id: str,
    workspace_path: Path,
    source_root_text: str,
    patch_path: Path,
    target_files: list[str],
    patched_files: list[str],
    keep_failed_workspace: bool,
    started_at: datetime,
    steps: list[dict[str, Any]],
) -> int:
    steps.extend(
        [
            _skipped_step("copy_source_tree"),
            _skipped_step("hash_target_files_before_apply"),
            _skipped_step("git_apply_check"),
            _skipped_step("git_apply"),
            _skipped_step("post_apply_verification"),
        ]
    )
    materialization = _build_materialization(
        "skipped",
        None,
        None,
        candidate_run_id,
        workspace_path,
        source_root_text,
        patch_path,
        target_files,
        patched_files,
        [],
        "skipped",
        False,
        keep_failed_workspace,
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
    print(f"Candidate run id: {candidate_run_id}")
    print(f"Workspace path: {workspace_path}")
    print("Changed files: none")
    print("No patch to materialize: candidate expected_effect is 'none'.")
    print(f"Main source tree was not modified: {source_root_text}")
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
    target_files: list[str] = []
    patched_files: list[str] = []
    changed_files: list[str] = []
    patch_text = ""

    if not candidate_run_dir.exists() or not candidate_run_dir.is_dir():
        print("Final status: failed")
        print("Failed step: validate_patch_scope")
        print(
            f"ERROR: Candidate run directory not found: {candidate_run_dir}",
            file=sys.stderr,
        )
        print("Workspace removed on failure: False")
        return 1

    validation_started = time.perf_counter()
    try:
        if not candidate_json_path.exists():
            raise FileNotFoundError(f"candidate.json not found: {candidate_json_path}")
        if not patch_path.exists():
            raise FileNotFoundError(f"candidate.diff not found: {patch_path}")

        candidate_data = json.loads(candidate_json_path.read_text(encoding="utf-8-sig"))
        if not isinstance(candidate_data, dict):
            raise ValueError(f"candidate.json must contain a JSON object: {candidate_json_path}")

        target_files = _validate_target_files(candidate_data)
        patch_text = patch_path.read_text(encoding="utf-8")
        patch_has_changes = bool(patch_text.strip())
        patched_files = _parse_patched_files(patch_text) if patch_has_changes else []

        if patch_has_changes:
            if not patched_files:
                raise ValueError(
                    "candidate.diff is non-empty, but no patched file paths could be parsed."
                )
            unexpected_files = [
                patched_file
                for patched_file in patched_files
                if patched_file not in set(target_files)
            ]
            if unexpected_files:
                raise ValueError(
                    "candidate.diff targets files not listed in "
                    "candidate.json['target_files']: "
                    + ", ".join(unexpected_files)
                )
        else:
            if candidate_data.get("expected_effect") == "none":
                validation_duration = round(time.perf_counter() - validation_started, 3)
                steps.append(
                    _step_status(
                        "validate_patch_scope", "success", None, validation_duration
                    )
                )
                return _skip_noop_candidate(
                    candidate_run_dir,
                    candidate_run_id,
                    workspace_path,
                    args.source_root,
                    patch_path,
                    target_files,
                    patched_files,
                    args.keep_failed_workspace,
                    started_at,
                    steps,
                )
            raise ValueError(
                "candidate.diff is empty, but candidate expected_effect is not 'none'."
            )

        validation_duration = round(time.perf_counter() - validation_started, 3)
        steps.append(
            _step_status("validate_patch_scope", "success", None, validation_duration)
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        validation_duration = round(time.perf_counter() - validation_started, 3)
        steps.extend(
            [
                _step_status(
                    "validate_patch_scope", "failed", None, validation_duration
                ),
                _skipped_step("copy_source_tree"),
                _skipped_step("hash_target_files_before_apply"),
                _skipped_step("git_apply_check"),
                _skipped_step("git_apply"),
                _skipped_step("post_apply_verification"),
            ]
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            args.source_root,
            patch_path,
            target_files,
            patched_files,
            changed_files,
            "not_run",
            args.keep_failed_workspace,
            False,
            started_at,
            "validate_patch_scope",
            str(exc),
            steps,
            commands,
        )

    copy_started = time.perf_counter()
    workspace_touched = False
    try:
        if not source_root_path.exists() or not source_root_path.is_dir():
            raise FileNotFoundError(f"Source root not found: {source_root_path}")

        if workspace_path.exists():
            if not args.overwrite:
                raise FileExistsError(
                    f"Candidate workspace already exists: {workspace_path}. "
                    "Use --overwrite to recreate it."
                )
            _ensure_deletable_workspace(workspace_path, workspace_root)
            shutil.rmtree(workspace_path)

        workspace_path.mkdir(parents=True, exist_ok=True)
        workspace_touched = True
        shutil.copytree(source_root_path, workspace_source_path, ignore=_copy_ignore)
        copy_duration = round(time.perf_counter() - copy_started, 3)
        steps.append(_step_status("copy_source_tree", "success", None, copy_duration))
    except (OSError, ValueError) as exc:
        copy_duration = round(time.perf_counter() - copy_started, 3)
        steps.extend(
            [
                _step_status("copy_source_tree", "failed", None, copy_duration),
                _skipped_step("hash_target_files_before_apply"),
                _skipped_step("git_apply_check"),
                _skipped_step("git_apply"),
                _skipped_step("post_apply_verification"),
            ]
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            args.source_root,
            patch_path,
            target_files,
            patched_files,
            changed_files,
            "not_run",
            args.keep_failed_workspace,
            workspace_touched,
            started_at,
            "copy_source_tree",
            str(exc),
            steps,
            commands,
        )

    hash_started = time.perf_counter()
    try:
        before_hashes = _hash_workspace_target_files(workspace_path, target_files)
        hash_duration = round(time.perf_counter() - hash_started, 3)
        steps.append(
            _step_status(
                "hash_target_files_before_apply", "success", None, hash_duration
            )
        )
    except (OSError, ValueError) as exc:
        hash_duration = round(time.perf_counter() - hash_started, 3)
        steps.extend(
            [
                _step_status(
                    "hash_target_files_before_apply", "failed", None, hash_duration
                ),
                _skipped_step("git_apply_check"),
                _skipped_step("git_apply"),
                _skipped_step("post_apply_verification"),
            ]
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            args.source_root,
            patch_path,
            target_files,
            patched_files,
            changed_files,
            "not_run",
            args.keep_failed_workspace,
            True,
            started_at,
            "hash_target_files_before_apply",
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
                _skipped_step("post_apply_verification"),
            ]
        )
        detail = stderr.strip() or stdout.strip() or error_message
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            args.source_root,
            patch_path,
            target_files,
            patched_files,
            changed_files,
            "not_run",
            args.keep_failed_workspace,
            True,
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
        steps.extend(
            [
                _step_status("git_apply", "failed", exit_code, duration),
                _skipped_step("post_apply_verification"),
            ]
        )
        detail = stderr.strip() or stdout.strip() or error_message
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            args.source_root,
            patch_path,
            target_files,
            patched_files,
            changed_files,
            "not_run",
            args.keep_failed_workspace,
            True,
            started_at,
            "git_apply",
            detail,
            steps,
            commands,
        )
    steps.append(_step_status("git_apply", "success", exit_code, duration))

    verification_started = time.perf_counter()
    try:
        after_hashes = _hash_workspace_target_files(workspace_path, target_files)
        changed_files = _detect_changed_files(before_hashes, after_hashes)
        if patch_text.strip() and not changed_files:
            raise ValueError(
                "candidate.diff applied successfully, but no target file hash changed."
            )
        verification_duration = round(time.perf_counter() - verification_started, 3)
        steps.append(
            _step_status(
                "post_apply_verification", "success", None, verification_duration
            )
        )
    except (OSError, ValueError) as exc:
        verification_duration = round(time.perf_counter() - verification_started, 3)
        steps.append(
            _step_status(
                "post_apply_verification", "failed", None, verification_duration
            )
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            args.source_root,
            patch_path,
            target_files,
            patched_files,
            changed_files,
            "failed",
            args.keep_failed_workspace,
            True,
            started_at,
            "post_apply_verification",
            str(exc),
            steps,
            commands,
        )

    materialization = _build_materialization(
        "success",
        None,
        None,
        candidate_run_id,
        workspace_path,
        args.source_root,
        patch_path,
        target_files,
        patched_files,
        changed_files,
        "success",
        False,
        args.keep_failed_workspace,
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
    print(f"Candidate run id: {candidate_run_id}")
    print(f"Workspace path: {workspace_path}")
    print("Changed files:")
    for changed_file in changed_files:
        print(f"- {changed_file}")
    print(f"Main source tree was not modified: {args.source_root}")
    print(f"Artifact log: {candidate_run_dir / 'apply_candidate.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
