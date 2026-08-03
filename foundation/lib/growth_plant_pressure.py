"""Moderate plant pressure for growth-strain proofs.

Reuses Viv GovernedFleet (already on L:/Continue/Viv) — duty-cycled burn,
not full-blast rid_stressor. Goal: depress Master S_n into the strain band
(above critical / near_dead, below calibrated target) so growth_pending can fire.
"""
from __future__ import annotations

import multiprocessing as mp
import time
from typing import Any

try:
    import psutil
except ImportError as exc:
    raise SystemExit("growth_plant_pressure requires psutil") from exc

from lib.cpu_governor import GovernedFleet
from lib.growth_strain import is_near_dead, load_baseline, load_policy, sample_plant


def _default_cores(n: int | None = None) -> list[int]:
    total = psutil.cpu_count(logical=True) or 8
    want = int(n) if n is not None else max(2, total // 2)
    want = max(1, min(want, total))
    return list(range(want))


class PlantPressure:
    """Fixed-duty CPU pressure for growth tests (Architect-operator tool)."""

    def __init__(
        self,
        *,
        cores: int | None = None,
        duty: float = 0.35,
        window: float = 0.1,
    ) -> None:
        self.core_ids = _default_cores(cores)
        self.duty = max(0.0, min(1.0, float(duty)))
        self.window = float(window)
        self.fleet: GovernedFleet | None = None

    def start(self) -> dict[str, Any]:
        if mp.current_process().name != "MainProcess":
            raise RuntimeError("PlantPressure must start from main process")
        self.fleet = GovernedFleet(self.core_ids, window=self.window)
        self.fleet.start(initial_duty=self.duty)
        return {
            "cores": self.core_ids,
            "duty": self.duty,
            "pids": self.fleet.pids(),
        }

    def set_duty(self, duty: float) -> None:
        self.duty = max(0.0, min(1.0, float(duty)))
        if self.fleet is not None:
            self.fleet.set_all(self.duty)

    def stop(self) -> None:
        if self.fleet is not None:
            self.fleet.stop()
            self.fleet = None

    def __enter__(self) -> "PlantPressure":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def seek_strain_band(
    pressure: PlantPressure,
    *,
    warm_s: float = 20.0,
    duty_lo: float = 0.15,
    duty_hi: float = 0.55,
    step: float = 0.05,
    hold_s: float = 3.0,
) -> dict[str, Any]:
    """Ramp duty until Master S_n is in (critical, target) or report miss."""
    baseline = load_baseline()
    policy = load_policy()
    if not baseline:
        return {"ok": False, "reason": "no_baseline"}
    target = float(baseline["target_master_s_n"])
    crit = float(policy.get("critical_s_n") or 0.15)
    # Leave margin above critical so near_dead does not clear strain
    band_lo = crit + 0.05
    band_hi = target

    history: list[dict[str, Any]] = []
    duty = max(duty_lo, min(duty_hi, pressure.duty))
    pressure.set_duty(duty)
    t0 = time.time()
    found = False
    last = sample_plant()

    while time.time() - t0 < warm_s:
        last = sample_plant()
        sn = float(last["master_s_n"])
        row = {
            "t": round(time.time() - t0, 1),
            "duty": round(duty, 3),
            "master_s_n": sn,
            "cpu_load_pct": last.get("cpu_load_pct"),
            "status": last.get("status"),
            "near_dead": is_near_dead(last, policy),
        }
        history.append(row)
        print(
            f"seek t={row['t']:4.1f}s duty={duty:.2f} S_n={sn:.4f} "
            f"load={row['cpu_load_pct']} near_dead={row['near_dead']}",
            flush=True,
        )
        if band_lo < sn < band_hi and not row["near_dead"]:
            found = True
            break
        if sn >= band_hi and duty < duty_hi:
            duty = min(duty_hi, duty + step)
            pressure.set_duty(duty)
        elif sn <= band_lo and duty > duty_lo:
            duty = max(duty_lo, duty - step)
            pressure.set_duty(duty)
        time.sleep(hold_s)

    return {
        "ok": found,
        "band_lo": band_lo,
        "band_hi": band_hi,
        "final_duty": duty,
        "plant": last,
        "history": history,
        "reason": "in_band" if found else "band_not_reached",
    }
