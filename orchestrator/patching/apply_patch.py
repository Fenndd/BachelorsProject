"""Compatibility note for patch application.

The current Step 9 implementation lives in
orchestrator.patching.materialize_candidate. That command materializes generated
candidate diffs into isolated workspace copies and never modifies the main
project source tree.

This module is kept as a lightweight compatibility marker for the broader future
patching API; it is not the primary command for applying candidate patches.
"""
