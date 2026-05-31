"""Materialize a generated candidate patch into an isolated workspace copy.

This command never modifies the main project source tree. It copies a
base source root into the workspace directory specified by
``--candidate-workspace-dir`` and applies candidate edits only inside that
copy. In the closed-loop flow the workspace lives under
``workspace/experiments/<experiment_id>/candidate_workspaces/<iteration>/``.
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator.core.patching.diff_stats import parse_diff_stats
from orchestrator.core.patching.scope_validation import (
    normalize_repo_path,
    validate_allowed_files_list,
    validate_candidate_scope,
)
from orchestrator.logging_config import configure_logging, get_logger
from orchestrator.shared.io.json_io import read_json

from orchestrator.paths import paths

LOGGER = get_logger(__name__)


EXTERNAL_SCOPE_ENFORCEMENT = "external_allowed_files"


class LineRangeEditApplyError(ValueError):
    """Line-range edit failure carrying compact partial diagnostics."""

    def __init__(self, message: str, results: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.results = results


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply a candidate diff inside an isolated workspace copy."
    )
    parser.add_argument(
        "--candidate-run",
        required=True,
        help="Path to a candidate run directory containing candidate.json.",
    )
    parser.add_argument(
        "--base-source-root",
        required=True,
        help=(
            "Repo-like base source root to copy from. The directory must "
            "contain repo-relative paths such as cpp/external/lambdatwist/p3p.cc. "
            "Its contents are copied directly into the candidate workspace."
        ),
    )
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
    parser.add_argument(
        "--target-file",
        default=None,
        help=(
            "Repo-relative target file path (new schema: all edits apply to this file). "
            "Required when candidate.json has no target_files. "
            "When omitted, target_files are read from candidate.json (legacy)."
        ),
    )
    parser.add_argument(
        "--allowed-file",
        action="append",
        default=None,
        dest="allowed_files",
        help=(
            "Externally allowed file path (may be repeated). "
            "If provided, candidate target_files and diff paths "
            "must be a subset of these allowed files."
        ),
    )
    parser.add_argument(
        "--candidate-workspace-dir",
        required=True,
        help=(
            "Workspace directory for this candidate. This exact path is used as "
            "the isolated copy where edits are applied."
        ),
    )
    return parser.parse_args(argv)


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = paths.repo_root / path
    return path.resolve()


def _resolve_base_source_root(args: argparse.Namespace) -> tuple[Path, str]:
    """Resolve materialization base source root.

    Returns ``(base_source_root_path, base_source_root_display)``.
    """

    base_source_root_path = _resolve_path(args.base_source_root)
    if not base_source_root_path.exists() or not base_source_root_path.is_dir():
        raise ValueError(
            f"Base source root is not a valid directory: {args.base_source_root}"
        )

    return (base_source_root_path, _display_path(base_source_root_path))


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(paths.repo_root).as_posix()
    except ValueError:
        return str(path)


def _normalize_candidate_path(path_text: str) -> str:
    return normalize_repo_path(path_text)


def _resolve_scope_metadata(
    raw_allowed_files: list[str] | None,
    target_files: list[str],
) -> tuple[str, list[str]]:
    if raw_allowed_files is None or not raw_allowed_files:
        raise ValueError(
            "--allowed-file is required. Provide at least one allowed file path."
        )
    return (
        EXTERNAL_SCOPE_ENFORCEMENT,
        validate_allowed_files_list(raw_allowed_files, label="--allowed-file"),
    )


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


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_line_range_edits(
    candidate_data: dict[str, Any], target_files: list[str],
    default_file: str | None = None,
) -> list[dict[str, Any]]:
    if "edits" not in candidate_data:
        raise ValueError("line_range_edits candidate.json is missing required field 'edits'.")

    raw_edits = candidate_data["edits"]
    if not isinstance(raw_edits, list):
        raise ValueError("line_range_edits candidate.json field 'edits' must be a list.")

    expected_effect = candidate_data.get("expected_effect")
    if expected_effect is not None and expected_effect != "none" and not raw_edits:
        raise ValueError(
            "line_range_edits candidate has no edits, but expected_effect is not 'none'."
        )

    target_set = set(target_files)
    validated_edits: list[dict[str, Any]] = []
    for index, edit in enumerate(raw_edits):
        label = f"line_range_edits edit {index}"
        if not isinstance(edit, dict):
            raise ValueError(f"{label} must be a JSON object.")

        raw_file = edit.get("file")
        if isinstance(raw_file, str) and raw_file.strip():
            use_default_file = False
        elif default_file is not None:
            raw_file = default_file
            use_default_file = True
        else:
            raise ValueError(f"{label} field 'file' must be a non-empty string.")
        try:
            edit_file = _normalize_candidate_path(raw_file)
        except ValueError as exc:
            raise ValueError(f"{label} field 'file' is invalid: {exc}") from exc
        if not use_default_file and edit_file not in target_set:
            raise ValueError(
                f"{label} modifies file not listed in candidate.json['target_files']: "
                f"{edit_file}"
            )

        start_line = edit.get("start_line")
        end_line = edit.get("end_line")
        if not _is_positive_int(start_line):
            raise ValueError(f"{label} field 'start_line' must be a positive integer.")
        if not _is_positive_int(end_line):
            raise ValueError(f"{label} field 'end_line' must be a positive integer.")
        if start_line > end_line:
            raise ValueError(f"{label} requires start_line <= end_line.")

        original = edit.get("original")
        replace = edit.get("replace")
        if not isinstance(original, str) or original == "":
            raise ValueError(f"{label} field 'original' must be a non-empty string.")
        if not isinstance(replace, str):
            raise ValueError(f"{label} field 'replace' must be a string.")

        validated_edits.append(
            {
                "index": index,
                "file": edit_file,
                "start_line": start_line,
                "end_line": end_line,
                "original": original,
                "replace": replace,
            }
        )

    return validated_edits


def _unique_files_from_edits(edits: list[dict[str, Any]]) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for edit in edits:
        edit_file = edit["file"]
        if edit_file not in seen:
            files.append(edit_file)
            seen.add(edit_file)
    return files


def _split_preserving_line_endings(text: str) -> list[str]:
    return text.splitlines(keepends=True)


def _range_text_from_lines(lines: list[str], start_line: int, end_line: int) -> str:
    return "".join(lines[start_line - 1 : end_line])


def _replacement_lines(replace: str, selected_text: str) -> list[str]:
    if replace == "":
        return []
    if selected_text.endswith("\r\n") and "\r\n" not in replace:
        replace = replace.replace("\n", "\r\n")
    return _split_preserving_line_endings(replace)


def _content_without_trailing_line_endings(text: str) -> str:
    return "\n".join(line.rstrip("\r\n") for line in text.splitlines(keepends=True))


def _strip_trailing_spaces_tabs_per_line(text: str) -> list[str]:
    return [line.rstrip("\r\n").rstrip(" \t") for line in text.splitlines(keepends=True)]


def _line_range_matches_trailing_whitespace_tolerant(selected_text: str, original: str) -> bool:
    selected_lines = _strip_trailing_spaces_tabs_per_line(selected_text)
    original_lines = _strip_trailing_spaces_tabs_per_line(original)
    return selected_lines == original_lines


def _strip_surrounding_spaces_tabs_per_line(text: str) -> list[str]:
    return [line.rstrip("\r\n").strip(" \t") for line in text.splitlines(keepends=True)]


def _line_range_matches_surrounding_whitespace_tolerant(
    selected_text: str,
    original: str,
) -> bool:
    selected_lines = _strip_surrounding_spaces_tabs_per_line(selected_text)
    original_lines = _strip_surrounding_spaces_tabs_per_line(original)
    return len(selected_lines) == len(original_lines) and selected_lines == original_lines


def _split_line_body_and_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _leading_spaces_tabs(text: str) -> str:
    return text[: len(text) - len(text.lstrip(" \t"))]


def _common_indentation(lines: list[str]) -> str:
    indents: list[str] = []
    for line in lines:
        body, _ending = _split_line_body_and_ending(line)
        if not body.strip(" \t"):
            continue
        indents.append(_leading_spaces_tabs(body))
    if not indents:
        return ""
    common = indents[0]
    for indent in indents[1:]:
        while common and not indent.startswith(common):
            common = common[:-1]
        if not common:
            break
    return common


def _adapt_replacement_indentation_to_actual_source(
    replace: str,
    selected_text: str,
    original: str,
) -> str:
    selected_lines = _split_preserving_line_endings(selected_text)
    original_lines = _split_preserving_line_endings(original)
    replacement = replace
    line_ending = _line_ending_suffix(selected_text)
    if line_ending and replacement and not replacement.endswith(("\n", "\r\n")):
        replacement += line_ending
    replacement_lines = _split_preserving_line_endings(replacement)
    if not replacement_lines:
        return replacement

    selected_nonblank = [
        line for line in selected_lines if _split_line_body_and_ending(line)[0].strip(" \t")
    ]
    original_nonblank = [
        line for line in original_lines if _split_line_body_and_ending(line)[0].strip(" \t")
    ]
    if not selected_nonblank or not original_nonblank:
        raise ValueError("Cannot safely adapt indentation for an all-blank line range.")

    if len(selected_lines) == 1 and len(replacement_lines) == 1:
        actual_indent = _leading_spaces_tabs(_split_line_body_and_ending(selected_lines[0])[0])
        replace_body, replace_ending = _split_line_body_and_ending(replacement_lines[0])
        return actual_indent + replace_body.lstrip(" \t") + replace_ending

    actual_base_indent = _common_indentation(selected_lines)
    replacement_base_indent = _common_indentation(replacement_lines)
    adapted_lines: list[str] = []
    for line in replacement_lines:
        body, ending = _split_line_body_and_ending(line)
        if not body.strip(" \t"):
            adapted_lines.append(ending)
            continue
        if replacement_base_indent and not body.startswith(replacement_base_indent):
            raise ValueError("Replacement indentation is inconsistent with its base indentation.")
        relative_body = body[len(replacement_base_indent) :] if replacement_base_indent else body.lstrip(" \t")
        adapted_lines.append(actual_base_indent + relative_body + ending)
    return "".join(adapted_lines)


def _line_ending_suffix(text: str) -> str:
    if text.endswith("\r\n"):
        return "\r\n"
    if text.endswith("\n"):
        return "\n"
    return ""


def _replacement_lines_for_line_range(replace: str, selected_text: str) -> list[str]:
    if replace == "":
        return []
    line_ending = _line_ending_suffix(selected_text)
    replacement = replace
    if line_ending and not replacement.endswith(("\n", "\r\n")):
        replacement += line_ending
    return _replacement_lines(replacement, selected_text)


def _replace_exactly_once(text: str, original: str, replace: str) -> tuple[str, int]:
    first = text.find(original)
    if first == -1:
        return text, 0
    second = text.find(original, first + max(len(original), 1))
    if second != -1:
        return text, 2
    return text[:first] + replace + text[first + len(original) :], 1


def _line_range_result(edit: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": edit["index"],
        "file": edit["file"],
        "start_line": edit["start_line"],
        "end_line": edit["end_line"],
        "line_range_valid": None,
        "status": "failed",
        "match_mode": "none",
        "method": None,
        "failure_reason": None,
        "fallback_match_count": None,
        "detail": None,
    }


def _fail_line_range_result(
    result: dict[str, Any],
    *,
    failure_reason: str,
    detail: str,
    fallback_match_count: int | None = None,
) -> None:
    result.update(
        {
            "status": "failed",
            "match_mode": "none",
            "method": None,
            "failure_reason": failure_reason,
            "fallback_match_count": fallback_match_count,
            "detail": detail,
        }
    )


def _apply_single_line_range_edit(
    text: str,
    edit: dict[str, Any],
    *,
    allow_exact_search_fallback: bool,
) -> tuple[str, dict[str, Any]]:
    lines = _split_preserving_line_endings(text)
    start_line = edit["start_line"]
    end_line = edit["end_line"]
    result = _line_range_result(edit)

    if start_line > len(lines) or end_line > len(lines):
        selected_text = None
        result["line_range_valid"] = False
    else:
        result["line_range_valid"] = True
        selected_text = _range_text_from_lines(lines, start_line, end_line)
        selected_content = _content_without_trailing_line_endings(selected_text)
        if selected_text == edit["original"] or selected_content == edit["original"]:
            lines[start_line - 1 : end_line] = _replacement_lines_for_line_range(
                edit["replace"], selected_text
            )
            result.update(
                {
                    "method": "line_range",
                    "match_mode": "line_range_exact",
                    "status": "success",
                    "detail": "line range matched original text exactly.",
                }
            )
            return "".join(lines), result

        if _line_range_matches_trailing_whitespace_tolerant(selected_text, edit["original"]):
            lines[start_line - 1 : end_line] = _replacement_lines_for_line_range(
                edit["replace"], selected_text
            )
            result.update(
                {
                    "method": "line_range",
                    "match_mode": "line_range_trailing_whitespace_tolerant",
                    "status": "success",
                    "detail": "line range matched original text after ignoring trailing spaces/tabs.",
                }
            )
            return "".join(lines), result

        if _line_range_matches_surrounding_whitespace_tolerant(selected_text, edit["original"]):
            try:
                adapted_replace = _adapt_replacement_indentation_to_actual_source(
                    edit["replace"], selected_text, edit["original"]
                )
            except ValueError as exc:
                detail = (
                    "line range matched after ignoring leading/trailing spaces/tabs, "
                    f"but replacement indentation could not be adapted safely: {exc}"
                )
                _fail_line_range_result(
                    result,
                    failure_reason="line_range_surrounding_whitespace_mismatch",
                    detail=detail,
                )
                raise LineRangeEditApplyError(detail, [result]) from exc
            lines[start_line - 1 : end_line] = _replacement_lines_for_line_range(
                adapted_replace, selected_text
            )
            result.update(
                {
                    "method": "line_range",
                    "match_mode": "line_range_surrounding_whitespace_tolerant",
                    "status": "success",
                    "detail": "line range matched original text after ignoring leading/trailing spaces/tabs; replacement indentation adapted to actual source.",
                }
            )
            return "".join(lines), result

    if not allow_exact_search_fallback:
        reason = "invalid_line_range" if selected_text is None else "fallback_not_allowed"
        detail = "line range is outside the target file." if selected_text is None else "line range did not match and exact-search fallback is disabled."
        _fail_line_range_result(result, failure_reason=reason, detail=detail)
        raise LineRangeEditApplyError(detail, [result])

    replaced_text, occurrence_count = _replace_exactly_once(
        text, edit["original"], edit["replace"]
    )
    if occurrence_count == 1:
        match_mode = (
            "invalid_line_range_exact_search_fallback"
            if result["line_range_valid"] is False
            else "exact_search_fallback"
        )
        result.update(
            {
                "method": "exact_search_fallback",
                "match_mode": match_mode,
                "status": "success",
                "fallback_match_count": 1,
                "detail": "line range did not match; unique exact-search fallback applied.",
            }
        )
        return replaced_text, result
    if occurrence_count == 0:
        detail = (
            f"edit {edit['index']} for {edit['file']} did not match line range and "
            "original text was not found by exact-search fallback."
        )
        _fail_line_range_result(
            result,
            failure_reason="fallback_no_match",
            detail=detail,
            fallback_match_count=0,
        )
        raise LineRangeEditApplyError(detail, [result])

    detail = (
        f"edit {edit['index']} for {edit['file']} did not match line range and "
        "exact-search fallback is ambiguous because original text occurs multiple times."
    )
    _fail_line_range_result(
        result,
        failure_reason="fallback_ambiguous",
        detail=detail,
        fallback_match_count=occurrence_count,
    )
    raise LineRangeEditApplyError(detail, [result])


def _not_attempted_line_range_result(edit: dict[str, Any]) -> dict[str, Any]:
    result = _line_range_result(edit)
    result.update(
        {
            "line_range_valid": None,
            "status": "not_attempted",
            "match_mode": "none",
            "method": None,
            "failure_reason": "previous_edit_failed",
            "fallback_match_count": None,
            "detail": "Not attempted because a previous edit failed.",
        }
    )
    return result


def _complete_line_range_results_after_failure(
    edits: list[dict[str, Any]],
    partial_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    completed = list(partial_results)
    present_indexes = {result.get("index") for result in completed}
    for edit in edits:
        if edit["index"] not in present_indexes:
            completed.append(_not_attempted_line_range_result(edit))
    return sorted(completed, key=lambda result: result["index"])


def _apply_line_range_edits(
    workspace_path: Path,
    edits: list[dict[str, Any]],
    *,
    allow_exact_search_fallback: bool = True,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for edit in edits:
        grouped.setdefault(edit["file"], []).append(edit)

    results: list[dict[str, Any]] = []
    before_text_by_file: dict[str, str] = {}
    after_text_by_file: dict[str, str] = {}

    for edit_file, file_edits in grouped.items():
        file_path = workspace_path / edit_file
        if not file_path.exists() or not file_path.is_file():
            failed = _line_range_result(sorted(file_edits, key=lambda item: item["index"])[0])
            detail = f"line_range_edits target file not found: {file_path}"
            _fail_line_range_result(
                failed,
                failure_reason="target_file_missing",
                detail=detail,
            )
            complete_results = _complete_line_range_results_after_failure(
                edits,
                [*results, failed],
            )
            raise LineRangeEditApplyError(detail, complete_results)

        original_text = file_path.read_text(encoding="utf-8")
        current_text = original_text
        before_text_by_file[edit_file] = original_text

        for edit in sorted(file_edits, key=lambda item: item["start_line"], reverse=True):
            try:
                current_text, edit_result = _apply_single_line_range_edit(
                    current_text,
                    edit,
                    allow_exact_search_fallback=allow_exact_search_fallback,
                )
            except LineRangeEditApplyError as exc:
                complete_results = _complete_line_range_results_after_failure(
                    edits,
                    [*results, *exc.results],
                )
                raise LineRangeEditApplyError(str(exc), complete_results) from exc
            results.append(edit_result)

        after_text_by_file[edit_file] = current_text
        file_path.write_text(current_text, encoding="utf-8")

    exact_matches = sum(
        1 for result in results if result["match_mode"] == "line_range_exact"
    )
    trailing_whitespace_tolerant_matches = sum(
        1
        for result in results
        if result["match_mode"] == "line_range_trailing_whitespace_tolerant"
    )
    fallback_matches = sum(
        1 for result in results if result["method"] == "exact_search_fallback"
    )
    surrounding_whitespace_tolerant_matches = sum(
        1
        for result in results
        if result["match_mode"] == "line_range_surrounding_whitespace_tolerant"
    )
    return {
        "before_text_by_file": before_text_by_file,
        "after_text_by_file": after_text_by_file,
        "results": sorted(results, key=lambda result: result["index"]),
        "exact_matches": exact_matches,
        "trailing_whitespace_tolerant_matches": trailing_whitespace_tolerant_matches,
        "surrounding_whitespace_tolerant_matches": surrounding_whitespace_tolerant_matches,
        "fallback_matches": fallback_matches,
        "fallback_used": fallback_matches > 0,
        "allow_exact_search_fallback": allow_exact_search_fallback,
    }


def _generate_inspection_diff(
    before_text_by_file: dict[str, str],
    after_text_by_file: dict[str, str],
    output_path: Path,
) -> Path:
    diff_parts: list[str] = []
    for file_path in sorted(before_text_by_file):
        before_text = before_text_by_file[file_path]
        after_text = after_text_by_file[file_path]
        if before_text == after_text:
            continue
        diff_parts.extend(
            getattr(difflib, "unified" + "_diff")(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )
        )
    output_path.write_text("".join(diff_parts), encoding="utf-8")
    return output_path


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
        if name in {"build", "CMakeFiles", "Testing", "CMakeCache.txt", "build.ninja"}:
            ignored.add(name)
        elif any(
            fnmatch.fnmatch(name, pattern)
            for pattern in [
                "build-*",
                "cmake-build-*",
                ".ninja_*",
                "*.exe",
                "*.obj",
                "*.o",
                "*.pdb",
                "*.ilk",
                "*.dll",
                "*.lib",
                "*.a",
            ]
        ):
            ignored.add(name)
    return ignored


def _copy_base_source_tree(
    base_source_root_path: Path,
    workspace_path: Path,
) -> None:
    shutil.copytree(
        base_source_root_path,
        workspace_path,
        ignore=_copy_ignore,
        dirs_exist_ok=True,
    )


def _ensure_deletable_workspace(workspace_path: Path, workspace_root: Path) -> None:
    workspace_path = workspace_path.resolve()
    workspace_root = workspace_root.resolve()
    if workspace_path == workspace_root or workspace_root not in workspace_path.parents:
        raise ValueError(
            f"Refusing to delete workspace outside workspace root: {workspace_path}"
        )


def _default_patch_apply_metadata() -> dict[str, Any]:
    return {
        "patch_apply_strategy": "not_run",
    }


def _build_materialization(
    overall_status: str,
    failed_step: str | None,
    error_message: str | None,
    candidate_run_id: str,
    candidate_run_dir: Path,
    candidate_run_display_id: str | None,
    workspace_path: Path,
    base_source_root: str,
    patch_path: Path,
    target_files: list[str],
    edit_files: list[str],
    changed_files: list[str],
    post_apply_verification: str,
    workspace_removed_on_failure: bool,
    keep_failed_workspace: bool,
    started_at: datetime,
    steps: list[dict[str, Any]],
    scope_enforcement: str,
    allowed_files: list[str],
    patch_apply_strategy: str,
    **extra_metadata: Any,
) -> dict[str, Any]:
    diff_stats = _materialization_diff_stats(patch_path, extra_metadata)
    materialization: dict[str, Any] = {
        "overall_status": overall_status,
        "failed_step": failed_step,
        "error_message": error_message,
        "candidate_run_id": candidate_run_id,
        "candidate_run_dir": _display_path(candidate_run_dir),
        "candidate_run_display_id": candidate_run_display_id or candidate_run_id,
        "workspace_path": _display_path(workspace_path),
        "source_root": base_source_root,
        "base_source_root": base_source_root,
        "patch_file": _display_path(patch_path),
        "target_files": target_files,
        "edit_files": edit_files,
        "changed_files": changed_files,
        "scope_enforcement": scope_enforcement,
        "allowed_files": allowed_files,
        "post_apply_verification": post_apply_verification,
        "patch_apply_strategy": patch_apply_strategy,
        "workspace_removed_on_failure": workspace_removed_on_failure,
        "workspace_retained": workspace_path.exists(),
        "workspace_exists_after_run": workspace_path.exists(),
        "workspace_removal_reason": (
            "materialization_failed" if workspace_removed_on_failure else None
        ),
        "keep_failed_workspace": keep_failed_workspace,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "steps": steps,
        "diff_stats": diff_stats,
    }
    materialization.update(extra_metadata)
    return materialization


def _materialization_diff_stats(
    patch_path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    try:
        diff_text = patch_path.read_text(encoding="utf-8") if patch_path.exists() else ""
    except OSError:
        diff_text = ""
    stats = parse_diff_stats(diff_text)
    stats["edit_count"] = metadata.get("line_range_edit_count")
    stats["fallback_used"] = bool(metadata.get("line_range_fallback_used"))
    return stats


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
        f"Base source root: {materialization.get('base_source_root') or source_root}",
        f"Patch file path: {patch_path}",
        "",
        "Target files:",
        *_format_log_list(materialization["target_files"]),
        "",
        "Files referenced by edits:",
        *_format_log_list(materialization["edit_files"]),
        "",
        f"Scope enforcement: {materialization['scope_enforcement']}",
        "Allowed files:",
        *_format_log_list(materialization["allowed_files"]),
        "",
        "Changed files detected after apply:",
        *_format_log_list(materialization["changed_files"]),
        "",
        f"Post-apply verification: {materialization['post_apply_verification']}",
        f"Patch apply strategy: {materialization['patch_apply_strategy']}",
        f"Line-range edit count: {materialization.get('line_range_edit_count', 'n/a')}",
        "Line-range exact matches: "
        f"{materialization.get('line_range_exact_matches', 'n/a')}",
        "Line-range trailing-whitespace tolerant matches: "
        f"{materialization.get('line_range_trailing_whitespace_tolerant_matches', 'n/a')}",
        "Line-range surrounding-whitespace tolerant matches: "
        f"{materialization.get('line_range_surrounding_whitespace_tolerant_matches', 'n/a')}",
        "Line-range fallback matches: "
        f"{materialization.get('line_range_fallback_matches', 'n/a')}",
        "Line-range fallback used: "
        f"{materialization.get('line_range_fallback_used', 'n/a')}",
        "Generated diff path: "
        f"{materialization.get('generated_diff_path') or 'none'}",
        "Generated diff base: "
        f"{materialization.get('generated_diff_base') or 'none'}",
        f"Workspace removed on failure: {materialization['workspace_removed_on_failure']}",
        f"Keep failed workspace: {materialization['keep_failed_workspace']}",
        "",
        "Commands:",
    ]

    edit_results = materialization.get("line_range_edit_results") or []
    if edit_results:
        lines.extend(["", "Line-range edit results:"])
        for result in edit_results:
            lines.append(
                "- edit {index} {file}:{start_line}-{end_line} "
                "status={status} method={method}".format(**result)
            )
            if result.get("detail"):
                lines.append(f"  detail: {result['detail']}")
        lines.append("")

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
    base_source_root_text: str,
    patch_path: Path,
    target_files: list[str],
    edit_files: list[str],
    changed_files: list[str],
    post_apply_verification: str,
    keep_failed_workspace: bool,
    rollback_workspace: bool,
    started_at: datetime,
    failed_step: str,
    error_message: str,
    steps: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    scope_enforcement: str,
    allowed_files: list[str],
    patch_apply_metadata: dict[str, Any] | None = None,
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
        candidate_run_dir,
        None,
        workspace_path,
        base_source_root_text,
        patch_path,
        target_files,
        edit_files,
        changed_files,
        post_apply_verification,
        workspace_removed_on_failure,
        keep_failed_workspace,
        started_at,
        steps,
        scope_enforcement,
        allowed_files,
        **(patch_apply_metadata or _default_patch_apply_metadata()),
    )
    _write_json(candidate_run_dir / "materialization.json", materialization)
    _write_log(
        candidate_run_dir / "apply_candidate.log",
        candidate_run_id,
        candidate_run_dir,
        workspace_path,
        base_source_root_text,
        patch_path,
        commands,
        materialization,
    )
    LOGGER.info("Final status: failed")
    LOGGER.info("Failed step: %s", failed_step)
    LOGGER.error("ERROR: %s", error_message)
    LOGGER.info("Workspace removed on failure: %s", workspace_removed_on_failure)
    LOGGER.info("Logs saved to: %s", candidate_run_dir / "apply_candidate.log")
    return 1


def _skip_noop_candidate(
    candidate_run_dir: Path,
    candidate_run_id: str,
    workspace_path: Path,
    base_source_root_text: str,
    patch_path: Path,
    target_files: list[str],
    edit_files: list[str],
    keep_failed_workspace: bool,
    started_at: datetime,
    steps: list[dict[str, Any]],
    scope_enforcement: str,
    allowed_files: list[str],
    patch_apply_metadata: dict[str, Any] | None = None,
) -> int:
    steps.extend(
        [
            _skipped_step("copy_source_tree"),
            _skipped_step("hash_target_files_before_apply"),
            _skipped_step("line_range_apply"),
            _skipped_step("post_apply_verification"),
        ]
    )
    materialization = _build_materialization(
        "skipped",
        None,
        None,
        candidate_run_id,
        candidate_run_dir,
        None,
        workspace_path,
        base_source_root_text,
        patch_path,
        target_files,
        edit_files,
        [],
        "skipped",
        False,
        keep_failed_workspace,
        started_at,
        steps,
        scope_enforcement,
        allowed_files,
        **(patch_apply_metadata or _default_patch_apply_metadata()),
    )
    _write_json(candidate_run_dir / "materialization.json", materialization)
    _write_log(
        candidate_run_dir / "apply_candidate.log",
        candidate_run_id,
        candidate_run_dir,
        workspace_path,
        base_source_root_text,
        patch_path,
        [],
        materialization,
    )
    LOGGER.info("Final status: skipped")
    LOGGER.info("Candidate run id: %s", candidate_run_id)
    LOGGER.info("Workspace path: %s", workspace_path)
    LOGGER.info("Changed files: none")
    LOGGER.info("No patch to materialize: candidate has no edits.")
    LOGGER.info("Main source tree was not modified: %s", base_source_root_text)
    LOGGER.info("Logs saved to: %s", candidate_run_dir / "apply_candidate.log")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    started_at = datetime.now().astimezone()
    candidate_run_dir = _resolve_path(args.candidate_run)
    candidate_run_id = candidate_run_dir.name
    workspace_path = _resolve_path(args.candidate_workspace_dir)
    workspace_root = workspace_path.parent
    try:
        base_source_root_path, base_source_root_display = (
            _resolve_base_source_root(args)
        )
    except ValueError as exc:
        LOGGER.info("Final status: failed")
        LOGGER.info("Failed step: parse_args")
        LOGGER.error("ERROR: %s", exc)
        LOGGER.info("Workspace removed on failure: False")
        return 1
    candidate_json_path = candidate_run_dir / "candidate.json"
    patch_path = (candidate_run_dir / "candidate.generated.diff").resolve()

    LOGGER.info("Candidate run id: %s", candidate_run_id)
    LOGGER.info("Workspace path: %s", workspace_path)
    LOGGER.info("Base source root: %s", base_source_root_display)

    steps: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    target_files: list[str] = []
    edit_files: list[str] = []
    changed_files: list[str] = []
    line_range_edits: list[dict[str, Any]] = []
    generated_diff_path: Path | None = None
    generated_diff_created = False
    line_range_apply_result: dict[str, Any] | None = None
    allowed_files: list[str] = []
    patch_apply_metadata = _default_patch_apply_metadata()
    source_root_metadata = {
        "generated_diff_base": None,
    }
    patch_apply_metadata.update(source_root_metadata)

    scope_enforcement = EXTERNAL_SCOPE_ENFORCEMENT
    if not candidate_run_dir.exists() or not candidate_run_dir.is_dir():
        LOGGER.info("Final status: failed")
        LOGGER.info("Failed step: validate_candidate_scope")
        LOGGER.error(
            "ERROR: %s", f"Candidate run directory not found: {candidate_run_dir}"
        )
        LOGGER.info("Workspace removed on failure: False")
        return 1

    validation_started = time.perf_counter()
    try:
        if not candidate_json_path.exists():
            raise FileNotFoundError(f"candidate.json not found: {candidate_json_path}")

        candidate_data = read_json(candidate_json_path)
        if not isinstance(candidate_data, dict):
            raise ValueError(f"candidate.json must contain a JSON object: {candidate_json_path}")

        generated_diff_path = patch_path

        if args.target_file:
            target_files = [_normalize_candidate_path(args.target_file)]
        else:
            target_files = _validate_target_files(candidate_data)
        scope_enforcement, allowed_files = (
            _resolve_scope_metadata(args.allowed_files, target_files)
        )

        line_range_edits = _validate_line_range_edits(
            candidate_data, target_files,
            default_file=args.target_file,
        )
        edit_files = _unique_files_from_edits(line_range_edits)
        validate_candidate_scope(target_files, edit_files, allowed_files)
        patch_apply_metadata.update(
            {
                "line_range_edit_count": len(line_range_edits),
                "line_range_exact_matches": 0,
                "line_range_trailing_whitespace_tolerant_matches": 0,
                "line_range_surrounding_whitespace_tolerant_matches": 0,
                "line_range_fallback_matches": 0,
                "line_range_fallback_used": False,
                "line_range_allow_exact_search_fallback": True,
                "generated_diff_path": None,
                "generated_diff_created": False,
                "line_range_edit_results": [],
            }
        )
        if not line_range_edits:
            validation_duration = round(time.perf_counter() - validation_started, 3)
            steps.append(
                _step_status(
                    "validate_candidate_scope", "success", None, validation_duration
                )
            )
            return _skip_noop_candidate(
                candidate_run_dir,
                candidate_run_id,
                workspace_path,
                base_source_root_display,
                patch_path,
                target_files,
                edit_files,
                args.keep_failed_workspace,
                started_at,
                steps,
                scope_enforcement,
                allowed_files,
                patch_apply_metadata,
            )

        validation_duration = round(time.perf_counter() - validation_started, 3)
        steps.append(
            _step_status("validate_candidate_scope", "success", None, validation_duration)
        )
        LOGGER.info("Patch file path: %s", patch_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        validation_duration = round(time.perf_counter() - validation_started, 3)
        steps.extend(
            [
                _step_status(
                    "validate_candidate_scope", "failed", None, validation_duration
                ),
                _skipped_step("copy_source_tree"),
                _skipped_step("hash_target_files_before_apply"),
                _skipped_step("line_range_apply"),
                _skipped_step("post_apply_verification"),
            ]
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            base_source_root_display,
            patch_path,
            target_files,
            edit_files,
            changed_files,
            "not_run",
            args.keep_failed_workspace,
            False,
            started_at,
            "validate_candidate_scope",
            str(exc),
            steps,
            commands,
            scope_enforcement,
            allowed_files,
            patch_apply_metadata,
        )

    copy_started = time.perf_counter()
    workspace_touched = False
    try:
        if not base_source_root_path.exists() or not base_source_root_path.is_dir():
            raise FileNotFoundError(f"Base source root not found: {base_source_root_path}")

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
        _copy_base_source_tree(base_source_root_path, workspace_path)
        copy_duration = round(time.perf_counter() - copy_started, 3)
        steps.append(_step_status("copy_source_tree", "success", None, copy_duration))
    except (OSError, ValueError) as exc:
        copy_duration = round(time.perf_counter() - copy_started, 3)
        steps.extend(
            [
                _step_status("copy_source_tree", "failed", None, copy_duration),
                _skipped_step("hash_target_files_before_apply"),
                _skipped_step("line_range_apply"),
                _skipped_step("post_apply_verification"),
            ]
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            base_source_root_display,
            patch_path,
            target_files,
            edit_files,
            changed_files,
            "not_run",
            args.keep_failed_workspace,
            workspace_touched,
            started_at,
            "copy_source_tree",
            str(exc),
            steps,
            commands,
            scope_enforcement,
            allowed_files,
            patch_apply_metadata,
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
                _skipped_step("line_range_apply"),
                _skipped_step("post_apply_verification"),
            ]
        )
        return _fail(
            candidate_run_dir,
            candidate_run_id,
            workspace_root,
            workspace_path,
            base_source_root_display,
            patch_path,
            target_files,
            edit_files,
            changed_files,
            "not_run",
            args.keep_failed_workspace,
            True,
            started_at,
            "hash_target_files_before_apply",
            str(exc),
            steps,
            commands,
            scope_enforcement,
            allowed_files,
            patch_apply_metadata,
        )

    if True:
        apply_started = time.perf_counter()
        try:
            line_range_apply_result = _apply_line_range_edits(
                workspace_path,
                line_range_edits,
                allow_exact_search_fallback=True,
            )
            assert generated_diff_path is not None
            _generate_inspection_diff(
                line_range_apply_result["before_text_by_file"],
                line_range_apply_result["after_text_by_file"],
                generated_diff_path,
            )
            generated_diff_created = generated_diff_path.exists()
            apply_duration = round(time.perf_counter() - apply_started, 3)
            steps.extend(
                [
                    _step_status("line_range_apply", "success", None, apply_duration),
                ]
            )
            patch_apply_metadata.update(
                {
                    "patch_apply_strategy": "line_range_edits",
                    "line_range_exact_matches": line_range_apply_result["exact_matches"],
                    "line_range_trailing_whitespace_tolerant_matches": line_range_apply_result[
                        "trailing_whitespace_tolerant_matches"
                    ],
                    "line_range_surrounding_whitespace_tolerant_matches": line_range_apply_result[
                        "surrounding_whitespace_tolerant_matches"
                    ],
                    "line_range_fallback_matches": line_range_apply_result[
                        "fallback_matches"
                    ],
                    "line_range_fallback_used": line_range_apply_result[
                        "fallback_used"
                    ],
                    "line_range_allow_exact_search_fallback": line_range_apply_result[
                        "allow_exact_search_fallback"
                    ],
                    "generated_diff_path": _display_path(generated_diff_path),
                    "generated_diff_created": generated_diff_created,
                    "generated_diff_base": "base_source_root",
                    "line_range_edit_results": line_range_apply_result["results"],
                }
            )
        except (OSError, ValueError) as exc:
            apply_duration = round(time.perf_counter() - apply_started, 3)
            if isinstance(exc, LineRangeEditApplyError):
                patch_apply_metadata["line_range_edit_results"] = sorted(
                    exc.results,
                    key=lambda result: result["index"],
                )
            patch_apply_metadata.update(
                {
                    "patch_apply_strategy": "line_range_edits_failed",
                    "line_range_edit_count": len(line_range_edits),
                    "generated_diff_path": _display_path(generated_diff_path) if generated_diff_created and generated_diff_path is not None else None,
                    "generated_diff_created": generated_diff_created,
                }
            )
            steps.extend(
                [
                    _step_status("line_range_apply", "failed", None, apply_duration),
                    _skipped_step("post_apply_verification"),
                ]
            )
            return _fail(
                candidate_run_dir,
                candidate_run_id,
                workspace_root,
                workspace_path,
                base_source_root_display,
                patch_path,
                target_files,
                edit_files,
                changed_files,
                "not_run",
                args.keep_failed_workspace,
                True,
                started_at,
                "line_range_apply",
                str(exc),
                steps,
                commands,
                scope_enforcement,
                allowed_files,
                patch_apply_metadata,
            )

        verification_started = time.perf_counter()
        try:
            after_hashes = _hash_workspace_target_files(workspace_path, target_files)
            changed_files = _detect_changed_files(before_hashes, after_hashes)
            if line_range_edits and not changed_files:
                raise ValueError(
                    "line_range_edits applied successfully, but no target file hash changed."
                )
            verification_duration = round(time.perf_counter() - verification_started, 3)
            steps.append(
                _step_status(
                    "post_apply_verification", "success", None, verification_duration
                )
            )
        except (OSError, ValueError) as exc:
            verification_duration = round(time.perf_counter() - verification_started, 3)
            patch_apply_metadata["patch_apply_strategy"] = "line_range_edits_failed"
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
                base_source_root_display,
                patch_path,
                target_files,
                edit_files,
                changed_files,
                "failed",
                args.keep_failed_workspace,
                True,
                started_at,
                "post_apply_verification",
                str(exc),
                steps,
                commands,
                scope_enforcement,
                allowed_files,
                patch_apply_metadata,
            )

        materialization = _build_materialization(
            "success",
            None,
            None,
            candidate_run_id,
            candidate_run_dir,
            None,
            workspace_path,
            base_source_root_display,
            patch_path,
            target_files,
            edit_files,
            changed_files,
            "success",
            False,
            args.keep_failed_workspace,
            started_at,
            steps,
            scope_enforcement,
            allowed_files,
            **patch_apply_metadata,
        )
        _write_json(candidate_run_dir / "materialization.json", materialization)
        _write_log(
            candidate_run_dir / "apply_candidate.log",
            candidate_run_id,
            candidate_run_dir,
            workspace_path,
            base_source_root_display,
            patch_path,
            commands,
            materialization,
        )

        LOGGER.info("Final status: success")
        LOGGER.info("Candidate run id: %s", candidate_run_id)
        LOGGER.info("Workspace path: %s", workspace_path)
        LOGGER.info("Changed files:")
        for changed_file in changed_files:
            LOGGER.info("- %s", changed_file)
        LOGGER.info("Generated diff: %s", generated_diff_path)
        LOGGER.info("Base source root was not modified: %s", base_source_root_display)
        LOGGER.info("Artifact log: %s", candidate_run_dir / "apply_candidate.log")
        return 0

if __name__ == "__main__":
    configure_logging()
    raise SystemExit(main())
