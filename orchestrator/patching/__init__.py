"""Patch materialization helpers for candidate workspaces."""

__all__ = ["materialize_candidate_main"]


def __getattr__(name: str) -> object:
    """Load command entry points lazily so modules can run with `python -m`."""
    if name == "materialize_candidate_main":
        from .materialize_candidate import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
