#!/usr/bin/env python3
"""
GPU triad plot — temp vs power/VRAM/clock (NVML, fast updates).

PC port companion to rid_plot_main.py for the RTX plant.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.gpu_stress import GpuStressMode, launch_gpu_stress, stop_gpu_stress
from lib.gpu_triad import GPU_TRIAD_ARTIFACTS, GpuSensorPair, GpuTriadSession, format_gpu_triad_line
from lib.rid_triad import dedupe_sensor_rows

VERSION = "1.0.0-pc"
NVML_POLL_S = 0.5  # NVML updates faster than iCUE


def collect(
    duration: float,
    interval: float,
    pair: GpuSensorPair,
    stress_mode: str | None,
    gpu_index: int,
    csv_path: Path,
) -> list[dict]:
    session = GpuTriadSession(pair=pair, index=gpu_index)
    procs = launch_gpu_stress(stress_mode) if stress_mode else []
    rows: list[dict] = []
    new_file = not csv_path.is_file()
    t_end = time.time() + duration
    polls = 0
    try:
        with csv_path.open("a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new_file:
                w.writerow(["t_s", "a", "b", "a_label", "b_label", "ltp", "rsr", "rle", "rle_rate", "util_pct", "gpu_name"])
            while time.time() < t_end:
                polls += 1
                s = session.sample_on_change()
                if s:
                    d = s.to_dict()
                    rows.append(d)
                    w.writerow([d["t_s"], d["a"], d["b"], d["a_label"], d["b_label"],
                                d["ltp"], d["rsr"], d["rle"], d["rle_rate"], d["util_pct"], d["gpu_name"]])
                    fh.flush()
                    print(format_gpu_triad_line(s))
                time.sleep(interval)
    finally:
        if procs:
            stop_gpu_stress(procs)
    print(f"Polls={polls} logged={len(rows)} -> {csv_path}")
    return rows


def plot_csv(csv_path: Path, out_png: Path) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("pip install matplotlib")
        return False
    with csv_path.open(newline="", encoding="utf-8") as fh:
        raw = list(csv.DictReader(fh))
    rows = dedupe_sensor_rows(raw) if raw and "a" in raw[0] else raw
    if not rows:
        return False
    t = [float(r["t_s"]) for r in rows]
    ltp = [float(r["ltp"]) for r in rows]
    rsr = [float(r["rsr"]) for r in rows]
    rle = [float(r["rle"]) for r in rows]
    rate = [float(r["rle_rate"]) for r in rows]
    step = dict(drawstyle="steps-post")
    fig, axes = plt.subplots(4, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(t, ltp, "b", **step)
    axes[0].set_ylabel("LTP")
    axes[1].plot(t, rsr, "g", **step)
    axes[1].set_ylabel("RSR")
    axes[2].plot(t, rle, "r", **step)
    axes[2].set_ylabel("RLE gap")
    axes[3].plot(t, rate, "mo", markersize=3, linestyle="none")
    axes[3].set_ylabel("dRLE/dt")
    axes[3].set_xlabel("Time (s)")
    name = rows[0].get("gpu_name", "GPU")
    fig.suptitle(f"GPU triad — {name} ({csv_path.name})")
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"wrote {out_png}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GPU triad plot (NVML temp/power/vram)")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--interval", type=float, default=NVML_POLL_S)
    ap.add_argument("--pair", default=GpuSensorPair.TEMP_POWER.value, choices=[p.value for p in GpuSensorPair])
    ap.add_argument("--stress", default="", choices=["", "normal", "extreme", "rtx"])
    ap.add_argument("--gpu", type=int, default=0)
    ap.add_argument("--csv", type=Path, default=GPU_TRIAD_ARTIFACTS / "gpu_triad.csv")
    ap.add_argument("--out", type=Path, default=GPU_TRIAD_ARTIFACTS / "gpu_triad_plot.png")
    ap.add_argument("--plot-only", type=Path, default=None, help="Plot existing CSV, skip capture")
    args = ap.parse_args(argv)

    if args.plot_only:
        return 0 if plot_csv(args.plot_only, args.out) else 1

    mode = args.stress or None
    print(f"GPU triad capture {args.seconds:.0f}s pair={args.pair} stress={mode or 'off'}")
    rows = collect(args.seconds, args.interval, GpuSensorPair(args.pair), mode, args.gpu, args.csv)
    summary = {
        "version": VERSION,
        "n": len(rows),
        "pair": args.pair,
        "stress": mode,
        "csv": str(args.csv),
        "png": str(args.out),
    }
    if rows:
        summary["temp_range"] = [min(r["a"] for r in rows), max(r["a"] for r in rows)]
        summary["b_range"] = [min(r["b"] for r in rows), max(r["b"] for r in rows)]
    summary_path = args.csv.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot_csv(args.csv, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
