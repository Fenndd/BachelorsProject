"""Shared dataclasses for LLM provider clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    """Configuration needed to call an LLM provider."""

    provider: str
    model: str
    base_url: str
    api_key_env: str
    thinking_enabled: bool
    reasoning_effort: str
    max_tokens: int | None


@dataclass(frozen=True)
class LLMResponse:
    """Parsed response returned by an LLM provider."""

    provider: str
    model: str
    content: str
    reasoning_content: str | None
    raw_response: dict[str, Any]
