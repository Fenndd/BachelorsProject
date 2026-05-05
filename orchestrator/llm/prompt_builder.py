"""Prompt construction for controlled C++ optimization requests."""

from __future__ import annotations


def build_optimization_prompt(
    source_file_path: str,
    source_code: str,
    additional_context: str | None = None,
    allowed_files: list[str] | None = None,
) -> tuple[str, str]:
    """Build system and user prompts for one controlled optimization request."""
    if not source_file_path:
        raise ValueError("source_file_path must not be empty.")
    if not source_code:
        raise ValueError("source_code must not be empty.")

    system_prompt = (
        "You are a careful C++ optimization assistant. "
        "Preserve numerical correctness and expected numerical output. "
        "Treat Eigen aliasing, lazy evaluation, temporary lifetime, and "
        "expression-template behavior as safety-critical. "
        "Do not change public APIs unless explicitly asked. "
        "Prefer small, local, low-risk optimizations. "
        "Return only valid JSON. Do not use markdown. "
        "Do not include prose outside the JSON object."
    )

    _allowed_files_list = allowed_files or [source_file_path]
    allowed_section_lines = [
        "Allowed files you may modify:",
    ]
    for af in _allowed_files_list:
        allowed_section_lines.append(f"- {af}")
    allowed_section_lines.extend([
        "",
        "Hard rule:",
        "The unified diff and target_files must reference only the allowed files above.",
        "Do not modify benchmark, tests, adapters, validator, CMake, orchestrator, configs, docs, or result files.",
        "",
    ])
    allowed_section = "\n".join(allowed_section_lines)

    context_section = additional_context or "No additional context provided."
    user_prompt = f"""Project context:
This project is a local experimental pipeline for automated optimization of C++ 3D vision algorithms using LLMs.
The first minimal case study is a P3P solver based on a Lambda Twist baseline.

Target file path:
{source_file_path}

{allowed_section}
Source code:
<source_code>
{source_code}
</source_code>

Additional context:
{context_section}

Task:
Propose at most one minimal optimization candidate for the target file.
Use a unified diff.
Keep the patch minimal.
Avoid changing algorithmic semantics.
Avoid changing expected numerical output.
Do not change public APIs unless explicitly asked.
Avoid broad refactors.
Avoid changing function signatures.
Avoid adding dependencies.
Avoid modifying external baseline code unless the proposed diff is small and clearly justified.

Eigen safety rules:
- Do not remove .eval() from Eigen expressions when the same object may appear on the left-hand side and right-hand side of an assignment.
- Do not remove .eval() from inverse, transpose, block, segment, or expression-template assignments unless the change is clearly alias-safe.
- If aliasing, lazy evaluation, temporary lifetime, or expression-template behavior is involved, treat the optimization as unsafe unless it is obviously safe.
- Do not use .noalias() unless it is mathematically and structurally guaranteed that there is no aliasing.

Numerical correctness rules:
- Preserve algorithmic semantics.
- Preserve numerical behavior.
- Do not change tolerances, Newton iteration counts, root-selection logic, discriminant handling, sign checks, or degeneracy handling unless explicitly requested.
- Do not reorder floating-point computations if that could affect numerical stability.
- Do not replace mathematically sensitive operations with approximations.

Return exactly one JSON object and nothing else.
Do not wrap the JSON in markdown.
Do not include explanations outside JSON.
Use a real unified diff.
Do not invent fake git index hashes such as "index 1234567..abcdefg".
Prefer unified diff headers and hunks with "--- a/path", "+++ b/path", and "@@ ...".
The diff must target only files listed in target_files.

Required JSON output schema:
{{
  "schema_version": "1.0",
  "candidate_type": "unified_diff",
  "summary": "Short summary of the proposed optimization.",
  "rationale": "Why this change may improve performance.",
  "risk_level": "low",
  "expected_effect": "runtime",
  "target_files": [
    "relative/path/to/file.cpp"
  ],
  "correctness_notes": "Why the numerical behavior should remain unchanged.",
  "unified_diff": "diff --git ...",
  "requires_manual_review": true
}}

Allowed values:
- schema_version: "1.0"
- candidate_type: "unified_diff"
- risk_level: "low", "medium", "high"
- expected_effect: "runtime", "memory", "both", "none"
- requires_manual_review: boolean

If no safe optimization is found:
- set expected_effect to "none"
- set unified_diff to an empty string
- explain why in summary, rationale, and correctness_notes
"""

    return system_prompt, user_prompt
