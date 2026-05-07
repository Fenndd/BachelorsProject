"""Prompt construction for controlled C++ optimization requests."""

from __future__ import annotations


SUPPORTED_CANDIDATE_TYPES = {"unified_diff", "line_range_edits"}
SUPPORTED_SOURCE_PRESENTATIONS = {"plain", "line_numbered"}


def format_source_plain(source_code: str) -> str:
    """Return source code unchanged for legacy plain prompt presentation."""
    return source_code


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
    candidate_type: str = "unified_diff",
    source_presentation: str = "plain",
) -> tuple[str, str]:
    """Build system and user prompts for one controlled optimization request."""
    if not source_file_path:
        raise ValueError("source_file_path must not be empty.")
    if not source_code:
        raise ValueError("source_code must not be empty.")
    _validate_prompt_mode(candidate_type, source_presentation)

    system_prompt = _build_system_prompt()
    source_for_prompt = _format_source(source_code, source_presentation)
    context_section = additional_context or "No additional context provided."
    user_prompt = "\n".join(
        [
            _build_project_context_section(source_file_path, allowed_files, candidate_type),
            _build_source_section(source_for_prompt, source_presentation),
            _build_additional_context_section(context_section),
            _build_task_and_safety_section(candidate_type),
            _build_output_instructions(candidate_type),
        ]
    )

    return system_prompt, user_prompt


def _validate_prompt_mode(candidate_type: str, source_presentation: str) -> None:
    if candidate_type not in SUPPORTED_CANDIDATE_TYPES:
        raise ValueError(
            "candidate_type must be one of: line_range_edits, unified_diff."
        )
    if source_presentation not in SUPPORTED_SOURCE_PRESENTATIONS:
        raise ValueError("source_presentation must be one of: line_numbered, plain.")
    if candidate_type == "unified_diff" and source_presentation != "plain":
        raise ValueError("candidate_type='unified_diff' requires source_presentation='plain'.")
    if candidate_type == "line_range_edits" and source_presentation != "line_numbered":
        raise ValueError(
            "candidate_type='line_range_edits' requires "
            "source_presentation='line_numbered'."
        )


def _format_source(source_code: str, source_presentation: str) -> str:
    if source_presentation == "plain":
        return format_source_plain(source_code)
    if source_presentation == "line_numbered":
        return format_source_line_numbered(source_code)
    raise ValueError(f"Unsupported source_presentation: {source_presentation!r}")


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
    candidate_type: str,
) -> str:
    allowed_files_list = allowed_files or [source_file_path]
    candidate_reference = (
        "The unified diff and target_files must reference only the allowed files above."
        if candidate_type == "unified_diff"
        else "The edits and target_files must reference only the allowed files above."
    )
    allowed_section_lines = [
        "Allowed files you may modify:",
        *[f"- {allowed_file}" for allowed_file in allowed_files_list],
        "",
        "Hard rule:",
        candidate_reference,
        "Do not modify benchmark, tests, adapters, validator, CMake, orchestrator, configs, docs, or result files.",
    ]
    allowed_section = "\n".join(allowed_section_lines)

    return f"""Project context:
This project is a local experimental pipeline for automated optimization of C++ 3D vision algorithms using LLMs.
The first minimal case study is a P3P solver based on a Lambda Twist baseline.

Target file path:
{source_file_path}

{allowed_section}"""


def _build_source_section(source_for_prompt: str, source_presentation: str) -> str:
    presentation_note = (
        "Source code:"
        if source_presentation == "plain"
        else "Source code with 1-based line numbers for edit targeting:"
    )
    return f"""{presentation_note}
<source_code>
{source_for_prompt}
</source_code>"""


def _build_additional_context_section(context_section: str) -> str:
    return f"""Additional context:
{context_section}"""


def _build_task_and_safety_section(candidate_type: str) -> str:
    format_task_line = (
        "Use a unified diff."
        if candidate_type == "unified_diff"
        else "Use line_range_edits with minimal line ranges."
    )
    external_code_line = (
        "Avoid modifying external baseline code unless the proposed diff is small and clearly justified."
        if candidate_type == "unified_diff"
        else "Avoid modifying external baseline code unless the proposed change is small and clearly justified."
    )
    return f"""Task:
Propose at most one minimal optimization candidate for the target file.
{format_task_line}
Keep the patch minimal.
Avoid changing algorithmic semantics.
Avoid changing expected numerical output.
Do not change public APIs unless explicitly asked.
Avoid broad refactors.
Avoid changing function signatures.
Avoid adding dependencies.
{external_code_line}

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


def _build_output_instructions(candidate_type: str) -> str:
    if candidate_type == "unified_diff":
        return _build_unified_diff_output_instructions()
    if candidate_type == "line_range_edits":
        return _build_line_range_edits_output_instructions()
    raise ValueError(f"Unsupported candidate_type: {candidate_type!r}")


def _build_unified_diff_output_instructions() -> str:
    return """Return exactly one JSON object and nothing else.
Do not wrap the JSON in markdown.
Do not include explanations outside JSON.
Use a real unified diff.
Do not invent fake git index hashes such as "index 1234567..abcdefg".
Prefer unified diff headers and hunks with "--- a/path", "+++ b/path", and "@@ ...".
The diff must target only files listed in target_files.

Required JSON output schema:
{
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
}

Allowed values:
- schema_version: "1.0"
- candidate_type: "unified_diff"
- risk_level: "low", "medium", "high"
- expected_effect: "runtime", "memory", "both", "none"
- requires_manual_review: boolean

If no safe optimization is found:
- set expected_effect to "none"
- set unified_diff to an empty string
- explain why in summary, rationale, and correctness_notes"""


def _build_line_range_edits_output_instructions() -> str:
    return """Return exactly one JSON object and nothing else.
Do not wrap the JSON in markdown.
Do not include explanations outside JSON.
Use edits[] instead of unified_diff.
The edits must target only files listed in target_files.

Line range edit rules:
- start_line and end_line refer to the numbered source shown in the prompt.
- original must contain the exact original source text for that range.
- original must NOT include the "0001 | " line-number prefix.
- replace must contain only the replacement source text.
- For multi-line edits, original and replace may contain newline characters.
- If changing multiple locations is necessary, return multiple edit objects.
- Keep edits minimal.
- The materializer will verify that actual lines start_line..end_line exactly match original before applying.

Required JSON output schema:
{
  "schema_version": "1.1",
  "candidate_type": "line_range_edits",
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
- schema_version: "1.1"
- candidate_type: "line_range_edits"
- risk_level: "low", "medium", "high"
- expected_effect: "runtime", "memory", "both", "none"
- requires_manual_review: boolean

If no safe optimization is found:
- set expected_effect = "none"
- set edits = []
- explain why in summary, rationale, and correctness_notes"""
