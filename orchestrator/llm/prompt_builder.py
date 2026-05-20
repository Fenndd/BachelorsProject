"""Prompt construction for controlled C++ optimization requests."""

from __future__ import annotations


def format_source_line_numbered(source_code: str) -> str:
    """Format source code with 1-based, 4-digit line numbers for prompts only.

    Real empty lines inside the source are preserved. A trailing newline does not
    create an additional artificial numbered empty line.
    """
    return "\n".join(
        f"{line_number:04d} | {line}"
        for line_number, line in enumerate(source_code.splitlines(), start=1)
    )


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

    system_prompt = _build_system_prompt()
    source_for_prompt = format_source_line_numbered(source_code)
    context_section = additional_context or "No additional context provided."
    user_prompt = "\n".join(
        [
            _build_project_context_section(source_file_path, allowed_files),
            _build_source_section(source_for_prompt),
            _build_additional_context_section(context_section),
            _build_task_and_safety_section(),
            _build_output_instructions(),
        ]
    )

    return system_prompt, user_prompt


def _build_system_prompt() -> str:
    return (
        "You are a careful C++ optimization assistant. "
        "Preserve numerical correctness and expected numerical output. "
        "Treat Eigen aliasing, lazy evaluation, temporary lifetime, and "
        "expression-template behavior as safety-critical. "
        "Do not change public APIs unless explicitly asked. "
        "Prefer small, local, low-risk optimizations. "
        "Return only valid JSON. Do not use markdown. "
        "Do not include prose outside the JSON object."
    )


def _build_project_context_section(
    source_file_path: str,
    allowed_files: list[str] | None,
) -> str:
    allowed_files_list = allowed_files or [source_file_path]
    allowed_section_lines = [
        "Allowed files you may modify:",
        *[f"- {allowed_file}" for allowed_file in allowed_files_list],
        "",
        "Hard rule:",
        "The edits and target_files must reference only the allowed files above.",
        "Do not modify benchmark, tests, adapters, validator, CMake, orchestrator, configs, docs, or result files.",
    ]
    allowed_section = "\n".join(allowed_section_lines)

    return f"""Project context:
This project is a local experimental pipeline for automated optimization of C++ 3D vision algorithms using LLMs.
The first minimal case study is a P3P solver based on a Lambda Twist baseline.

Target file path:
{source_file_path}

{allowed_section}"""


def _build_source_section(source_for_prompt: str) -> str:
    return f"""Source code with 1-based line numbers for edit targeting:
<source_code>
{source_for_prompt}
</source_code>"""


def _build_additional_context_section(context_section: str) -> str:
    return f"""Additional context:
{context_section}"""


def _build_task_and_safety_section() -> str:
    return f"""Task:
Propose at most one minimal optimization candidate for the target file.
Use edits[] with minimal line ranges.
Keep the patch minimal.
Avoid changing algorithmic semantics.
Avoid changing expected numerical output.
Do not change public APIs unless explicitly asked.
Avoid broad refactors.
Avoid changing function signatures.
Avoid adding dependencies.
Avoid modifying external baseline code unless the proposed change is small and clearly justified.

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
- Do not replace mathematically sensitive operations with approximations."""


def _build_output_instructions() -> str:
    return """Return exactly one JSON object and nothing else.
Do not wrap the JSON in markdown.
Do not include explanations outside JSON.
The edits must target only files listed in target_files.

Line range edit rules:
- start_line and end_line refer to the numbered source shown in the prompt.
- Line numbers are the integer labels shown before the "|" separator in the source block.
- Use those exact shown line labels as start_line and end_line.
- Do not offset, expand, infer, or transform line numbers.
- If the same code appears multiple times, target the intended occurrence by its exact shown line range.
- For repeated code blocks, include enough original lines to make the edit unambiguous.
- original must contain the exact original source text for that range.
- original must NOT include the "0001 | " line-number prefix.
- original must preserve the exact source text from the selected lines, excluding only the line-number prefix.
- replace must contain only the replacement source text.
- For multi-line edits, original and replace may contain newline characters.
- If changing multiple locations is necessary, return multiple edit objects.
- Keep edits minimal.
- The materializer will verify that actual lines start_line..end_line match original before applying. Exact text is required; trailing spaces at line ends may be tolerated by the materializer, but do not rely on this.

Required JSON output schema:
{
  "summary": "Short summary of the proposed optimization.",
  "rationale": "Why this change may improve performance.",
  "risk_level": "low",
  "expected_effect": "runtime",
  "target_files": [
    "relative/path/to/file.cpp"
  ],
  "correctness_notes": "Why the numerical behavior should remain unchanged.",
  "edits": [
    {
      "file": "relative/path/to/file.cpp",
      "start_line": 1,
      "end_line": 1,
      "original": "exact original text from the source, without line-number prefixes",
      "replace": "replacement text"
    }
  ],
  "requires_manual_review": true
}

Allowed values:
- risk_level: "low", "medium", "high"
- expected_effect: "runtime", "memory", "both", "none"
- requires_manual_review: boolean

If no safe optimization is found:
- set expected_effect = "none"
- set edits = []
- explain why in summary, rationale, and correctness_notes"""
