"""Architect plant monitor — better than iCUE + Task Manager for PRT windows.

Remade permanently into Viv from L: priors:
  - per-core load: piston_engine.read_loads (psutil percpu)
  - per-core temps / package / coolant: corsair_telemetry (iCUE CSV)
  - GPU: gpu_plant NVML (not Corsair GPU columns)
  - Master RID triad: master_rid.compute_master_rid

Console layout inspired by Steel_Brain live_stream.py; sensors are Viv plant.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError as exc:
    raise SystemExit("architect_monitor requires psutil") from exc

from lib.corsair_telemetry import read_latest, read_per_core_temps, latest_csv
from lib.master_rid import compute_master_rid, publish_master_rid
from lib.paths import RID_ARTIFACTS
from lib.piston_engine import read_loads
from lib.rid_triad import TriadSession

DEFAULT_JSONL = RID_ARTIFACTS / "architect_monitor.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bar(pct: float, width: int = 10) -> str:
    pct = max(0.0, min(100.0, float(pct)))
    filled = int(round(width * pct / 100.0))
    return "#" * filled + "-" * (width - filled)


def sample_frame(*, n_cores: int | None = None, publish: bool = True) -> dict[str, Any]:
    """One Architect frame: per-core + Corsair + NVML + Master RID."""
    logical = psutil.cpu_count(logical=True) or 16
    n = int(n_cores) if n_cores else logical
    n = max(1, min(n, logical))

    loads = read_loads(n)
    temps = read_per_core_temps(n_cores=n)
    cue = read_latest()
    session = TriadSession()
    triad = session.sample()
    master = compute_master_rid(triad)
    if publish:
        publish_master_rid(master)

    gpu: dict[str, Any] = {}
    try:
        from lib.gpu_plant import read_gpu

        g = read_gpu(0)
        gpu = g.to_dict()
    except Exception as exc:  # noqa: BLE001
        gpu = {"error": str(exc)}

    # Hot / cold cores by temp among known readings
    paired = [(i, temps[i], loads[i]) for i in range(n) if temps[i] and temps[i] > 0]
    hot = max(paired, key=lambda x: x[1]) if paired else None
    cold = min(paired, key=lambda x: x[1]) if paired else None
    load_hot = max(range(n), key=lambda i: loads[i]) if loads else None

    frame = {
        "timestamp": _utc(),
        "t_local": datetime.now().strftime("%H:%M:%S"),
        "n_cores": n,
        "per_core": [
            {
                "core": i,
                "load_pct": round(float(loads[i]), 1),
                "temp_c": round(float(temps[i]), 1) if temps[i] else None,
            }
            for i in range(n)
        ],
        "corsair": {
            "cpu_package_c": cue.get("cpu_package_c"),
            "coolant_c": cue.get("coolant_c"),
            "cpu_load_pct_icue": cue.get("cpu_load_pct"),
            "csv": cue.get("source"),
            "csv_mtime": None,
        },
        "cpu_total_pct": round(float(psutil.cpu_percent(interval=None)), 1),
        "ram_pct": round(float(psutil.virtual_memory().percent), 1),
        "gpu": gpu,
        "triad": {
            "a_c": triad.a_c,
            "b_c": triad.b_c,
            "a_label": triad.a_label,
            "b_label": triad.b_label,
            "s_n": triad.s_n,
            "status": triad.status,
        },
        "master": {
            "master_s_n": master.master_s_n,
            "master_rsr": master.master_rsr,
            "master_ltp": master.master_ltp,
            "master_rle": master.master_rle,
            "status": master.status,
            "subsystems": {
                k: {"s_n": v.s_n, "rsr": v.rsr, "ltp": v.ltp, "rle": v.rle, "available": v.available}
                for k, v in master.subsystems.items()
            },
        },
        "highlights": {
            "hottest_core": {"core": hot[0], "temp_c": hot[1], "load_pct": hot[2]} if hot else None,
            "coolest_core": {"core": cold[0], "temp_c": cold[1], "load_pct": cold[2]} if cold else None,
            "busiest_core": {"core": load_hot, "load_pct": loads[load_hot]} if load_hot is not None else None,
            "package_minus_coolant_c": (
                round(float(cue["cpu_package_c"]) - float(cue["coolant_c"]), 2)
                if cue.get("cpu_package_c") and cue.get("coolant_c")
                else None
            ),
        },
    }
    path = latest_csv()
    if path is not None:
        try:
            frame["corsair"]["csv_mtime"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        except OSError:
            pass
    return frame


def format_frame(frame: dict[str, Any]) -> str:
    """Compact multi-line console panel (no curses — PRT-friendly)."""
    lines: list[str] = []
    m = frame.get("master") or {}
    g = frame.get("gpu") or {}
    c = frame.get("corsair") or {}
    h = frame.get("highlights") or {}
    lines.append("=" * 72)
    lines.append(
        f" ARCHITECT MONITOR  {frame.get('t_local')}  |  "
        f"Master S_n={m.get('master_s_n')} {m.get('status')}  |  "
        f"RSR={m.get('master_rsr')} LTP={m.get('master_ltp')} RLE={m.get('master_rle')}"
    )
    lines.append("-" * 72)
    lines.append(
        f" CPU pkg={c.get('cpu_package_c')}°C  coolant={c.get('coolant_c')}°C  "
        f"Δ(pkg-cool)={h.get('package_minus_coolant_c')}  "
        f"total_load={frame.get('cpu_total_pct')}%  RAM={frame.get('ram_pct')}%"
    )
    if g and "error" not in g:
        lines.append(
            f" GPU {g.get('name')}  temp={g.get('temp_c')}°C  util={g.get('util_pct')}%  "
            f"VRAM={g.get('mem_used_mib')}/{g.get('mem_total_mib')} MiB  "
            f"P={g.get('power_w')}W  clk={g.get('clock_mhz')}MHz"
        )
    elif g.get("error"):
        lines.append(f" GPU unavailable: {g.get('error')}")

    subs = m.get("subsystems") or {}
    if subs:
        bits = "  ".join(
            f"{name}={sub.get('s_n')}" for name, sub in subs.items() if isinstance(sub, dict)
        )
        lines.append(f" Subsystems: {bits}")

    hot = h.get("hottest_core") or {}
    busy = h.get("busiest_core") or {}
    lines.append(
        f" Hot core #{hot.get('core')} {hot.get('temp_c')}°C@{hot.get('load_pct')}%  |  "
        f"Busy core #{busy.get('core')} {busy.get('load_pct')}%"
    )
    lines.append("-" * 72)
    lines.append(" CORE  LOAD%           TEMP°C")
    for row in frame.get("per_core") or []:
        load = float(row.get("load_pct") or 0)
        temp = row.get("temp_c")
        t_s = f"{temp:5.1f}" if isinstance(temp, (int, float)) else "  n/a"
        lines.append(f"  {row['core']:02d}   {load:5.1f} {_bar(load)}  {t_s}")
    lines.append("=" * 72)
    return "\n".join(lines)


def append_jsonl(frame: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(frame, ensure_ascii=False, default=str) + "\n")


def run_monitor(
    *,
    interval: float = 1.0,
    seconds: float | None = None,
    n_cores: int | None = None,
    jsonl: Path | None = None,
    clear: bool = True,
    publish: bool = True,
) -> dict[str, Any]:
    """Live loop. seconds=None → until Ctrl+C."""
    out_path = jsonl if jsonl is not None else DEFAULT_JSONL
    t0 = time.time()
    frames = 0
    print(
        f"Architect monitor -> {out_path} every {interval}s "
        f"(Corsair+NVML+per-core+Master RID). Ctrl+C to stop.",
        flush=True,
    )
    try:
        while True:
            frame = sample_frame(n_cores=n_cores, publish=publish)
            append_jsonl(frame, out_path)
            frames += 1
            panel = format_frame(frame)
            if clear and frames > 1:
                # ANSI clear — works in Windows Terminal / modern consoles
                print("\033[H\033[J", end="", flush=True)
            print(panel, flush=True)
            if seconds is not None and (time.time() - t0) >= seconds:
                break
            time.sleep(max(0.2, float(interval)))
    except KeyboardInterrupt:
        print("\nmonitor stopped.", flush=True)
    return {
        "ok": True,
        "frames": frames,
        "jsonl": str(out_path).replace("\\", "/"),
        "elapsed_s": round(time.time() - t0, 1),
    }
