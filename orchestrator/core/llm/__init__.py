"""LLM client interfaces and provider adapters."""

from .base import LLMConfig, LLMResponse

__all__ = [
    "LLMConfig",
    "LLMResponse",
    "DeepSeekClient",
    "MockLLMClient",
    "OptimizationCandidate",
    "build_optimization_prompt",
    "parse_optimization_candidate",
    "generate_candidate_main",
]


def __getattr__(name: str) -> object:
    """Load provider clients lazily so modules can also run with `python -m`."""
    if name == "DeepSeekClient":
        from .deepseek_client import DeepSeekClient

        return DeepSeekClient
    if name == "MockLLMClient":
        from .mock_client import MockLLMClient

        return MockLLMClient
    if name == "OptimizationCandidate":
        from .response_parser import OptimizationCandidate

        return OptimizationCandidate
    if name == "build_optimization_prompt":
        from .prompt_builder import build_optimization_prompt

        return build_optimization_prompt
    if name == "parse_optimization_candidate":
        from .response_parser import parse_optimization_candidate

        return parse_optimization_candidate
    if name == "generate_candidate_main":
        from .generate_candidate import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
