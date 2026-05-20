"""Execution commands for isolated candidate verification."""

__all__ = ["verify_candidate_main"]


def __getattr__(name: str):
    if name == "verify_candidate_main":
        from .verify_candidate import main

        return main
    raise AttributeError(name)
