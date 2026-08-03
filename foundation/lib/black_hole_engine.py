"""Black hole collapse simulator — RID triadic channels on live PC telemetry."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError as exc:
    raise SystemExit("black_hole requires psutil") from exc

from lib.corsair_telemetry import read_cpu_temp_c, read_latest
from lib.paths import AUTO_ARTIFACTS

BH_ARTIFACTS = AUTO_ARTIFACTS / "black_hole"
STATE_PATH = BH_ARTIFACTS / "collapse_state.json"
LOG_PATH = BH_ARTIFACTS / "collapse_log.jsonl"

# Collapse thresholds (env-tunable; extreme mode lowers via CLI)
MASS_CRITICAL = float(os.environ.get("VIV_BH_MASS", "0.8"))
DENSITY_CRITICAL = float(os.environ.get("VIV_BH_DENSITY", "0.5"))
ENERGY_CRITICAL = float(os.environ.get("VIV_BH_ENERGY", "0.6"))  # below = exhausted

TEMP_MAX = float(os.environ.get("VIV_BH_TEMP_MAX", "72"))
FREQ_VAR_MAX = float(os.environ.get("VIV_BH_FREQ_VAR", "200_000").replace("_", ""))
MEM_MIN_KB = int(os.environ.get("VIV_BH_MEM_MIN_KB", "100_000"))
MEM_MAX_KB = int(os.environ.get("VIV_BH_MEM_MAX_KB", "0"))  # 0 = auto from psutil

MAX_FREQ_HIST = 5


@dataclass
class CollapseSample:
    timestamp: str
    temp_c: float
    avg_freq_mhz: float
    mem_available_kb: int
    mass: float
    density: float
    energy: float
    s_n: float
    collapsed: bool
    latched: bool
    n_cores: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mem_max_kb() -> int:
    if MEM_MAX_KB > 0:
        return MEM_MAX_KB
    total = psutil.virtual_memory().total // 1024
    return max(MEM_MIN_KB + 1, int(total))


def read_temp_c() -> float:
    t = read_cpu_temp_c()
    if t is not None and t > 0:
        return float(t)
    try:
        temps = psutil.sensors_temperatures()
        best = 0.0
        if temps:
            for _name, entries in temps.items():
                for entry in entries:
                    if entry.current and entry.current > best:
                        best = float(entry.current)
        if best > 0:
            return best
    except (OSError, AttributeError):
        pass
    cue = read_latest()
    pkg = cue.get("cpu_package_c")
    return float(pkg) if pkg else 0.0


def read_cpu_freqs_khz() -> list[int]:
    freqs: list[int] = []
    try:
        per = psutil.cpu_freq(percpu=True)
        if per:
            for f in per:
                if f and f.current and f.current > 0:
                    freqs.append(int(f.current * 1000))
    except (OSError, AttributeError):
        pass
    if not freqs:
        try:
            f = psutil.cpu_freq()
            if f and f.current and f.current > 0:
                n = psutil.cpu_count(logical=True) or 1
                freqs = [int(f.current * 1000)] * n
        except (OSError, AttributeError):
            pass
    return freqs


def read_mem_available_kb() -> int:
    return int(psutil.virtual_memory().available // 1024)


class ChannelEngine:
    """Mass (RSR), Density (LTP), Energy (remaining RAM fraction)."""

    def __init__(self) -> None:
        self._freq_hist: list[float] = []
        self.latched = False

    def compute(
        self,
        freqs: list[int],
        temp_c: float,
        mem_kb: int,
        *,
        phone_compat: bool = False,
    ) -> tuple[float, float, float]:
        # --- MASS: frequency coherence (stable high freq = high mass) ---
        if not freqs:
            mass = 0.0
        else:
            avg = sum(freqs) / len(freqs)
            self._freq_hist.append(avg)
            if len(self._freq_hist) > MAX_FREQ_HIST:
                self._freq_hist.pop(0)
            if len(self._freq_hist) >= 2:
                mean = sum(self._freq_hist) / len(self._freq_hist)
                variance = sum(abs(x - mean) for x in self._freq_hist) / len(self._freq_hist)
                mass = max(0.0, 1.0 - variance / max(FREQ_VAR_MAX, 1.0))
            else:
                mass = 1.0

        # --- DENSITY: thermal density ---
        density = max(0.0, min(1.0, temp_c / max(TEMP_MAX, 1.0)))

        mem_max = _mem_max_kb()
        # --- ENERGY: remaining memory (1=full, 0=empty) ---
        if phone_compat:
            # Phone script formula (RLE rises as RAM consumed); collapse uses rle < threshold
            energy = max(0.0, 1.0 - (mem_kb - MEM_MIN_KB) / max(mem_max - MEM_MIN_KB, 1))
        else:
            energy = max(0.0, min(1.0, (mem_kb - MEM_MIN_KB) / max(mem_max - MEM_MIN_KB, 1)))

        return mass, density, energy

    def collapsed(
        self,
        mass: float,
        density: float,
        energy: float,
        *,
        phone_compat: bool = False,
        mass_thr: float = MASS_CRITICAL,
        density_thr: float = DENSITY_CRITICAL,
        energy_thr: float = ENERGY_CRITICAL,
    ) -> bool:
        if phone_compat:
            event = mass > mass_thr and density > density_thr and energy < energy_thr
        else:
            # Canonical: mass high, density high, energy depleted (low remaining)
            event = mass > mass_thr and density > density_thr and energy < energy_thr
        if event:
            self.latched = True
        return self.latched or event

    def s_n(self, mass: float, density: float, energy: float) -> float:
        # Geometric mean; energy exhaustion lowers S_n via (1 - energy) as load channel
        rle = max(1e-6, energy)
        rsr = max(1e-6, mass)
        ltp = max(1e-6, 1.0 - density)  # headroom inverse of density
        return (rsr * ltp * rle) ** (1.0 / 3.0)


def sample_once(engine: ChannelEngine, *, phone_compat: bool = False) -> CollapseSample:
    freqs = read_cpu_freqs_khz()
    temp = read_temp_c()
    mem = read_mem_available_kb()
    mass, density, energy = engine.compute(freqs, temp, mem, phone_compat=phone_compat)
    collapsed = engine.collapsed(mass, density, energy, phone_compat=phone_compat)
    avg_mhz = (sum(freqs) / len(freqs) / 1000.0) if freqs else 0.0
    return CollapseSample(
        timestamp=datetime.now(timezone.utc).isoformat(),
        temp_c=round(temp, 1),
        avg_freq_mhz=round(avg_mhz, 1),
        mem_available_kb=mem,
        mass=round(mass, 4),
        density=round(density, 4),
        energy=round(energy, 4),
        s_n=round(engine.s_n(mass, density, energy), 4),
        collapsed=collapsed,
        latched=engine.latched,
        n_cores=psutil.cpu_count(logical=True) or 0,
    )


def append_log(sample: CollapseSample) -> None:
    BH_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(sample.to_dict(), separators=(",", ":")) + "\n")


def write_state(sample: CollapseSample) -> Path:
    BH_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(sample.to_dict(), indent=2), encoding="utf-8")
    return STATE_PATH


# --- Stressors (PC: all logical cores) ---

def _arctan(x: Decimal, one: Decimal) -> Decimal:
    z = one / x
    z2 = z * z
    term = z
    result = term
    i = 3
    while True:
        term *= z2
        next_term = term / Decimal(i)
        if next_term == 0:
            break
        if i % 4 == 3:
            result -= next_term
        else:
            result += next_term
        i += 2
    return result


def _compute_pi() -> None:
    one = Decimal(1)
    while True:
        getcontext().prec = 500
        _ = 16 * _arctan(Decimal(5), one) - 4 * _arctan(Decimal(239), one)


def _memory_apocalypse() -> None:
    holder: list[bytearray] = []
    while True:
        try:
            for _ in range(50):
                holder.append(bytearray(1024 * 1024))
        except MemoryError:
            if len(holder) > 100:
                holder = holder[-50:]
        time.sleep(0.05)


def launch_stressors(n_cores: int | None = None) -> list:
    from lib.rid_stressor import start_stressor

    return start_stressor(n_cores)


def stop_stressors(procs: list) -> None:
    from lib.rid_stressor import stop_stressor

    stop_stressor(procs)


def format_line(s: CollapseSample) -> str:
    flag = "BLACK HOLE FORMED - EVENT HORIZON CROSSED" if s.collapsed else "STABLE"
    return (
        f"[BH] T={s.temp_c:.1f}C Freq={s.avg_freq_mhz/1000:.2f}GHz "
        f"Mass={s.mass:.3f} Dens={s.density:.3f} En={s.energy:.3f} S_n={s.s_n:.3f} {flag}"
    )


def print_line(s: CollapseSample) -> None:
    print(format_line(s), flush=True)
