"""CLI wrapper for the current narrow candidate smoke verifier.

The public command intentionally remains:

    py -m orchestrator.execution.verify_candidate --candidate-run ...

The implementation lives in candidate_smoke_verification.py to make it clear
that this is a Step 9, smoke-test-only verifier, not the future general
candidate execution pipeline.
"""

from __future__ import annotations

from .candidate_smoke_verification import main


if __name__ == "__main__":
    raise SystemExit(main())
