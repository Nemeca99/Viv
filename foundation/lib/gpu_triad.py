"""GPU RID triad — NVML sensors (temp, power, VRAM) for PC black hole runs."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from lib.gpu_plant import read_gpu
from lib.rid_triad import sensor_triad, sensor_key
from lib.paths import AUTO_ARTIFACTS

GPU_TRIAD_ARTIFACTS = AUTO_ARTIFACTS / "black_hole" / "gpu_triad"
GPU_TRIAD_ARTIFACTS.mkdir(parents=True, exist_ok=True)


class GpuSensorPair(str, Enum):
    TEMP_POWER = "temp_power"      # A=temp C, B=power W
    TEMP_VRAM = "temp_vram"        # A=temp C, B=VRAM used MiB
    TEMP_CLOCK = "temp_clock"      # A=temp C, B=clock MHz


@dataclass
class GpuTriadSample:
    timestamp: str
    t_s: float
    a: float
    b: float
    a_label: str
    b_label: str
    ltp: float
    rsr: float
    rle: float
    rle_rate: float
    util_pct: float
    fan_pct: int
    gpu_name: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_gpu_sensors(pair: GpuSensorPair, index: int = 0) -> tuple[float, float, str, str, str, float, int]:
    g = read_gpu(index)
    if pair == GpuSensorPair.TEMP_POWER:
        return g.temp_c, g.power_w, "gpu_temp_c", "gpu_power_w", g.name, g.util_pct, g.fan_pct
    if pair == GpuSensorPair.TEMP_VRAM:
        used = float(g.mem_used_mib)
        return g.temp_c, used, "gpu_temp_c", "gpu_vram_used_mib", g.name, g.util_pct, g.fan_pct
    return g.temp_c, float(g.clock_mhz), "gpu_temp_c", "gpu_clock_mhz", g.name, g.util_pct, g.fan_pct


class GpuTriadSession:
    def __init__(self, pair: GpuSensorPair = GpuSensorPair.TEMP_POWER, index: int = 0) -> None:
        self.pair = pair
        self.index = index
        self.prev_rle: float | None = None
        self.prev_ts: float | None = None
        self.t0: float | None = None
        self.last_key: tuple[float, float] | None = None

    def sample_on_change(self) -> GpuTriadSample | None:
        a, b, a_label, b_label, name, util, fan = read_gpu_sensors(self.pair, self.index)
        key = sensor_key(a, b)
        if self.last_key is not None and key == self.last_key:
            return None
        return self._commit(a, b, a_label, b_label, name, util, fan)

    def sample(self) -> GpuTriadSample:
        a, b, a_label, b_label, name, util, fan = read_gpu_sensors(self.pair, self.index)
        return self._commit(a, b, a_label, b_label, name, util, fan)

    def _commit(
        self, a: float, b: float, a_label: str, b_label: str, name: str, util: float, fan: int,
    ) -> GpuTriadSample:
        ts = time.time()
        if self.t0 is None:
            self.t0 = ts
        dt = (ts - self.prev_ts) if self.prev_ts else 0.0
        self.prev_ts = ts
        ltp, rsr, rle, rle_rate = sensor_triad(a, b, self.prev_rle, dt)
        self.prev_rle = rle
        self.last_key = sensor_key(a, b)
        return GpuTriadSample(
            timestamp=datetime.now(timezone.utc).isoformat(),
            t_s=ts - (self.t0 or ts),
            a=round(a, 2),
            b=round(b, 2),
            a_label=a_label,
            b_label=b_label,
            ltp=round(ltp, 4),
            rsr=round(rsr, 4),
            rle=round(rle, 6),
            rle_rate=round(rle_rate, 6),
            util_pct=round(util, 1),
            fan_pct=fan,
            gpu_name=name,
        )


def format_gpu_triad_line(s: GpuTriadSample) -> str:
    return (
        f"t={s.t_s:5.1f}s  {s.gpu_name}  A({s.a_label})={s.a:.1f}  B({s.b_label})={s.b:.1f}  "
        f"LTP={s.ltp:.2f}  RLE={s.rle:.4f}  Util={s.util_pct:.0f}%"
    )
