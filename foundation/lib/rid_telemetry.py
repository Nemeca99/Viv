"""RID telemetry — PC port (uses lib/rid_triad, not phone stubs)."""
from __future__ import annotations

import json
from pathlib import Path

from lib.rid_triad import (
    DORMANCY_THRESHOLD,
    TriadSample,
    TriadSession,
    format_line,
    read_sensors,
    runtime_channels,
    sensor_triad,
)

# Back-compat aliases for rid_main / heart hooks
RidSample = TriadSample


def get_cpu_load() -> float:
    import psutil

    return float(psutil.cpu_percent(interval=0.05))


def get_ram_usage() -> float:
    import psutil

    return float(psutil.virtual_memory().percent)


def get_cpu_temp() -> float:
    from lib.corsair_telemetry import read_cpu_temp_c

    t = read_cpu_temp_c()
    if t and t > 0:
        return float(t)
    sens = read_sensors()
    return (sens.a_c + sens.b_c) / 2.0


def compute_rid(
    cpu_load: float,
    ram_usage: float,
    cpu_temp: float,
    prev_load: float,
) -> tuple[float, float, float, float]:
    load_hist = [prev_load, cpu_load]
    return runtime_channels(load_hist, cpu_temp, ram_usage)


_session = TriadSession()


def sample_once(prev_load: float | None = None) -> TriadSample:
    del prev_load  # session tracks load history internally
    return _session.sample()


def write_json_sample(path: Path, sample: TriadSample) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sample.to_dict(), indent=2), encoding="utf-8")
