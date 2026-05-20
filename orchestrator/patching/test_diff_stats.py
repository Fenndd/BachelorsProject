from __future__ import annotations

from orchestrator.patching.diff_stats import parse_diff_stats


def test_parse_diff_stats_counts_only_real_changes() -> None:
    diff_text = """diff --git a/cpp/a.cc b/cpp/a.cc
--- a/cpp/a.cc
+++ b/cpp/a.cc
@@ -1,4 +1,5 @@
 context
-old line
+new line
+added line
 unchanged
diff --git a/cpp/b.cc b/cpp/b.cc
--- a/cpp/b.cc
+++ b/cpp/b.cc
@@ -10,3 +10,2 @@
-removed line
 kept
"""

    stats = parse_diff_stats(diff_text)

    assert stats == {
        "files_changed": 2,
        "lines_added": 2,
        "lines_removed": 2,
        "changed_blocks": 2,
    }
