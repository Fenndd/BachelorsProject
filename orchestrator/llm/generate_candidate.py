"""Manual command for generating one LLM optimization candidate.

This command reads one source file, asks the configured LLM for a controlled
optimization candidate, validates the JSON response, and saves artifacts. It
does not apply patches or modify source files.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from orchestrator.llm.deepseek_client import DeepSeekClient, DeepSeekClientError
from orchestrator.llm.mock_client import MockLLMClient, MockLLMClientError
from orchestrator.llm.prompt_builder import build_optimization_prompt
from orchestrator.llm.response_parser import (
    OptimizationCandidate,
    parse_optimization_candidate,
)
from orchestrator.patching.scope_validation import (
    normalize_repo_path,
    validate_allowed_files_list,
)
from orchestrator.storage import RunStorage


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAX_SOURCE_CHARS = 120000


def _configure_text_streams() -> None:
    """Make console output tolerant of Unicode on Windows consoles."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, TypeError):
            continue


def _safe_print(*values: Any, file: Any | None = None, **kwargs: Any) -> None:
    """Print without allowing UnicodeEncodeError to fail candidate generation."""

    output = sys.stdout if file is None else file
    try:
        print(*values, file=output, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(value) for value in values)
        encoding = getattr(output, "encoding", None) or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_text, file=output, **kwargs)


class CandidateGenerationFailure(RuntimeError):
    """Controlled failure with a stable step name for saved status artifacts."""

    def __init__(self, failed_step: str, error_message: str) -> None:
        super().__init__(error_message)
        self.failed_step = failed_step
        self.error_message = error_message


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one LLM optimization candidate without applying it."
    )
    parser.add_argument("--config", required=True, help="Path to the LLM config JSON.")
    parser.add_argument("--source", required=True, help="Path to the target source file.")
    parser.add_argument(
        "--source-root",
        default=None,
        help=(
            "Physical root directory to read --source from. Defaults to the "
            "repository root. When provided, --source must be a repo-relative "
            "logical path."
        ),
    )
    parser.add_argument(
        "--context",
        default=None,
        help="Optional extra context to include in the optimization prompt.",
    )
    parser.add_argument(
        "--max-source-chars",
        type=int,
        default=DEFAULT_MAX_SOURCE_CHARS,
        help="Maximum source file size in characters.",
    )
    parser.add_argument(
        "--allowed-file",
        action="append",
        default=None,
        dest="allowed_files",
        help=(
            "File path the LLM is allowed to modify (may be repeated). "
            "Defaults to the --source path if not provided."
        ),
    )
    parser.add_argument(
        "--candidate-type",
        choices=["unified_diff", "line_range_edits"],
        default="unified_diff",
        help="Candidate edit format to request from the LLM.",
    )
    parser.add_argument(
        "--source-presentation",
        choices=["plain", "line_numbered"],
        default="plain",
        help="Source presentation format to use in the optimization prompt.",
    )
    return parser.parse_args(argv)


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _resolve_source_root(source_root_text: str | None) -> Path:
    if source_root_text is None:
        return REPO_ROOT
    return _resolve_path(source_root_text)


