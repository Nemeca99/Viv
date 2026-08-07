#!/usr/bin/env python3
"""Plant S_n dose gate — furnace-style shed/add for UML mix training.

Port of foundation/docs/external cpu_thermal_furnace + tri_axis_furnace governor:
  S_n high  → ADD_FUEL  (allow full mix dose)
  S_n mid   → SHED_LOAD (scale mix_ratio down)
  S_n low   → CRITICAL  (floor mix / cool-down)

RID remains stability; this never changes sealed UML destinations.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_FOUNDATION = Path(__file__).resolve().parents[1]
if str(_FOUNDATION) not in sys.path:
    sys.path.insert(0, str(_FOUNDATION))

SCHEMA = "uml_plant_sn_gate_v1"


@dataclass
class PlantSnView:
    master_s_n: float
    available: bool
    source: str
    coolant_s_n: float | None = None
    gpu_s_n: float | None = None

    @property
    def s_n(self) -> float:
        return float(self.master_s_n)


def read_plant_sn() -> PlantSnView:
    try:
        from lib.master_rid import load_master_rid

        master = load_master_rid()
        if master is None:
            return PlantSnView(master_s_n=0.5, available=False, source="master_rid_missing")
        subs = master.subsystems if isinstance(master.subsystems, dict) else {}
        cool = subs.get("coolant_loop")
        gpu = subs.get("gpu")
        return PlantSnView(
            master_s_n=float(master.master_s_n),
            available=True,
            source="master_rid",
            coolant_s_n=float(cool.s_n) if cool is not None and getattr(cool, "available", False) else None,
            gpu_s_n=float(gpu.s_n) if gpu is not None and getattr(gpu, "available", False) else None,
        )
    except Exception as exc:
        return PlantSnView(
            master_s_n=0.5,
            available=False,
            source=f"master_rid_error:{exc!r}",
        )


def dose_decision(
    *,
    base_mix: float,
    plant: PlantSnView | None = None,
    add_fuel_floor: float = 0.85,
    critical_ceil: float = 0.45,
    mix_floor: float = 0.15,
) -> dict[str, Any]:
    """Map plant S_n → effective mix_ratio and furnace-style action.

    Matches external furnace:
      s_n >= add_fuel_floor → ADD_FUEL (full base_mix)
      critical_ceil < s_n < add_fuel_floor → SHED_LOAD (mix *= s_n)
      s_n <= critical_ceil → CRITICAL_COOLING (mix_floor)
    """
    plant = plant or read_plant_sn()
    s_n = max(0.0, min(1.0, float(plant.s_n)))
    base = max(0.0, min(1.0, float(base_mix)))
    floor = max(0.0, min(base, float(mix_floor)))

    if s_n >= float(add_fuel_floor):
        action = "ADD_FUEL"
        effective = base
        scale = 1.0
    elif s_n > float(critical_ceil):
        action = "SHED_LOAD"
        scale = s_n
        effective = max(floor, base * scale)
    else:
        action = "CRITICAL_COOLING"
        scale = 0.0
        effective = floor

    return {
        "schema_version": SCHEMA,
        "action": action,
        "plant_s_n": s_n,
        "plant_available": plant.available,
        "plant_source": plant.source,
        "base_mix": base,
        "effective_mix": float(effective),
        "scale": float(scale),
        "add_fuel_floor": float(add_fuel_floor),
        "critical_ceil": float(critical_ceil),
        "mix_floor": floor,
        "coolant_s_n": plant.coolant_s_n,
        "gpu_s_n": plant.gpu_s_n,
    }


__all__ = ["PlantSnView", "dose_decision", "read_plant_sn"]
