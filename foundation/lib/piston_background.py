"""Background piston tick — runs on its own thread without blocking the main loop."""
from __future__ import annotations

import json
import threading
import time
from typing import Any

from lib.piston_engine import PISTON_STATE_PATH

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop = threading.Event()
_interval_s = 1.0
_journal = False
_beats = 0


def _loop() -> None:
    global _beats
    from lib.piston_engine import piston_pulse

    while not _stop.is_set():
        t0 = time.monotonic()
        try:
            piston_pulse(journal=_journal)
            _beats += 1
        except Exception:
            pass
        sleep_s = _interval_s - (time.monotonic() - t0)
        if sleep_s > 0 and not _stop.wait(sleep_s):
            continue
        if _stop.is_set():
            break


def start_piston_background(*, interval: float = 1.0, journal: bool = False) -> bool:
    """Start daemon piston thread. Returns False if already running."""
    global _thread, _interval_s, _journal, _beats
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _interval_s = max(0.25, float(interval))
        _journal = journal
        _beats = 0
        _stop.clear()
        _thread = threading.Thread(
            target=_loop,
            name="viv-piston-bg",
            daemon=True,
        )
        _thread.start()
        return True


def stop_piston_background(*, timeout: float = 3.0) -> int:
    """Stop background piston. Returns beats completed this session."""
    global _thread, _beats
    with _lock:
        _stop.set()
        t = _thread
    if t is not None and t.is_alive():
        t.join(timeout=timeout)
    with _lock:
        beats = _beats
        _thread = None
    return beats


def piston_background_running() -> bool:
    with _lock:
        return _thread is not None and _thread.is_alive()


def read_piston_snapshot() -> dict[str, Any]:
    """Read latest piston state without ticking — for non-blocking main loops."""
    if not PISTON_STATE_PATH.is_file():
        return {"available": False}
    try:
        data = json.loads(PISTON_STATE_PATH.read_text(encoding="utf-8"))
        pkg = float(data.get("package_s_n", 0))
        beat = int(data.get("beat", 0))
        budget = float(data.get("package_budget_pct", 100))
        firing = data.get("firing_order") or []
        active = ",".join(str(c) for c in firing)
        return {
            "available": True,
            "beat": beat,
            "package_s_n": round(pkg, 4),
            "cpu_budget_pct": budget,
            "state_path": str(PISTON_STATE_PATH),
            "line": (
                f"[PISTON] beat={beat} firing=[{active}] "
                f"pkg_S_n={pkg:.3f} cpu_budget={budget:.0f}%"
            ),
            "background": piston_background_running(),
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {"available": False, "error": "read_failed"}
