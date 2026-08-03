"""RID triad — PC port of L:/Phone/ridplot.py, ridv14.py, rid_v12-1.py.

Sensor triad (dual readings A °C, B °C) — Phone arithmetic, PC sensors:
  LTP = (A + B) / 2
  RSR = A * B
  RLE = A*B - ((A+B)/2)^2
  RLE_rate = dRLE/dt

Runtime channels (rid_v12, 0–1) — load stability, thermal headroom, RAM:
  S_n = (RSR * LTP * RLE)^(1/3)   dormancy if S_n < 0.45

PC sensor pairs (default cpu_gpu):
  A = Corsair CPU package (liquid loop) or psutil fallback
  B = GPU die (NVML) or Corsair coolant fallback
"""
from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

try:
    import psutil
except ImportError as exc:
    raise SystemExit("rid_triad requires psutil") from exc

from lib.corsair_telemetry import read_cpu_temp_c, read_latest
from lib.paths import RID_ARTIFACTS

DORMANCY_THRESHOLD = 0.45
RLE_WARN_NORM = -0.01
ICUE_SAMPLE_INTERVAL_S = 1.0  # match Corsair iCUE CSV cadence (~1 Hz)
THERMAL_IDEAL_C = 37.0
THERMAL_ABORT_C = 70.0
MAX_FREQ_HIST = 8


class SensorPair(str, Enum):
    CPU_GPU = "cpu_gpu"
    CPU_COOLANT = "cpu_coolant"
    CORE_SPREAD = "core_spread"


