"""Offline mock LLM client for deterministic candidate-generation tests.

The mock client never reads API keys and never performs network requests. It
loads a predefined optimization candidate JSON object and returns it through the
same LLMResponse shape used by real provider clients.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .base import LLMConfig, LLMResponse
from orchestrator.paths import paths


class MockLLMClientError(RuntimeError):
    """Raised when the mock LLM client cannot load a configured response."""


class MockLLMClient:
    """Deterministic offline LLM client backed by a JSON response file."""

    def __init__(self, config: LLMConfig, response_file: Path) -> None:
        """Create a mock client from a validated config and response path."""
        self.config = config
        self.response_file = response_file

    @classmethod
    def from_config_file(cls, config_path: Path | str) -> "MockLLMClient":
        """Load mock client configuration from a JSON file."""
        path = Path(config_path)
        data = _read_json_object(path, "LLM config")

        provider = _require_string(data, "provider")
        if provider != "mock":
            raise MockLLMClientError(
                f"Mock LLM config provider must be 'mock', got {provider!r}."
            )

        model = _require_string(data, "model")
        response_file_text = _require_string(data, "mock_response_file")
        response_file = Path(response_file_text)
        if not response_file.is_absolute():
            config_relative_response_file = path.parent / response_file
            response_file = (
                config_relative_response_file
                if config_relative_response_file.exists()
                else paths.repo_root / response_file
            )
        response_file = response_file.resolve()
        if not response_file.exists():
            raise MockLLMClientError(f"Mock response file not found: {response_file}")
        if not response_file.is_file():
            raise MockLLMClientError(f"Mock response path is not a file: {response_file}")

        thinking = data.get("thinking", {})
        if thinking is None:
            thinking = {}
        if not isinstance(thinking, dict):
            raise MockLLMClientError("LLM config field 'thinking' must be an object.")

        thinking_enabled = thinking.get("enabled", False)
        reasoning_effort = thinking.get("effort", "none")
        max_tokens = data.get("max_tokens")
        if not isinstance(thinking_enabled, bool):
            raise MockLLMClientError("LLM config field 'thinking.enabled' must be a boolean.")
        if not isinstance(reasoning_effort, str) or not reasoning_effort:
            raise MockLLMClientError(
                "LLM config field 'thinking.effort' must be a non-empty string."
            )
        if max_tokens is not None and (
            not isinstance(max_tokens, int) or isinstance(max_tokens, bool)
        ):
            raise MockLLMClientError("LLM config field 'max_tokens' must be an integer.")

        return cls(
            config=LLMConfig(
                provider=provider,
                model=model,
                base_url=str(data.get("base_url", "")),
                api_key_env=str(data.get("api_key_env", "")),
                thinking_enabled=thinking_enabled,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
            ),
            response_file=response_file,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Return the configured mock candidate as an LLMResponse."""
        candidate = _read_json_object(self.response_file, "mock response")
        content = json.dumps(candidate, ensure_ascii=False)
        raw_response = {
            "id": "mock-candidate-response",
            "object": "chat.completion.mock",
            "provider": self.config.provider,
            "model": self.config.model,
            "mock_response_file": str(self.response_file),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                        "reasoning_content": None,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_chars": len(system_prompt) + len(user_prompt),
                "completion_chars": len(content),
            },
        }
        return LLMResponse(
            provider=self.config.provider,
            model=self.config.model,
            content=content,
            reasoning_content=None,
            raw_response=raw_response,
        )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise MockLLMClientError(f"{label} file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except JSONDecodeError as exc:
        raise MockLLMClientError(f"Invalid JSON in {label} {path}: {exc}") from exc
    except OSError as exc:
        raise MockLLMClientError(f"Could not read {label} {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise MockLLMClientError(f"{label} must be a JSON object: {path}")
    return payload


def _require_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise MockLLMClientError(
            f"LLM config field '{field_name}' must be a non-empty string."
        )
    return value
