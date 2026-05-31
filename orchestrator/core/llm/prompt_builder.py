"""Prompt construction for controlled C++ optimization requests."""

from __future__ import annotations

PROMPT_VERSION = "2.0-minimal"
CANDIDATE_SCHEMA_VERSION = "2.0-minimal"


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
    source_code: str,
    additional_context: str | None = None,
) -> tuple[str, str]:
    """Build system and user prompts for one controlled optimization request."""
    if not source_code:
        raise ValueError("source_code must not be empty.")

    system_prompt = _build_system_prompt()
    source_for_prompt = format_source_line_numbered(source_code)

    user_prompt = "\n\n".join(
        [
            _build_task_section(),
            _build_additional_context_section(additional_context),
            _build_source_section(source_for_prompt),
            _build_safety_section(),
            _build_line_edit_rules_section(),
            _build_output_schema_section(),
        ]
    )

    return system_prompt, user_prompt


def _build_system_prompt() -> str:
    return (
        "You are a careful C++ numerical optimization assistant. "
        "Propose one small, local optimization candidate for the provided solver source code. "
        "Preserve numerical correctness, solver semantics, public APIs, and expected output behavior. "
        "Return only valid JSON matching the requested schema. Do not use markdown or prose outside JSON."
    )


def _build_task_section() -> str:
    return (
        "Task:\n"
        "Improve computational efficiency under the automated benchmark while preserving "
        "correctness and numerical behavior.\n"
        "Propose at most one minimal local optimization candidate.\n"
        "If no safe improvement is available, return edits = []."
    )


def _build_additional_context_section(additional_context: str | None) -> str:
    context_text = additional_context or "No additional user guidance."
    return f"User guidance / additional context:\n{context_text}"


def _build_source_section(source_for_prompt: str) -> str:
    return (
        "Source code with 1-based line numbers for edit targeting:\n"
        "<source_code>\n"
        f"{source_for_prompt}\n"
        "</source_code>"
    )


def _build_safety_section() -> str:
    return (
        "Safety constraints:\n"
        "- Preserve solver semantics, public API, output semantics, tolerances, "
        "root-selection logic, degeneracy handling, and sign checks.\n"
        "- Treat Eigen expressions as lazy: do not remove .eval(), add .noalias(), "
        "or bind references to Eigen temporaries unless clearly alias-safe and lifetime-safe.\n"
        "- Do not reorder floating-point computations when numerical stability may be affected."
    )


def _build_line_edit_rules_section() -> str:
    return (
        "Line edit rules:\n"
        "- start_line and end_line must use the line numbers shown before the \"|\" separator.\n"
        "- original must exactly match the selected source lines, without line-number prefixes.\n"
        "- replace must contain only replacement source text.\n"
        "- Keep edits minimal.\n"
        "- Return edits = [] if no safe optimization is available."
    )


def _build_output_schema_section() -> str:
    return (
        "Required JSON output schema:\n"
        "{\n"
        '  "summary": "Short summary of the proposed change.",\n'
        '  "rationale": "Why this may improve computational efficiency.",\n'
        '  "correctness_notes": "Why solver behavior should remain unchanged.",\n'
        '  "edits": [\n'
        "    {\n"
        '      "start_line": 1,\n'
        '      "end_line": 1,\n'
        '      "original": "exact original source text",\n'
        '      "replace": "replacement source text"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "\n"
        "No-op candidate (when no safe optimization is found):\n"
        "{\n"
        '  "summary": "No safe local optimization found.",\n'
        '  "rationale": "No change appears safe or useful.",\n'
        '  "correctness_notes": "No code changes proposed.",\n'
        '  "edits": []\n'
        "}"
    )
