"""Sn-governed CPU duty-cycle enforcement.

The CPU is the heat source. S_n sets the allowed utilization ceiling:
  S_n = 1.0 -> 100% duty ,  S_n = 0.0 -> 0% duty.
Each managed worker is pinned to a core and runs a busy/sleep loop whose
duty fraction is driven by a shared value the governor updates every tick.

Fail-safe direction is DOWN: on stale telemetry or dormancy, duty -> floor
(less heat), never up.
"""
from __future__ import annotations

import multiprocessing as mp
import time
from ctypes import c_double

try:
    import psutil
except ImportError as exc:
    raise SystemExit("cpu_governor requires psutil") from exc


def governed_burn(duty: "mp.sharedctypes.Synchronized", window: float = 0.1) -> None:
    """Worker: hold this core near (duty*100)% by busy/sleep duty cycling."""
    while True:
        d = duty.value
        if d <= 0.0:
            time.sleep(window)
            continue
        if d >= 1.0:
            end = time.perf_counter() + window
            x = 1.0
            while time.perf_counter() < end:
                x = (x * 1.000001 + 0.000001) % 100000.0
            continue
        busy = window * d
        idle = window - busy
        end = time.perf_counter() + busy
        x = 1.0
        while time.perf_counter() < end:
            x = (x * 1.000001 + 0.000001) % 100000.0
        if idle > 0:
            time.sleep(idle)


class GovernedFleet:
    """One duty-controlled worker per managed core."""

    def __init__(self, cores: list[int], window: float = 0.1) -> None:
        self.cores = cores
        self.window = window
        self._duties: dict[int, "mp.sharedctypes.Synchronized"] = {}
        self._procs: dict[int, mp.Process] = {}

    def start(self, initial_duty: float = 0.0) -> None:
        for core in self.cores:
            shared = mp.Value(c_double, float(initial_duty))
            proc = mp.Process(target=governed_burn, args=(shared, self.window), daemon=True)
            proc.start()
            self._duties[core] = shared
            self._procs[core] = proc
            try:
                psutil.Process(proc.pid).cpu_affinity([core])
            except (psutil.Error, OSError, AttributeError):
                pass

    def set_duty(self, core: int, frac: float) -> None:
        shared = self._duties.get(core)
        if shared is not None:
            shared.value = max(0.0, min(1.0, float(frac)))

    def set_all(self, frac: float) -> None:
        for core in self.cores:
            self.set_duty(core, frac)

    def pids(self) -> dict[int, int]:
        return {core: proc.pid for core, proc in self._procs.items()}

    def stop(self) -> None:
        for shared in self._duties.values():
            shared.value = 0.0
        for proc in self._procs.values():
            proc.terminate()
        for proc in self._procs.values():
            proc.join(timeout=2.0)
        self._duties.clear()
        self._procs.clear()
