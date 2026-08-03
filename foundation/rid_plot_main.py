#!/usr/bin/env python3
"""
RID live plot — PC port of L:/Phone/ridplot.py

1 Hz iCUE-aligned polling. One point per sensor change. Step-style plot (honest stairs).
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.paths import RID_ARTIFACTS
from lib.rid_stressor import start_stressor, stop_stressor
from lib.rid_triad import ICUE_SAMPLE_INTERVAL_S, SensorPair, TriadSession, dedupe_sensor_rows

VERSION = "1.1.0-pc"


def load_csv(path: Path, *, dedupe: bool = True) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if dedupe and rows and "a_c" in rows[0]:
        before = len(rows)
        rows = dedupe_sensor_rows(rows)
        if before != len(rows):
            print(f"Deduped {before} -> {len(rows)} rows (sensor change only)")

    ltp_l, rsr_l, rle_l, rate_l, t_l = [], [], [], [], []
    for row in rows:
        t_l.append(float(row.get("t_s") or row.get("Timestamp") or len(t_l)))
        ltp_l.append(float(row["ltp"] if "ltp" in row else row.get("LTP", 0)))
        rsr_l.append(float(row["rsr"] if "rsr" in row else row.get("RSR", 0)))
        rle_l.append(float(row["rle"] if "rle" in row else row.get("RLE", 0)))
        rate_l.append(float(row.get("rle_rate") or row.get("RLE_rate") or 0))
    return ltp_l, rsr_l, rle_l, rate_l, t_l


def collect_live(
    duration: float,
    interval: float,
    pair: SensorPair,
    stress: bool,
    cores: int | None,
    csv_out: Path | None,
    log_all: bool,
) -> tuple[list[float], list[float], list[float], list[float], list[float], int]:
    session = TriadSession(pair=pair)
    procs = start_stressor(cores) if stress else []
    ltp_l, rsr_l, rle_l, rate_l, t_l = [], [], [], [], []
    polls = 0
    fh = None
    writer = None
    if csv_out:
        csv_out.parent.mkdir(parents=True, exist_ok=True)
        new = not csv_out.is_file()
        fh = csv_out.open("a", newline="", encoding="utf-8")
        writer = csv.writer(fh)
        if new:
            writer.writerow(["t_s", "a_c", "b_c", "ltp", "rsr", "rle", "rle_rate", "s_n"])
    t_end = time.time() + duration
    try:
        while time.time() < t_end:
            polls += 1
            s = session.sample() if log_all else session.sample_on_change()
            if s is None:
                time.sleep(interval)
                continue
            t_l.append(s.t_s)
            ltp_l.append(s.ltp)
            rsr_l.append(s.rsr)
            rle_l.append(s.rle)
            rate_l.append(s.rle_rate)
            if writer:
                writer.writerow([s.t_s, s.a_c, s.b_c, s.ltp, s.rsr, s.rle, s.rle_rate, s.s_n])
                fh.flush()
            time.sleep(interval)
    finally:
        if fh:
            fh.close()
        if procs:
            stop_stressor(procs)
    return ltp_l, rsr_l, rle_l, rate_l, t_l, polls


def plot_channels(
    ltp_l: list[float],
    rsr_l: list[float],
    rle_l: list[float],
    rate_l: list[float],
    t_l: list[float],
    out_png: Path | None,
    show: bool,
) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — pip install matplotlib")
        return False

    if not t_l:
        print("No data to plot.")
        return False

    fig, axes = plt.subplots(4, 1, figsize=(10, 8), sharex=True)
    step = dict(drawstyle="steps-post")

    axes[0].plot(t_l, ltp_l, "b", label="LTP (add)", **step)
    axes[0].set_ylabel("C avg")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(t_l, rsr_l, "g", label="RSR (mult)", **step)
    axes[1].set_ylabel("Product")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(t_l, rle_l, "r", label="RLE (sub, gap)", **step)
    axes[2].set_ylabel("Variance gap")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    axes[3].plot(t_l, rate_l, "m", label="RLE rate (div)", marker="o", markersize=3, linestyle="none")
    axes[3].axhline(0, color="gray", linewidth=0.5)
    axes[3].set_ylabel("dRLE/dt")
    axes[3].set_xlabel("Time (s)")
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    fig.suptitle(f"RID triad — PC v{VERSION} (1 Hz, log on sensor change)")
    plt.tight_layout()
    if out_png:
        out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_png, dpi=150)
        print(f"wrote {out_png}")
    if show:
        plt.show()
    else:
        plt.close(fig)
    return True


def plot_csv(csv_path: Path, out_png: Path) -> bool:
    data = load_csv(csv_path, dedupe=True)
    return plot_channels(*data, out_png=out_png, show=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RID triad plot (PC port of Phone/ridplot.py)")
    ap.add_argument("--csv", type=Path, default=None, help="Plot existing CSV (auto-dedupes)")
    ap.add_argument("--no-dedupe", action="store_true", help="Keep all rows when loading CSV")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--interval", type=float, default=ICUE_SAMPLE_INTERVAL_S, help="Poll interval (default 1s)")
    ap.add_argument("--stress", action="store_true")
    ap.add_argument("--cores", type=int, default=None)
    ap.add_argument("--pair", default=SensorPair.CPU_COOLANT.value, choices=[p.value for p in SensorPair])
    ap.add_argument("--out", type=Path, default=RID_ARTIFACTS / "rid_plot_pc.png")
    ap.add_argument("--live-csv", type=Path, default=RID_ARTIFACTS / "rid_plot_live.csv")
    ap.add_argument("--log-all", action="store_true", help="Log/plot every poll")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args(argv)

    if args.csv:
        print(f"Loading {args.csv}")
        data = load_csv(args.csv, dedupe=not args.no_dedupe)
        polls = 0
    else:
        print(
            f"Live {args.seconds:.0f}s, pair={args.pair}, poll={args.interval}s, "
            f"log={'all' if args.log_all else 'on_change'}"
        )
        ltp_l, rsr_l, rle_l, rate_l, t_l, polls = collect_live(
            args.seconds,
            args.interval,
            SensorPair(args.pair),
            args.stress,
            args.cores,
            args.live_csv,
            args.log_all,
        )
        data = (ltp_l, rsr_l, rle_l, rate_l, t_l)
        print(f"Polls: {polls}  Points logged: {len(ltp_l)} -> {args.live_csv}")

    ok = plot_channels(*data, out_png=args.out, show=args.show)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
