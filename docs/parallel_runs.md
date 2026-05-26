# Parallel Experiment Runs

## Purpose

Experiment runs continue running even when you leave the live output screen.
Multiple experiment runs can be active in parallel. This avoids blocking the
TUI during long optimization experiments.

## Main Components

| Component | Role |
|---|---|
| `ActiveRunsManager` | Central registry for active and recently finished runs. Owned by the TUI app. |
| `ActiveRun` | Per-run state: status, output buffer, cancel event, subscriber callbacks. |
| `ActiveRunScreen` | Live output stream for a single run. |
| `MainScreen` Active Runs panel | Lists all active and recent runs with auto-refresh. |

## Lifecycle

1. **Start** from `ExperimentScreen` (select config + Dry Run / Real Run)
   or from `ConfigBuilderScreen` (Save & Run after paid confirmation).
2. The `ActiveRunsManager` spawns a worker thread that launches the
   experiment subprocess.
3. `ActiveRunScreen` opens and subscribes to stdout/stderr lines and
   status changes. It displays the stream in real time.
4. **Back / Escape** closes the `ActiveRunScreen` but does **not** cancel
   the run. The run continues in the background.
5. A finished run remains visible in the **Active Runs** list on the
   `MainScreen`. You can reopen the screen to review its output.
6. The manager keeps up to **20** most recently finished runs; older ones
   are pruned from the list.

## Cancellation

- The **Cancel** button on `ActiveRunScreen` requests cancellation of the
  subprocess.
- Cancellation is implemented via a `threading.Event` that the worker
  thread checks before starting and during streaming output.
- Process tree termination is **best-effort**:
  - On Windows: `taskkill /PID <pid> /T /F`.
  - On Unix: sends `SIGTERM`, then `SIGKILL` if the process does not stop
    within a short grace period.
- The stdout/stderr buffer remains available after cancellation.

## Quit Guard

Quitting the TUI while active experiment runs exist triggers a
confirmation dialog (`QuitConfirmScreen`):

- The dialog shows the count of active experiment runs.
- **Cancel Runs & Quit**: requests cancellation of all active runs,
  then waits up to 8 seconds for subprocesses to stop before exiting.
- **Stay**: returns to the TUI without quitting.

Legacy baseline processes (managed by `BaselineScreen`'s separate process
counter) are also counted in the quit guard.

## Scope

- `ActiveRunsManager` is for **experiment runs** (dry-run and real runs
  launched from `ExperimentScreen` or `ConfigBuilderScreen`).
- `BaselineScreen` uses a **separate, legacy** process counter
  (`register_process` / `unregister_process`). Baseline runs still block
  the screen until finished; Back and Escape are locked during execution.
  `Ctrl+U` (Force Unlock) is available to recover from stuck baseline
  processes.
