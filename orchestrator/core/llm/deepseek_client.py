"""Minimal DeepSeek V4 Flash client using the OpenAI-compatible HTTP API.

This module only sends and parses LLM requests. It does not optimize C++ code,
generate patches, apply patches, compare runs, or call the baseline pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from json import JSONDecodeError
from pathlib import Path
from typing import Any
from urllib import error, request

from .base import LLMConfig, LLMResponse


DEFAULT_SYSTEM_PROMPT = "You are a precise coding assistant. Return concise answers."
DEFAULT_USER_PROMPT = (
    "Return a short JSON object with fields provider, model, and status='ok'."
)


class DeepSeekClientError(RuntimeError):
    """Raised when the DeepSeek client cannot complete a request."""


class DeepSeekClient:
    """Small DeepSeek client for one-off chat completion requests."""

    def __init__(self, config: LLMConfig) -> None:
        """Create a client from a validated LLM configuration."""
        self.config = config

    @classmethod
    def from_config_file(cls, config_path: Path | str) -> "DeepSeekClient":
        """Load client configuration from a JSON file."""
        return cls(_load_config(config_path))

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send one chat completion request and return a parsed response."""
        api_key = os.environ.get(self.config.api_key_env)
        if not api_key:
            raise DeepSeekClientError(
                f"Missing API key environment variable: {self.config.api_key_env}"
            )

        payload = self._build_payload(system_prompt, user_prompt)
        raw_response = self._post_chat_completion(payload, api_key)
        return self._parse_response(raw_response)

    def _build_payload(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "reasoning_effort": self.config.reasoning_effort,
        }

        if self.config.thinking_enabled:
            payload["thinking"] = {"type": "enabled"}
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens

        return payload

    def _post_chat_completion(
        self, payload: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        endpoint = f"{self.config.base_url.rstrip('/')}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with request.urlopen(http_request, timeout=600) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise DeepSeekClientError(
                f"DeepSeek API HTTP error {exc.code}: {error_body}"
            ) from exc
        except error.URLError as exc:
            raise DeepSeekClientError(f"DeepSeek API request failed: {exc}") from exc

        try:
            parsed = json.loads(response_body)
        except JSONDecodeError as exc:
            raise DeepSeekClientError(
                f"DeepSeek API returned invalid JSON: {exc}"
            ) from exc

        if not isinstance(parsed, dict):
            raise DeepSeekClientError("DeepSeek API response JSON was not an object.")
        return parsed

    def _parse_response(self, raw_response: dict[str, Any]) -> LLMResponse:
        try:
            choices = raw_response["choices"]
            message = choices[0]["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekClientError(
                "DeepSeek API response is missing choices[0].message.content."
            ) from exc

        if not isinstance(content, str):
            raise DeepSeekClientError(
                "DeepSeek API response field choices[0].message.content is not a string."
            )

        reasoning_content = message.get("reasoning_content")
        if reasoning_content is not None and not isinstance(reasoning_content, str):
            raise DeepSeekClientError(
                "DeepSeek API response field choices[0].message.reasoning_content "
                "is not a string."
            )

        return LLMResponse(
            provider=self.config.provider,
            model=self.config.model,
            content=content,
            reasoning_content=reasoning_content,
            raw_response=raw_response,
        )


def _load_config(config_path: Path | str) -> LLMConfig:
    path = Path(config_path)
    if not path.exists():
        raise DeepSeekClientError(f"LLM config file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise DeepSeekClientError(f"Invalid JSON in LLM config {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise DeepSeekClientError(f"LLM config must be a JSON object: {path}")

    thinking = data.get("thinking", {})
    if not isinstance(thinking, dict):
        raise DeepSeekClientError("LLM config field 'thinking' must be an object.")

    try:
        provider = _require_string(data, "provider")
        model = _require_string(data, "model")
        base_url = _require_string(data, "base_url")
        api_key_env = _require_string(data, "api_key_env")
        thinking_enabled = thinking.get("enabled", False)
        reasoning_effort = thinking.get("effort", "high")
        max_tokens = data.get("max_tokens")
    except KeyError as exc:
        raise DeepSeekClientError(f"Missing required LLM config field: {exc}") from exc

    if not isinstance(thinking_enabled, bool):
        raise DeepSeekClientError("LLM config field 'thinking.enabled' must be a boolean.")
    if not isinstance(reasoning_effort, str) or not reasoning_effort:
        raise DeepSeekClientError(
            "LLM config field 'thinking.effort' must be a non-empty string."
        )
    if max_tokens is not None and (
        not isinstance(max_tokens, int) or isinstance(max_tokens, bool)
    ):
        raise DeepSeekClientError("LLM config field 'max_tokens' must be an integer.")

    return LLMConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        api_key_env=api_key_env,
        thinking_enabled=thinking_enabled,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
    )


def _require_string(data: dict[str, Any], field_name: str) -> str:
    value = data[field_name]
    if not isinstance(value, str) or not value:
        raise DeepSeekClientError(
            f"LLM config field '{field_name}' must be a non-empty string."
        )
    return value


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual DeepSeek LLM smoke test.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the DeepSeek LLM JSON config file.",
    )
    parser.add_argument(
        "--system",
        default=DEFAULT_SYSTEM_PROMPT,
        help="System prompt to send to the model.",
    )
    parser.add_argument(
        "--user",
        default=DEFAULT_USER_PROMPT,
        help="User prompt to send to the model.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run a small manual DeepSeek smoke test."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        client = DeepSeekClient.from_config_file(args.config)
        response = client.complete(
            system_prompt=args.system,
            user_prompt=args.user,
        )
    except DeepSeekClientError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Provider: {response.provider}")
    print(f"Model: {response.model}")
    print("Content:")
    print(response.content)
    print(f"Reasoning content present: {response.reasoning_content is not None}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
