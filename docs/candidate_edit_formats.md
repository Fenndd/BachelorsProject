# Candidate Edit Schema

The project uses one built-in LLM candidate representation: structured line-range edits.

This is fixed infrastructure behavior, not an experiment configuration option.

## Current Flow

- The LLM receives the target source with 1-based line numbers.
- The LLM returns a JSON object containing `edits[]`.
- Each edit contains `start_line`, `end_line`, `original`, and `replace`.
- The materializer verifies that `original` matches the selected source range before applying the replacement.
- The materializer may use its internal exact-search fallback when a line range does not match but the original text appears exactly once.
- After applying edits, the system writes `candidate.generated.diff` as an inspection artifact.

## Candidate JSON Shape

```json
{
  "summary": "Short summary of the proposed optimization.",
  "rationale": "Why this change may improve performance.",
  "correctness_notes": "Why numerical behavior should remain unchanged.",
  "edits": [
    {
      "start_line": 1,
      "end_line": 1,
      "original": "exact source text without line-number prefixes",
      "replace": "replacement source text"
    }
  ]
}
```

- An edit does not contain a `file` field. The target file is known from the orchestrator
  experiment config and is passed to the materializer via `--target-file`. All edits
  apply to that single target file.

- If no safe optimization is available, the candidate returns `edits: []` (a no-op candidate).

## Materialization Metadata

The file `materialization.json` contains `target_files` and `edit_files` as
orchestrator-generated metadata (not LLM input). These are derived from the
`--target-file` CLI argument and the edits applied.
