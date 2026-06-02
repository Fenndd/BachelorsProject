# Parallel Experiment Runs

Experiment runs launched from the TUI are **non-blocking** — they continue in
the background even when you leave the live output screen. Multiple runs can
be active in parallel.

The **Active Runs** panel on the MainScreen lists all active and recently
finished runs. Click a run to reopen its live output. Leaving the
ActiveRunScreen does **not** cancel the run.

Quitting the TUI while experiment runs are active shows a confirmation dialog.
Cancelling all runs on quit will stop background subprocesses before exiting.

For command-line equivalents, see [docs/usage.md](usage.md).
