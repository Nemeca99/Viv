"""GPU black hole collapse — air-cooled plant (separate physics from liquid CPU)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.gpu_plant import GPU_TEMP_MAX, read_gpu
from lib.paths import AUTO_ARTIFACTS

GPU_BH_ARTIFACTS = AUTO_ARTIFACTS / "black_hole" / "gpu"
GPU_STATE_PATH = GPU_BH_ARTIFACTS / "collapse_state.json"
GPU_LOG_PATH = GPU_BH_ARTIFACTS / "collapse_log.jsonl"

MASS_CRITICAL = float(os.environ.get("VIV_GPU_BH_MASS", "0.75"))
DENSITY_CRITICAL = float(os.environ.get("VIV_GPU_BH_DENSITY", "0.55"))
ENERGY_CRITICAL = float(os.environ.get("VIV_GPU_BH_ENERGY", "0.55"))
MAX_HIST = 5


@dataclass
class GpuCollapseSample:
    timestamp: str
    plant: str
    gpu_name: str
    temp_c: float
    clock_mhz: int
    util_pct: float
    mem_free_mib: int
    mem_total_mib: int
    power_w: float
    fan_pct: int
    mass: float
    density: float
    energy: float
    s_n: float
    collapsed: bool
    latched: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GpuChannelEngine:
    """Mass=clock coherence, Density=thermal, Energy=VRAM remaining (air-cooled GPU plant)."""

    def __init__(self) -> None:
        self._clock_hist: list[float] = []
        self._util_hist: list[float] = []
        self.latched = False

    def compute(self, snap) -> tuple[float, float, float]:
        clock = float(snap.clock_mhz)
        if clock > 0:
            self._clock_hist.append(clock)
            if len(self._clock_hist) > MAX_HIST:
                self._clock_hist.pop(0)
        self._util_hist.append(float(snap.util_pct))
        if len(self._util_hist) > MAX_HIST:
            self._util_hist.pop(0)

        # Mass: stable high clock under load = coherent mass
        if len(self._clock_hist) >= 2:
            mean = sum(self._clock_hist) / len(self._clock_hist)
            variance = sum(abs(x - mean) for x in self._clock_hist) / len(self._clock_hist)
            mass = max(0.0, 1.0 - variance / max(float(os.environ.get("VIV_GPU_CLOCK_VAR", "150")), 1.0))
        elif snap.util_pct > 50:
            mass = 0.85
        else:
            mass = min(1.0, snap.util_pct / 100.0 + 0.3)

        # Density: thermal compression (air-cooled ceiling lower than CPU liquid)
        density = max(0.0, min(1.0, snap.temp_c / max(GPU_TEMP_MAX, 1.0)))

        # Energy: remaining VRAM fraction
        if snap.mem_total_mib > 0:
            energy = max(0.0, min(1.0, snap.mem_free_mib / snap.mem_total_mib))
        else:
            energy = 0.0

        return mass, density, energy

    def collapsed(
        self,
        mass: float,
        density: float,
        energy: float,
        *,
        mass_thr: float = MASS_CRITICAL,
        density_thr: float = DENSITY_CRITICAL,
        energy_thr: float = ENERGY_CRITICAL,
    ) -> bool:
        event = mass > mass_thr and density > density_thr and energy < energy_thr
        if event:
            self.latched = True
        return self.latched or event

    def s_n(self, mass: float, density: float, energy: float) -> float:
        rsr = max(1e-6, mass)
        ltp = max(1e-6, 1.0 - density)
        rle = max(1e-6, energy)
        return (rsr * ltp * rle) ** (1.0 / 3.0)


def sample_gpu_once(engine: GpuChannelEngine, index: int = 0) -> GpuCollapseSample:
    snap = read_gpu(index)
    mass, density, energy = engine.compute(snap)
    collapsed = engine.collapsed(mass, density, energy)
    return GpuCollapseSample(
        timestamp=datetime.now(timezone.utc).isoformat(),
        plant="gpu_air_cooled",
        gpu_name=snap.name,
        temp_c=round(snap.temp_c, 1),
        clock_mhz=snap.clock_mhz,
        util_pct=round(snap.util_pct, 1),
        mem_free_mib=snap.mem_free_mib,
        mem_total_mib=snap.mem_total_mib,
        power_w=round(snap.power_w, 1),
        fan_pct=snap.fan_pct,
        mass=round(mass, 4),
        density=round(density, 4),
        energy=round(energy, 4),
        s_n=round(engine.s_n(mass, density, energy), 4),
        collapsed=collapsed,
        latched=engine.latched,
    )


def append_gpu_log(sample: GpuCollapseSample) -> None:
    GPU_BH_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with GPU_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(sample.to_dict(), separators=(",", ":")) + "\n")


def write_gpu_state(sample: GpuCollapseSample) -> Path:
    GPU_BH_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    GPU_STATE_PATH.write_text(json.dumps(sample.to_dict(), indent=2), encoding="utf-8")
    return GPU_STATE_PATH


def format_gpu_line(s: GpuCollapseSample) -> str:
    flag = "BLACK HOLE FORMED - GPU EVENT HORIZON" if s.collapsed else "STABLE"
    return (
        f"[GPU-BH] {s.gpu_name} T={s.temp_c:.1f}C Clk={s.clock_mhz}MHz "
        f"Pwr={s.power_w:.0f}W Fan={s.fan_pct}% Util={s.util_pct:.0f}% "
        f"VRAM={s.mem_free_mib}/{s.mem_total_mib}MiB "
        f"Mass={s.mass:.3f} Dens={s.density:.3f} En={s.energy:.3f} S_n={s.s_n:.3f} {flag}"
    )


def print_gpu_line(s: GpuCollapseSample) -> None:
    print(format_gpu_line(s), flush=True)
