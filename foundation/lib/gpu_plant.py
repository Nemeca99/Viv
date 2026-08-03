"""GPU plant telemetry via NVML (RTX and friends). Air-cooled plant, separate from CPU liquid loop."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any

try:
    import pynvml
except ImportError as exc:
    raise SystemExit("gpu_plant requires nvidia-ml-py: pip install nvidia-ml-py") from exc

_NVML_INIT = False

GPU_TEMP_MAX = float(os.environ.get("VIV_GPU_TEMP_MAX", "83"))
GPU_CLOCK_VAR_MAX = float(os.environ.get("VIV_GPU_CLOCK_VAR", "150"))  # MHz
GPU_UTIL_VAR_MAX = float(os.environ.get("VIV_GPU_UTIL_VAR", "25"))


@dataclass
class GpuSnapshot:
    name: str
    index: int
    temp_c: float
    util_pct: float
    mem_used_mib: int
    mem_total_mib: int
    mem_free_mib: int
    clock_mhz: int
    power_w: float
    fan_pct: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "index": self.index,
            "temp_c": self.temp_c,
            "util_pct": self.util_pct,
            "mem_used_mib": self.mem_used_mib,
            "mem_total_mib": self.mem_total_mib,
            "mem_free_mib": self.mem_free_mib,
            "clock_mhz": self.clock_mhz,
            "power_w": self.power_w,
            "fan_pct": self.fan_pct,
        }


def _ensure_nvml() -> None:
    global _NVML_INIT
    if not _NVML_INIT:
        pynvml.nvmlInit()
        _NVML_INIT = True


def gpu_count() -> int:
    _ensure_nvml()
    return int(pynvml.nvmlDeviceGetCount())


def read_gpu(index: int = 0) -> GpuSnapshot:
    _ensure_nvml()
    h = pynvml.nvmlDeviceGetHandleByIndex(index)
    name = pynvml.nvmlDeviceGetName(h)
    if isinstance(name, bytes):
        name = name.decode("utf-8", errors="replace")
    temp = float(pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU))
    util = pynvml.nvmlDeviceGetUtilizationRates(h)
    mem = pynvml.nvmlDeviceGetMemoryInfo(h)
    try:
        clock = int(pynvml.nvmlDeviceGetClockInfo(h, pynvml.NVML_CLOCK_GRAPHICS))
    except pynvml.NVMLError:
        clock = 0
    try:
        power = float(pynvml.nvmlDeviceGetPowerUsage(h)) / 1000.0
    except pynvml.NVMLError:
        power = 0.0
    try:
        fan = int(pynvml.nvmlDeviceGetFanSpeed(h))
    except pynvml.NVMLError:
        fan = 0
    total_mib = int(mem.total // (1024 * 1024))
    used_mib = int(mem.used // (1024 * 1024))
    free_mib = int(mem.free // (1024 * 1024))
    return GpuSnapshot(
        name=name,
        index=index,
        temp_c=temp,
        util_pct=float(util.gpu),
        mem_used_mib=used_mib,
        mem_total_mib=total_mib,
        mem_free_mib=free_mib,
        clock_mhz=clock,
        power_w=power,
        fan_pct=fan,
    )


def read_gpu_nvidia_smi(index: int = 0) -> GpuSnapshot | None:
    """Fallback when NVML fails."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                f"--id={index}",
                "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,clocks.gr,power.draw,fan.speed",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
        parts = [p.strip() for p in out.split(",")]
        if len(parts) < 7:
            return None
        total = int(float(parts[4]))
        used = int(float(parts[3]))
        return GpuSnapshot(
            name=parts[0],
            index=index,
            temp_c=float(parts[1]),
            util_pct=float(parts[2]),
            mem_used_mib=used,
            mem_total_mib=total,
            mem_free_mib=max(0, total - used),
            clock_mhz=int(float(parts[5])),
            power_w=float(parts[6]) if parts[6] not in ("[N/A]", "N/A") else 0.0,
            fan_pct=int(float(parts[7])) if len(parts) > 7 and parts[7] not in ("[N/A]", "N/A") else 0,
        )
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
