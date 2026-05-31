"""Windows-only candidate evaluation queue for closed-loop experiments."""

from __future__ import annotations

import errno
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from orchestrator.paths import get_project_paths

if os.name == "nt":
    import msvcrt
else:  # pragma: no cover - exercised only on non-Windows platforms
    msvcrt = None  # type: ignore[assignment]


LOCK_RELATIVE_PATH = Path("locks") / "candidate_evaluation.lock"
WAIT_LOG_INTERVAL_SECONDS = 60.0
RETRY_SLEEP_SECONDS = 1.0


@contextmanager
def candidate_evaluation_lock(
    *,
    experiment_id: str,
    iteration: int,
    workspace_root: Path | str | None = None,
) -> Iterator[None]:
    """Serialize candidate evaluation across Windows experiment processes."""

    if os.name != "nt" or msvcrt is None:
        raise RuntimeError("The candidate evaluation queue is currently Windows-only.")

    workspace = Path(workspace_root) if workspace_root is not None else get_project_paths().workspace
    lock_path = workspace / LOCK_RELATIVE_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock_file = lock_path.open("a+b")
    locked = False
    try:
        lock_file.seek(0, 2)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)

        wait_started_at: float | None = None
        next_wait_log_at: float | None = None
        while True:
            try:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
                print(f"Acquired candidate evaluation queue lock. experiment={experiment_id}, iteration={iteration}")
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EDEADLK):
                    raise
                now = time.monotonic()
                if wait_started_at is None:
                    wait_started_at = now
                    next_wait_log_at = now + WAIT_LOG_INTERVAL_SECONDS
                    print(f"Waiting for candidate evaluation queue lock... experiment={experiment_id}, iteration={iteration}")
                elif next_wait_log_at is not None and now >= next_wait_log_at:
                    print(f"Still waiting for candidate evaluation queue lock... experiment={experiment_id}, iteration={iteration}")
                    next_wait_log_at = now + WAIT_LOG_INTERVAL_SECONDS
                time.sleep(RETRY_SLEEP_SECONDS)

        yield
    finally:
        try:
            if locked:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                print(f"Released candidate evaluation queue lock. experiment={experiment_id}, iteration={iteration}")
        finally:
            lock_file.close()