@dataclass
class SensorReading:
    a_c: float
    b_c: float
    a_label: str
    b_label: str
    cpu_load_pct: float
    ram_pct: float
    gpu_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TriadSample:
    timestamp: str
    t_s: float
    a_c: float
    b_c: float
    a_label: str
    b_label: str
    ltp: float
    rsr: float
    rle: float
    rle_rate: float
    runtime_rsr: float
    runtime_ltp: float
    runtime_rle: float
    s_n: float
    cpu_load_pct: float
    ram_pct: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _cv(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = statistics.fmean(xs)
    if m == 0:
        return None
    return statistics.pstdev(xs) / abs(m)


def sensor_triad(
    a: float,
    b: float,
    prev_rle: float | None,
    dt: float,
) -> tuple[float, float, float, float]:
    """Exact L:/Phone/ridv14.py arithmetic on dual sensor readings."""
    ltp = (a + b) / 2.0
    rsr = a * b
    expected = ((a + b) / 2.0) ** 2
    rle = (a * b) - expected
    if prev_rle is not None and dt > 0:
        rle_rate = (rle - prev_rle) / dt
    else:
        rle_rate = 0.0
    return ltp, rsr, rle, rle_rate


def runtime_channels(
    load_hist: list[float],
    temp_c: float,
    ram_pct: float,
) -> tuple[float, float, float, float]:
    """rid_v12-1 / rid_benchmark PC channels, all 0–1."""
    c = _cv(load_hist[-MAX_FREQ_HIST:]) if len(load_hist) >= 3 else None
    rsr = clamp(1.0 - c) if c is not None else 0.8

    if temp_c <= 0:
        ltp = 0.75
    else:
        span = THERMAL_ABORT_C - THERMAL_IDEAL_C
        ltp = clamp(1.0 - clamp((temp_c - THERMAL_IDEAL_C) / span))

    rle = clamp(1.0 - ram_pct / 100.0)
    s_n = (max(rsr, 1e-6) * max(ltp, 1e-6) * max(rle, 1e-6)) ** (1.0 / 3.0)
    return rsr, ltp, rle, s_n


def _psutil_max_temp() -> float:
    best = 0.0
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for _name, entries in temps.items():
                for entry in entries:
                    if entry.current and entry.current > best:
                        best = float(entry.current)
    except (OSError, AttributeError):
        pass
    return best


def _read_gpu_temp() -> tuple[float | None, str | None]:
    try:
        from lib.gpu_plant import read_gpu

        g = read_gpu(0)
        return g.temp_c, g.name
    except Exception:
        try:
            from lib.gpu_plant import read_gpu_nvidia_smi

            g = read_gpu_nvidia_smi(0)
            if g:
                return g.temp_c, g.name
        except Exception:
            pass
    return None, None


def read_sensors(pair: SensorPair = SensorPair.CPU_GPU) -> SensorReading:
    """Read dual PC plant sensors (replaces Phone /sys/class/thermal/thermal_zoneN)."""
    cue = read_latest()
    cpu_pkg = read_cpu_temp_c() or cue.get("cpu_package_c")
    coolant = cue.get("coolant_c")
    load = cue.get("cpu_load_pct")
    psutil_load = float(psutil.cpu_percent(interval=None))
    if load is not None:
        cpu_load = max(float(load), psutil_load)
    else:
        cpu_load = psutil_load
    ram_pct = float(psutil.virtual_memory().percent)

    if cpu_pkg is None or cpu_pkg <= 0:
        cpu_pkg = _psutil_max_temp()
    if cpu_pkg <= 0:
        cpu_pkg = 0.0

    gpu_temp, gpu_name = _read_gpu_temp()

    if pair == SensorPair.CPU_GPU:
        a, a_label = cpu_pkg, "cpu_package_c"
        if gpu_temp is not None and gpu_temp > 0:
            b, b_label = gpu_temp, "gpu_die_c"
        elif coolant is not None and coolant > 0:
            b, b_label = float(coolant), "coolant_c"
        else:
            time.sleep(0.05)
            b2 = read_cpu_temp_c() or _psutil_max_temp()
            b, b_label = b2 if b2 > 0 else cpu_pkg, "cpu_package_delayed"

    elif pair == SensorPair.CPU_COOLANT:
        a, a_label = cpu_pkg, "cpu_package_c"
        if coolant is not None and coolant > 0:
            b, b_label = float(coolant), "coolant_c"
        elif gpu_temp is not None and gpu_temp > 0:
            b, b_label = gpu_temp, "gpu_die_c"
        else:
            time.sleep(0.05)
            b2 = read_cpu_temp_c() or cpu_pkg
            b, b_label = b2, "cpu_package_delayed"

    else:  # CORE_SPREAD
        from lib.corsair_telemetry import read_per_core_temps

        n = psutil.cpu_count(logical=True) or 16
        cores = read_per_core_temps(n_cores=n)
        valid = [t for t in cores if t > 0]
        if len(valid) >= 2:
            a, b = max(valid), min(valid)
        else:
            a, b = cpu_pkg, cpu_pkg * 0.98 if cpu_pkg > 0 else 0.0
        a_label, b_label = "core_max_c", "core_min_c"
        gpu_name = gpu_name  # noqa: F841 — keep for metadata if set

    return SensorReading(
        a_c=float(a),
        b_c=float(b),
        a_label=a_label,
        b_label=b_label,
        cpu_load_pct=cpu_load,
        ram_pct=ram_pct,
        gpu_name=gpu_name,
    )


def sensor_key(a_c: float, b_c: float) -> tuple[float, float]:
    return (round(a_c, 2), round(b_c, 2))


class TriadSession:
    """Stateful sampler — tracks load history, RLE rate, elapsed time."""

    def __init__(self, pair: SensorPair = SensorPair.CPU_GPU) -> None:
        self.pair = pair
        self.load_hist: list[float] = []
        self.prev_rle: float | None = None
        self.prev_commit_ts: float | None = None
        self.t0: float | None = None
        self.last_sensor_key: tuple[float, float] | None = None

    def poll(self) -> SensorReading:
        return read_sensors(self.pair)

    def commit(self, sens: SensorReading, now: float | None = None) -> TriadSample:
        """Record triad on a new sensor reading (dt = time since last commit)."""
        ts = now if now is not None else time.time()
        if self.t0 is None:
            self.t0 = ts
        dt = (ts - self.prev_commit_ts) if self.prev_commit_ts else 0.0
        self.prev_commit_ts = ts

        self.load_hist.append(sens.cpu_load_pct)
        if len(self.load_hist) > 64:
            self.load_hist.pop(0)

        ltp, rsr, rle, rle_rate = sensor_triad(sens.a_c, sens.b_c, self.prev_rle, dt)
        self.prev_rle = rle
        self.last_sensor_key = sensor_key(sens.a_c, sens.b_c)

        avg_temp = (sens.a_c + sens.b_c) / 2.0 if sens.a_c > 0 and sens.b_c > 0 else max(sens.a_c, sens.b_c)
        rt_rsr, rt_ltp, rt_rle, s_n = runtime_channels(self.load_hist, avg_temp, sens.ram_pct)
        status = "DORMANT" if s_n < DORMANCY_THRESHOLD else "ACTIVE"

        return TriadSample(
            timestamp=datetime.now(timezone.utc).isoformat(),
            t_s=ts - (self.t0 or ts),
            a_c=round(sens.a_c, 2),
            b_c=round(sens.b_c, 2),
            a_label=sens.a_label,
            b_label=sens.b_label,
            ltp=round(ltp, 4),
            rsr=round(rsr, 4),
            rle=round(rle, 6),
            rle_rate=round(rle_rate, 6),
            runtime_rsr=round(rt_rsr, 4),
            runtime_ltp=round(rt_ltp, 4),
            runtime_rle=round(rt_rle, 4),
            s_n=round(s_n, 4),
            cpu_load_pct=round(sens.cpu_load_pct, 1),
            ram_pct=round(sens.ram_pct, 1),
            status=status,
        )

    def sample_on_change(self) -> TriadSample | None:
        """Poll sensors; commit only when A or B changes (iCUE step alignment)."""
        return self.sample_on_change_from(self.poll())

    def sample_on_change_from(self, sens: SensorReading) -> TriadSample | None:
        key = sensor_key(sens.a_c, sens.b_c)
        if self.last_sensor_key is not None and key == self.last_sensor_key:
            return None
        return self.commit(sens)

    def sample(self) -> TriadSample:
        """Unconditional sample (legacy / heartbeat hooks)."""
        return self.commit(self.poll())


def format_line(s: TriadSample) -> str:
    return (
        f"t={s.t_s:5.1f}s  A({s.a_label})={s.a_c:5.1f}°C  B({s.b_label})={s.b_c:5.1f}°C  "
        f"LTP={s.ltp:6.2f}  RLE={s.rle:8.4f}  S_n={s.s_n:.4f}  {s.status}"
    )


def default_csv_path(name: str) -> str:
    return str(RID_ARTIFACTS / name)


def dedupe_sensor_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep first row and each row where sensor pair changes."""
    out: list[dict[str, Any]] = []
    last: tuple[float, float] | None = None
    for row in rows:
        if "a_c" in row and "b_c" in row:
            key = sensor_key(float(row["a_c"]), float(row["b_c"]))
        elif "a" in row and "b" in row:
            key = sensor_key(float(row["a"]), float(row["b"]))
        else:
            out.append(row)
            continue
        if last is None or key != last:
            out.append(row)
            last = key
    return out
