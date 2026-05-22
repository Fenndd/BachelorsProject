"""CLI wrapper for candidate benchmark-family verification.

The public command intentionally remains:

    py -m orchestrator.core.execution.verify_candidate --candidate-run ...

The implementation verifies a materialized candidate in its isolated workspace
with the same smoke, adapter validator, family benchmark, and benchmark parser
path used by baseline automation. It does not compare candidates or select a
best candidate.
"""

from __future__ import annotations

from .candidate_benchmark_verification import main


if __name__ == "__main__":
    raise SystemExit(main())
