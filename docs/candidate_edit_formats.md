# Candidate Edit Schema

The project uses one built-in LLM candidate representation: structured line-range edits.

This is fixed infrastructure behavior, not an experiment configuration option.

## Current Flow

- The LLM receives the target source with 1-based line numbers.
- The LLM returns a JSON object containing `edits[]`.
- Each edit contains `file`, `start_line`, `end_line`, `original`, and `replace`.
- The materializer verifies that `original` matches the selected source range before applying the replacement.
- The materializer may use its internal exact-search fallback when a line range does not match but the original text appears exactly once.
- After applying edits, the system writes `candidate.generated.diff` as an inspection artifact.

## Candidate JSON Shape

```json
{
  "summary": "Short summary of the proposed optimization.",
  "rationale": "Why this change may improve performance.",
  "risk_level": "low",
  "expected_effect": "runtime",
  "target_files": ["relative/path/to/file.cpp"],
  "correctness_notes": "Why numerical behavior should remain unchanged.",
  "edits": [
    {
      "file": "relative/path/to/file.cpp",
      "start_line": 1,
      "end_line": 1,
      "original": "exact source text without line-number prefixes",
      "replace": "replacement source text"
    }
  ],
  "requires_manual_review": true
}
```

If no safe optimization is available, the candidate sets `expected_effect` to `none` and returns `edits: []`.
