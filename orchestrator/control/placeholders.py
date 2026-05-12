"""User-facing placeholder messages for not-yet-integrated controls."""

BASELINE_RUN = (
    "Baseline launcher integration is not connected in this control layer yet. "
    "The existing baseline entry point remains orchestrator/cli/main.py."
)
EXPERIMENT_RUN = (
    "Experiment subprocess integration will be added later. This command only "
    "validates the selected config path for now."
)
RESULTS_BROWSE = (
    "Results browsing is a placeholder in this first TUI skeleton. Use the "
    "results/latest CLI command for a best-effort summary."
)
ENVIRONMENT = (
    "Environment inspection and .env.local management are placeholders for a "
    "future step."
)
DOCTOR = (
    "Full doctor validation is not implemented yet. This command currently "
    "reports only basic repository, git, and directory status."
)
WORKSPACE = (
    "Workspace management actions are placeholders. This skeleton only reports "
    "basic workspace presence and counts."
)
