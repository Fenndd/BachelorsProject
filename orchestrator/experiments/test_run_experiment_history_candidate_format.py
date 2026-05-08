import unittest

from orchestrator.experiments.experiment_config import HistoryPolicyConfig
from orchestrator.experiments.run_experiment import build_variant_history_context


def _enabled_history_policy() -> HistoryPolicyConfig:
    return HistoryPolicyConfig(
        enabled=True,
        scope="variant",
        max_previous_iterations=1,
        include_failed_iterations=True,
        include_materialization_results=True,
        include_verification_results=True,
    )


def _previous_record() -> dict:
    return {
        "variant_id": "default",
        "variant_iteration": 1,
        "global_iteration": 1,
        "overall_status": "success",
        "generation": {
            "candidate_summary": "previous candidate",
            "risk_level": "low",
            "expected_effect": "runtime",
        },
        "materialization": {"status": "success", "changed_files": []},
        "verification": {"status": "success"},
    }


class RunExperimentHistoryCandidateFormatTest(unittest.TestCase):
    def test_default_history_instruction_uses_empty_unified_diff(self) -> None:
        context, metadata = build_variant_history_context(
            "default",
            [_previous_record()],
            _enabled_history_policy(),
        )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("empty unified_diff", context)
        self.assertNotIn("edits=[]", context)
        self.assertEqual(metadata["previous_iterations_used"], 1)

    def test_unified_diff_history_instruction_uses_empty_unified_diff(self) -> None:
        context, _metadata = build_variant_history_context(
            "default",
            [_previous_record()],
            _enabled_history_policy(),
            candidate_format_type="unified_diff",
        )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("empty unified_diff", context)
        self.assertNotIn("edits=[]", context)

    def test_line_range_history_instruction_uses_empty_edits(self) -> None:
        context, _metadata = build_variant_history_context(
            "default",
            [_previous_record()],
            _enabled_history_policy(),
            candidate_format_type="line_range_edits",
        )

        self.assertIsNotNone(context)
        assert context is not None
        self.assertIn("edits=[]", context)
        self.assertNotIn("empty unified_diff", context)


if __name__ == "__main__":
    unittest.main()