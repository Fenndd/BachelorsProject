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
from orchestrator.storage import RunStorage


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAX_SOURCE_CHARS = 120000


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
    client: DeepSeekClient | None,
    started_at: datetime,
) -> dict[str, Any]:
    config = client.config if client is not None else None
    return {
        "run_id": run_id,
        "scenario": "llm_candidate",
        "target_file": target_file,
        "provider": config.provider if config else "unknown",
        "model": config.model if config else "unknown",
        "thinking_enabled": config.thinking_enabled if config else None,
        "reasoning_effort": config.reasoning_effort if config else None,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": None,
        "repository": _repository_info(),
    }


def _build_status(
    overall_status: str,
    failed_step: str | None,
    error_message: str | None,
) -> dict[str, Any]:
    return {
        "overall_status": overall_status,
        "failed_step": failed_step,
        "error_message": error_message,
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
        f"Overall status: {status['overall_status']}",
        f"Failed step: {status['failed_step'] or 'none'}",
        f"Error message: {status['error_message'] or 'none'}",
        f"Started at: {metadata['started_at']}",
        f"Finished at: {metadata['finished_at']}",
    ]

    if candidate is not None:
        lines.extend(
            [
                f"Candidate summary: {candidate.summary}",
                f"Risk level: {candidate.risk_level}",
                f"Expected effect: {candidate.expected_effect}",
                f"Target files: {', '.join(candidate.target_files)}",
                f"Unified diff present: {bool(candidate.unified_diff)}",
            ]
        )
    else:
        lines.append("Candidate summary: none")

    lines.extend(["", f"Artifact directory: {_display_path(run_dir)}", ""])
    return "\n".join(lines)


def _build_index_record(
    metadata: dict[str, Any],
    status: dict[str, Any],
    candidate: OptimizationCandidate | None,
    run_dir: Path,
) -> dict[str, Any]:
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
        "target_file": metadata["target_file"],
        "risk_level": candidate.risk_level if candidate is not None else None,
        "expected_effect": candidate.expected_effect if candidate is not None else None,
        "unified_diff_present": bool(candidate and candidate.unified_diff),
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


def _print_final_summary(
    status: dict[str, Any],
    run_dir: Path | None,
    candidate: OptimizationCandidate | None,
) -> None:
    print(f"Final status: {status['overall_status']}")
    if status["overall_status"] == "success" and candidate is not None:
        print(f"Candidate summary: {candidate.summary}")
        print(f"Risk level: {candidate.risk_level}")
        print(f"Expected effect: {candidate.expected_effect}")
        print(f"Unified diff present: {bool(candidate.unified_diff)}")
    else:
        print(f"Failed step: {status['failed_step']}")
        print(f"Error message: {status['error_message']}")

    if run_dir is not None:
        print(f"Artifacts saved to: {_display_path(run_dir)}")
        print(f"CANDIDATE_RUN_DIR={_display_path(run_dir)}")


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


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    config_path = _resolve_path(args.config)
    source_path = _resolve_path(args.source)
    target_file = _display_path(source_path)

    storage = RunStorage(REPO_ROOT / "results")
    started_at = datetime.now().astimezone()
    run_id = storage.build_run_id("llm_candidate", started_at)
    run_dir = _create_run_directory(storage, run_id)
    if run_dir is None:
        return 1

    print(f"Target file: {target_file}")
    print(f"Run directory: {run_dir}")

    client: DeepSeekClient | None = None
    metadata = _build_metadata(run_id, target_file, client, started_at)
    candidate: OptimizationCandidate | None = None

    status: dict[str, Any]
    try:
        client = _load_client(config_path)

        metadata = _build_metadata(run_id, target_file, client, started_at)
        print(f"Provider/model: {client.config.provider}/{client.config.model}")

        try:
            source_code = _read_source(source_path, args.max_source_chars)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise CandidateGenerationFailure("read_source", str(exc)) from exc

        system_prompt, user_prompt = build_optimization_prompt(
            source_file_path=target_file,
            source_code=source_code,
            additional_context=args.context,
        )

        try:
            _write_json(
                run_dir / "llm_request.json",
                {
                    "target_file": target_file,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "additional_context": args.context,
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
            _write_json(run_dir / "candidate.json", asdict(candidate))
            _write_text(run_dir / "candidate.diff", candidate.unified_diff)
        except OSError as exc:
            raise CandidateGenerationFailure("save_artifacts", str(exc)) from exc

        status = _build_status("success", None, None)
    except CandidateGenerationFailure as exc:
        status = _build_status("failed", exc.failed_step, exc.error_message)

    try:
        index_path = _save_final_artifacts(storage, run_dir, metadata, status, candidate)
    except OSError as exc:
        status = _build_status("failed", "save_artifacts", str(exc))
        _print_final_summary(status, run_dir, candidate)
        return 1

    print(f"[Index] Appended run record to {_display_path(index_path)}")
    _print_final_summary(status, run_dir, candidate)
    return 0 if status["overall_status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