def _resolve_logical_target_file(
    source_text: str,
    source_root_provided: bool,
) -> str:
    """Resolve --source to the repo-relative logical target path.

    With a custom source root, --source is intentionally required to be logical
    and repo-relative so the physical source location cannot leak into the LLM
    prompt or candidate target paths.
    """
    source_path = Path(source_text)
    if source_root_provided and source_path.is_absolute():
        raise CandidateGenerationFailure(
            "parse_args",
            "--source must be a repo-relative logical path when --source-root is provided.",
        )

    if source_path.is_absolute():
        try:
            return source_path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError as exc:
            raise CandidateGenerationFailure(
                "parse_args",
                f"Absolute --source must be inside the repository root: {source_path}",
            ) from exc

    try:
        return normalize_repo_path(source_text)
    except ValueError as exc:
        raise CandidateGenerationFailure(
            "parse_args", f"Invalid --source value: {exc}"
        ) from exc


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _run_git_command(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _repository_info() -> dict[str, Any]:
    git_commit = _run_git_command(["rev-parse", "HEAD"])
    git_branch = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
    git_status = _run_git_command(["status", "--porcelain"])
    return {
        "git_commit": git_commit or "unknown",
        "git_branch": git_branch or "unknown",
        "dirty_worktree": None if git_status is None else bool(git_status),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _read_source(source_path: Path, max_source_chars: int) -> str:
    if max_source_chars <= 0:
        raise ValueError("--max-source-chars must be greater than zero.")
    if not source_path.exists():
        raise FileNotFoundError(f"Target source file not found: {source_path}")
    if not source_path.is_file():
        raise ValueError(f"Target source path is not a file: {source_path}")

    source_code = source_path.read_text(encoding="utf-8")
    if len(source_code) > max_source_chars:
        raise ValueError(
            f"Target source file has {len(source_code)} characters, "
            f"which exceeds --max-source-chars={max_source_chars}."
        )
    return source_code


def _build_metadata(
    run_id: str,
    target_file: str,
    source_root: str,
    physical_source_path: str,
    client: DeepSeekClient | None,
    started_at: datetime,
    candidate_format: dict[str, str],
) -> dict[str, Any]:
    config = client.config if client is not None else None
    return {
        "run_id": run_id,
        "scenario": "llm_candidate",
        "target_file": target_file,
        "source_root": source_root,
        "physical_source_path": physical_source_path,
        "provider": config.provider if config else "unknown",
        "model": config.model if config else "unknown",
        "thinking_enabled": config.thinking_enabled if config else None,
        "reasoning_effort": config.reasoning_effort if config else None,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": None,
        "candidate_format": candidate_format,
        "repository": _repository_info(),
    }


def _build_status(
    overall_status: str,
    failed_step: str | None,
    error_message: str | None,
    candidate_format: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "overall_status": overall_status,
        "failed_step": failed_step,
        "error_message": error_message,
        "candidate_format": candidate_format,
    }


def _build_summary(
    run_dir: Path,
    metadata: dict[str, Any],
    status: dict[str, Any],
    candidate: OptimizationCandidate | None,
) -> str:
    lines = [
        f"Run: {metadata['run_id']}",
        "Scenario: llm_candidate",
        f"Target file: {metadata['target_file']}",
        f"Provider: {metadata['provider']}",
        f"Model: {metadata['model']}",
        f"Candidate format: {metadata['candidate_format']['type']}",
        f"Source presentation: {metadata['candidate_format']['source_presentation']}",
        f"Overall status: {status['overall_status']}",
        f"Failed step: {status['failed_step'] or 'none'}",
        f"Error message: {status['error_message'] or 'none'}",
        f"Started at: {metadata['started_at']}",
        f"Finished at: {metadata['finished_at']}",
    ]

    if candidate is not None:
        field_summary = _candidate_field_summary(candidate)
        lines.extend(
            [
                f"Candidate summary: {candidate.summary}",
                f"Risk level: {candidate.risk_level}",
                f"Expected effect: {candidate.expected_effect}",
                f"Target files: {', '.join(candidate.target_files)}",
                f"Candidate type: {field_summary['candidate_type']}",
            ]
        )
        if candidate.candidate_type == "line_range_edits":
            lines.extend(
                [
                    f"Structured edits count: {field_summary['structured_edit_count']}",
                    f"Candidate edits present: {field_summary['candidate_edits_present']}",
                ]
            )
        else:
            lines.append(f"Unified diff present: {field_summary['unified_diff_present']}")
    else:
        lines.append("Candidate summary: none")

    lines.extend(["", f"Artifact directory: {_display_path(run_dir)}", ""])
    return "\n".join(lines)


def _candidate_field_summary(candidate: OptimizationCandidate) -> dict[str, Any]:
    structured_edit_count = len(candidate.edits) if candidate.candidate_type == "line_range_edits" else None
    return {
        "candidate_type": candidate.candidate_type,
        "structured_edit_count": structured_edit_count,
        "candidate_edits_present": bool(structured_edit_count),
        "unified_diff_present": bool(candidate.unified_diff),
    }


def _build_index_record(
    metadata: dict[str, Any],
    status: dict[str, Any],
    candidate: OptimizationCandidate | None,
    run_dir: Path,
) -> dict[str, Any]:
    candidate_fields = _candidate_field_summary(candidate) if candidate is not None else {
        "candidate_type": None,
        "structured_edit_count": None,
        "candidate_edits_present": None,
        "unified_diff_present": False,
    }
    return {
        "run_id": metadata["run_id"],
        "scenario": "llm_candidate",
        "overall_status": status["overall_status"],
        "failed_step": status["failed_step"],
        "error_message": status["error_message"],
        "started_at": metadata["started_at"],
        "finished_at": metadata["finished_at"],
        "provider": metadata["provider"],
        "model": metadata["model"],
        "candidate_format": metadata["candidate_format"],
        "target_file": metadata["target_file"],
        "risk_level": candidate.risk_level if candidate is not None else None,
        "expected_effect": candidate.expected_effect if candidate is not None else None,
        "candidate_type": candidate_fields["candidate_type"],
        "structured_edit_count": candidate_fields["structured_edit_count"],
        "candidate_edits_present": candidate_fields["candidate_edits_present"],
        "unified_diff_present": candidate_fields["unified_diff_present"],
        "requires_manual_review": (
            candidate.requires_manual_review if candidate is not None else None
        ),
        "run_dir": _display_path(run_dir),
    }


def _save_final_artifacts(
    storage: RunStorage,
    run_dir: Path,
    metadata: dict[str, Any],
    status: dict[str, Any],
    candidate: OptimizationCandidate | None,
) -> Path:
    metadata["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    storage.save_metadata(run_dir, metadata)
    storage.save_status(run_dir, status)
    storage.save_summary(run_dir, _build_summary(run_dir, metadata, status, candidate))
    return storage.append_index_record(
        _build_index_record(metadata, status, candidate, run_dir)
    )


def _save_candidate_artifacts(run_dir: Path, candidate: OptimizationCandidate) -> None:
    _write_json(run_dir / "candidate.json", asdict(candidate))
    if candidate.candidate_type == "unified_diff":
        _write_text(run_dir / "candidate.diff", candidate.unified_diff)
    elif candidate.candidate_type == "line_range_edits":
        _write_json(run_dir / "candidate.edits.json", {"edits": asdict(candidate)["edits"]})
    else:
        raise ValueError(f"Unsupported candidate_type: {candidate.candidate_type}")


def _print_final_summary(
    status: dict[str, Any],
    run_dir: Path | None,
    candidate: OptimizationCandidate | None,
) -> None:
    if run_dir is not None:
        _safe_print(f"CANDIDATE_RUN_DIR={_display_path(run_dir)}")

    _safe_print(f"Final status: {status['overall_status']}")
    if status["overall_status"] == "success" and candidate is not None:
        field_summary = _candidate_field_summary(candidate)
        _safe_print(f"Candidate summary: {candidate.summary}")
        _safe_print(f"Risk level: {candidate.risk_level}")
        _safe_print(f"Expected effect: {candidate.expected_effect}")
        _safe_print(f"Candidate type: {field_summary['candidate_type']}")
        if candidate.candidate_type == "line_range_edits":
            _safe_print(f"Structured edits count: {field_summary['structured_edit_count']}")
            _safe_print(f"Candidate edits present: {field_summary['candidate_edits_present']}")
        else:
            _safe_print(f"Unified diff present: {field_summary['unified_diff_present']}")
    else:
        _safe_print(f"Failed step: {status['failed_step']}")
        _safe_print(f"Error message: {status['error_message']}")

    if run_dir is not None:
        _safe_print(f"Artifacts saved to: {_display_path(run_dir)}")


def _classify_client_response_error(error_message: str) -> str:
    response_markers = [
        "returned invalid json",
        "response json",
        "response field",
        "missing choices",
        "choices[0].message.content",
    ]
    lowered = error_message.lower()
    if any(marker in lowered for marker in response_markers):
        return "parse_response"
    return "llm_request"


def _load_config_provider(config_path: Path) -> str:
    if not config_path.exists():
        raise CandidateGenerationFailure(
            "load_config", f"LLM config file not found: {config_path}"
        )
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise CandidateGenerationFailure(
            "load_config", f"Invalid JSON in LLM config {config_path}: {exc}"
        ) from exc
    except OSError as exc:
        raise CandidateGenerationFailure(
            "load_config", f"Could not read LLM config {config_path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise CandidateGenerationFailure(
            "load_config", f"LLM config must be a JSON object: {config_path}"
        )
    provider = payload.get("provider")
    if not isinstance(provider, str) or not provider:
        raise CandidateGenerationFailure(
            "load_config", "LLM config field 'provider' must be a non-empty string."
        )
    return provider


def _load_client(config_path: Path) -> Any:
    provider = _load_config_provider(config_path)
    if provider == "deepseek":
        try:
            return DeepSeekClient.from_config_file(config_path)
        except DeepSeekClientError as exc:
            raise CandidateGenerationFailure("load_config", str(exc)) from exc
    if provider == "mock":
        try:
            return MockLLMClient.from_config_file(config_path)
        except MockLLMClientError as exc:
            raise CandidateGenerationFailure("load_config", str(exc)) from exc
    raise CandidateGenerationFailure(
        "load_config", f"Unsupported LLM provider: {provider!r}"
    )


def _create_run_directory(storage: RunStorage, run_id: str) -> Path | None:
    try:
        return storage.create_run_directory("llm_candidate", run_id)
    except OSError as exc:
        status = _build_status("failed", "create_run_directory", str(exc))
        _print_final_summary(status, None, None)
        return None


def _resolve_allowed_files(
    raw_allowed_files: list[str] | None,
    target_file: str,
) -> list[str]:
    """Resolve, validate, and normalize the allowed-files list.

    If no allowed files are provided, fall back to [target_file] for backward
    compatibility. Each path is normalized to a forward-slash POSIX relative
    repo path.
    """
    if raw_allowed_files is None or not raw_allowed_files:
        return [target_file]

    try:
        return validate_allowed_files_list(
            raw_allowed_files,
            label="--allowed-file",
        )
    except ValueError as exc:
        raise CandidateGenerationFailure(
            "parse_args", f"Invalid --allowed-file value(s): {exc}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    _configure_text_streams()
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config_path = _resolve_path(args.config)
    source_root = _resolve_source_root(args.source_root)
    try:
        target_file = _resolve_logical_target_file(
            args.source,
            source_root_provided=args.source_root is not None,
        )
    except CandidateGenerationFailure as exc:
        status = _build_status("failed", exc.failed_step, exc.error_message)
        _print_final_summary(status, None, None)
        return 1
    source_path = (source_root / target_file).resolve()
    source_root_display = _display_path(source_root)
    physical_source_path_display = _display_path(source_path)
    candidate_format = {
        "type": args.candidate_type,
        "source_presentation": args.source_presentation,
    }

    # Resolve allowed files early
    allowed_files = _resolve_allowed_files(args.allowed_files, target_file)
    print(f"Allowed files for LLM: {', '.join(allowed_files)}")

    storage = RunStorage(REPO_ROOT / "results")
    started_at = datetime.now().astimezone()
    run_id = storage.build_run_id("llm_candidate", started_at)
    run_dir = _create_run_directory(storage, run_id)
    if run_dir is None:
        return 1

    print(f"Target file: {target_file}")
    print(f"Source root: {source_root_display}")
    print(f"Physical source path: {physical_source_path_display}")
    print(f"Run directory: {run_dir}")

    client: DeepSeekClient | None = None
    metadata = _build_metadata(
        run_id,
        target_file,
        source_root_display,
        physical_source_path_display,
        client,
        started_at,
        candidate_format,
    )
    candidate: OptimizationCandidate | None = None

    status: dict[str, Any]
    try:
        client = _load_client(config_path)

        metadata = _build_metadata(
            run_id,
            target_file,
            source_root_display,
            physical_source_path_display,
            client,
            started_at,
            candidate_format,
        )
        print(f"Provider/model: {client.config.provider}/{client.config.model}")

        try:
            source_code = _read_source(source_path, args.max_source_chars)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise CandidateGenerationFailure("read_source", str(exc)) from exc

        system_prompt, user_prompt = build_optimization_prompt(
            source_file_path=target_file,
            source_code=source_code,
            additional_context=args.context,
            allowed_files=allowed_files,
            candidate_type=args.candidate_type,
            source_presentation=args.source_presentation,
        )

        try:
            _write_json(
                run_dir / "llm_request.json",
                {
                    "target_file": target_file,
                    "source_root": source_root_display,
                    "physical_source_path": physical_source_path_display,
                    "allowed_files": allowed_files,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "additional_context": args.context,
                    "candidate_format": candidate_format,
                },
            )
        except OSError as exc:
            raise CandidateGenerationFailure("save_artifacts", str(exc)) from exc

        try:
            response = client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except (DeepSeekClientError, MockLLMClientError) as exc:
            failed_step = _classify_client_response_error(str(exc))
            raise CandidateGenerationFailure(failed_step, str(exc)) from exc

        try:
            _write_json(
                run_dir / "llm_response.json",
                {
                    "provider": response.provider,
                    "model": response.model,
                    "content": response.content,
                    "reasoning_content": response.reasoning_content,
                    "raw_response": response.raw_response,
                },
            )
        except OSError as exc:
            raise CandidateGenerationFailure("save_artifacts", str(exc)) from exc

        try:
            candidate = parse_optimization_candidate(response.content)
        except ValueError as exc:
            raise CandidateGenerationFailure("parse_response", str(exc)) from exc

        try:
            _save_candidate_artifacts(run_dir, candidate)
        except OSError as exc:
            raise CandidateGenerationFailure("save_artifacts", str(exc)) from exc

        status = _build_status("success", None, None, candidate_format)
    except CandidateGenerationFailure as exc:
        status = _build_status("failed", exc.failed_step, exc.error_message, candidate_format)

    try:
        index_path = _save_final_artifacts(storage, run_dir, metadata, status, candidate)
    except OSError as exc:
        status = _build_status("failed", "save_artifacts", str(exc), candidate_format)
        _print_final_summary(status, run_dir, candidate)
        return 1

    print(f"[Index] Appended run record to {_display_path(index_path)}")
    _print_final_summary(status, run_dir, candidate)
    return 0 if status["overall_status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
