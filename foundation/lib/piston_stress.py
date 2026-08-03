"""Piston-controlled CPU stress — affinity burners on active cores per pair."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from lib.piston_engine import PistonController, PistonState, write_piston_state
from lib.rid_stressor import StressProc, _popen_flags, stop_stressor, stress_alive

_BURN_SCRIPT_PATH = Path(__file__).resolve().parent / "stress_burn_worker.py"


class PistonStressFleet:
    """One subprocess burner per core pair, pinned via PistonController swaps."""

    def __init__(self, controller: PistonController | None = None) -> None:
        self.ctl = controller or PistonController()
        self.burners: dict[int, StressProc] = {}
        self.last_state: PistonState | None = None
        self.swaps_total = 0

    def start(self) -> int:
        self.stop()
        exe = sys.executable
        for pair_idx in range(len(self.ctl.pairs)):
            proc = subprocess.Popen(
                [exe, str(_BURN_SCRIPT_PATH)],
                creationflags=_popen_flags(),
            )
            self.burners[pair_idx] = proc
            core = self.ctl.active_by_pair[pair_idx]
            self.ctl.set_affinity(proc.pid, core)
        return stress_alive(list(self.burners.values()))

    def tick(self, *, journal_state: bool = False) -> PistonState:
        prev_active = dict(self.ctl.active_by_pair)
        state = self.ctl.tick()
        for pair_idx, proc in list(self.burners.items()):
            if proc.poll() is not None:
                proc = subprocess.Popen(
                    [sys.executable, str(_BURN_SCRIPT_PATH)],
                    creationflags=_popen_flags(),
                )
                self.burners[pair_idx] = proc
            core = self.ctl.active_by_pair[pair_idx]
            if prev_active.get(pair_idx) != core:
                self.swaps_total += 1
            self.ctl.set_affinity(proc.pid, core)
        if journal_state:
            write_piston_state(state)
        self.last_state = state
        return state

    def alive(self) -> int:
        return stress_alive(list(self.burners.values()))

    def stop(self) -> None:
        if self.burners:
            stop_stressor(list(self.burners.values()))
        self.burners.clear()

    def summary(self) -> dict[str, Any]:
        st = self.last_state
        return {
            "mode": "piston",
            "pairs": len(self.ctl.pairs),
            "burners_alive": self.alive(),
            "swaps_total": self.swaps_total,
            "package_s_n": round(st.package_s_n, 4) if st else None,
            "firing_order": st.firing_order if st else [],
        }
