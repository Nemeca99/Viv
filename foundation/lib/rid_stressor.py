"""CPU stress helpers for RID load tests (subprocess — safe on Windows)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List

StressProc = subprocess.Popen[bytes]
_BURN_SCRIPT = Path(__file__).resolve().parent / "stress_burn_worker.py"


def _proc_alive(p: object) -> bool:
    poll = getattr(p, "poll", None)
    if callable(poll):
        return poll() is None
    is_alive = getattr(p, "is_alive", None)
    if callable(is_alive):
        return bool(is_alive())
    return False


def _proc_stop(p: object, timeout: float = 2.0) -> None:
    if not _proc_alive(p):
        return
    terminate = getattr(p, "terminate", None)
    if callable(terminate):
        terminate()
    if isinstance(p, subprocess.Popen):
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=timeout)
    else:
        join = getattr(p, "join", None)
        if callable(join):
            join(timeout=timeout)
            if _proc_alive(p):
                kill = getattr(p, "kill", None)
                if callable(kill):
                    kill()
                join(timeout=timeout)


def cpu_burn() -> None:
    """Inline burn for threads; subprocess workers use stress_burn_worker.py."""
    x = 1.0
    while True:
        x = (x * 1.000001 + 0.000001) % 100000.0


def _popen_flags() -> int:
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    return 0


def start_stressor(cores: int | None = None) -> List[StressProc]:
    n = cores or os.cpu_count() or 8
    procs: List[StressProc] = []
    for _ in range(n):
        p = subprocess.Popen(
            [sys.executable, str(_BURN_SCRIPT)],
            creationflags=_popen_flags(),
        )
        procs.append(p)
    return procs


def stress_alive(procs: List[StressProc]) -> int:
    return sum(1 for p in procs if _proc_alive(p))


def ensure_stressor(procs: List[StressProc], cores: int | None = None) -> List[StressProc]:
    """Restart CPU stress workers if too many died."""
    n = cores or os.cpu_count() or 8
    alive = stress_alive(procs)
    if alive >= max(1, n // 2):
        return procs
    stop_stressor(procs)
    return start_stressor(cores)


def stop_stressor(procs: List[StressProc]) -> None:
    for p in procs:
        _proc_stop(p)
