"""Coupled CPU (liquid) + GPU (air) black hole collapse — dual plant physics."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.black_hole_engine import (
    CollapseSample,
    ChannelEngine,
    read_cpu_freqs_khz,
    read_mem_available_kb,
    read_temp_c,
)
from lib.gpu_black_hole_engine import GpuChannelEngine, GpuCollapseSample
from lib.gpu_plant import read_gpu
from lib.paths import AUTO_ARTIFACTS

COUPLED_ARTIFACTS = AUTO_ARTIFACTS / "black_hole" / "coupled"
COUPLED_STATE_PATH = COUPLED_ARTIFACTS / "collapse_state.json"
COUPLED_LOG_PATH = COUPLED_ARTIFACTS / "collapse_log.jsonl"


@dataclass
class CoupledSample:
    timestamp: str
    beat: int
    cpu: dict[str, Any]
    gpu: dict[str, Any]
    coupled_s_n: float
    regime: str
    cpu_horizon: bool
    gpu_horizon: bool
    dual_horizon: bool
    horizon_lag_s: float | None
    first_plant: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CoupledEngine:
    """Track two plants; measure horizon correlation vs decoupling."""

    def __init__(self) -> None:
        self.cpu_eng = ChannelEngine()
        self.gpu_eng = GpuChannelEngine()
        self.beat = 0
        self._cpu_horizon_at: float | None = None
        self._gpu_horizon_at: float | None = None
        self._t0: float | None = None

    def tick(
        self,
        *,
        cpu_thr: dict[str, float],
        gpu_thr: dict[str, float],
        phone_compat: bool = False,
        gpu_index: int = 0,
    ) -> CoupledSample:
        import time

        self.beat += 1
        if self._t0 is None:
            self._t0 = time.time()
        now = time.time() - (self._t0 or now)

        cpu = _sample_cpu(self.cpu_eng, phone_compat=phone_compat)
        gpu = _sample_gpu(self.gpu_eng, gpu_index)

        cpu_h = _apply_cpu_thr(self.cpu_eng, cpu, cpu_thr, phone_compat)
        gpu_h = _apply_gpu_thr(self.gpu_eng, gpu, gpu_thr)

        if cpu_h and self._cpu_horizon_at is None:
            self._cpu_horizon_at = now
        if gpu_h and self._gpu_horizon_at is None:
            self._gpu_horizon_at = now

        dual = self.cpu_eng.latched and self.gpu_eng.latched
        coupled_sn = (max(cpu.s_n, 1e-6) * max(gpu.s_n, 1e-6)) ** 0.5
        regime = _regime(cpu_h, gpu_h, dual, cpu, gpu)
        first, lag = _horizon_timing(self._cpu_horizon_at, self._gpu_horizon_at)

        return CoupledSample(
            timestamp=datetime.now(timezone.utc).isoformat(),
            beat=self.beat,
            cpu=cpu.to_dict(),
            gpu=gpu.to_dict(),
            coupled_s_n=round(coupled_sn, 4),
            regime=regime,
            cpu_horizon=cpu_h,
            gpu_horizon=gpu_h,
            dual_horizon=dual,
            horizon_lag_s=round(lag, 2) if lag is not None else None,
            first_plant=first,
        )


def _sample_cpu(eng: ChannelEngine, *, phone_compat: bool) -> CollapseSample:
    from datetime import datetime, timezone

    freqs = read_cpu_freqs_khz()
    temp = read_temp_c()
    mem = read_mem_available_kb()
    mass, density, energy = eng.compute(freqs, temp, mem, phone_compat=phone_compat)
    avg_mhz = (sum(freqs) / len(freqs) / 1000.0) if freqs else 0.0
    return CollapseSample(
        timestamp=datetime.now(timezone.utc).isoformat(),
        temp_c=round(temp, 1),
        avg_freq_mhz=round(avg_mhz, 1),
        mem_available_kb=mem,
        mass=round(mass, 4),
        density=round(density, 4),
        energy=round(energy, 4),
        s_n=round(eng.s_n(mass, density, energy), 4),
        collapsed=False,
        latched=eng.latched,
        n_cores=0,
    )


def _sample_gpu(eng: GpuChannelEngine, index: int) -> GpuCollapseSample:
    from datetime import datetime, timezone

    snap = read_gpu(index)
    mass, density, energy = eng.compute(snap)
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
        s_n=round(eng.s_n(mass, density, energy), 4),
        collapsed=False,
        latched=eng.latched,
    )


def _apply_cpu_thr(
    eng: ChannelEngine,
    s: CollapseSample,
    thr: dict[str, float],
    phone_compat: bool,
) -> bool:
    hit = eng.collapsed(
        s.mass,
        s.density,
        s.energy,
        phone_compat=phone_compat,
        mass_thr=thr["mass"],
        density_thr=thr["density"],
        energy_thr=thr["energy"],
    )
    s.collapsed = hit
    s.latched = eng.latched
    return hit


def _apply_gpu_thr(eng: GpuChannelEngine, s: GpuCollapseSample, thr: dict[str, float]) -> bool:
    hit = eng.collapsed(
        s.mass,
        s.density,
        s.energy,
        mass_thr=thr["mass"],
        density_thr=thr["density"],
        energy_thr=thr["energy"],
    )
    s.collapsed = hit
    s.latched = eng.latched
    return hit


def _regime(cpu_h: bool, gpu_h: bool, dual: bool, cpu: CollapseSample, gpu: GpuCollapseSample) -> str:
    if dual:
        return "dual_horizon"
    if cpu_h and not gpu_h:
        return "cpu_horizon_only"
    if gpu_h and not cpu_h:
        return "gpu_horizon_only"
    # Approaching but not crossed
    if cpu.density > 0.7 and gpu.density < 0.5:
        return "decoupled_cpu_hot"
    if gpu.density > 0.7 and cpu.density < 0.5:
        return "decoupled_gpu_hot"
    if cpu.s_n < 0.45 and gpu.s_n >= 0.45:
        return "decoupled_cpu_stress"
    if gpu.s_n < 0.45 and cpu.s_n >= 0.45:
        return "decoupled_gpu_stress"
    return "stable"


def _horizon_timing(
    cpu_at: float | None,
    gpu_at: float | None,
) -> tuple[str | None, float | None]:
    if cpu_at is None and gpu_at is None:
        return None, None
    if cpu_at is not None and gpu_at is None:
        return "cpu", None
    if gpu_at is not None and cpu_at is None:
        return "gpu", None
    assert cpu_at is not None and gpu_at is not None
    lag = abs(cpu_at - gpu_at)
    first = "cpu" if cpu_at <= gpu_at else "gpu"
    return first, lag


def write_coupled_state(sample: CoupledSample) -> Path:
    COUPLED_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    COUPLED_STATE_PATH.write_text(json.dumps(sample.to_dict(), indent=2), encoding="utf-8")
    return COUPLED_STATE_PATH


def append_coupled_log(sample: CoupledSample) -> None:
    COUPLED_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with COUPLED_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(sample.to_dict(), separators=(",", ":")) + "\n")


def format_coupled_line(s: CoupledSample) -> str:
    flag = "DUAL HORIZON" if s.dual_horizon else s.regime.upper()
    lag = f" lag={s.horizon_lag_s}s first={s.first_plant}" if s.horizon_lag_s is not None else ""
    return (
        f"[COUPLED] beat={s.beat} S_n={s.coupled_s_n:.3f} "
        f"CPU[T={s.cpu['temp_c']:.0f}C M={s.cpu['mass']:.2f} D={s.cpu['density']:.2f} E={s.cpu['energy']:.2f}] "
        f"GPU[T={s.gpu['temp_c']:.0f}C M={s.gpu['mass']:.2f} D={s.gpu['density']:.2f} E={s.gpu['energy']:.2f}] "
        f"{flag}{lag}"
    )


def print_coupled_line(s: CoupledSample) -> None:
    print(format_coupled_line(s), flush=True)
