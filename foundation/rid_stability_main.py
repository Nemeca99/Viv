#!/usr/bin/env python3
"""
RID stability test — PC port of L:/Phone/ridv14.py

Samples at iCUE cadence (1 Hz). Logs only when A or B changes (no duplicate holds).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import multiprocessing
import sys
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.paths import RID_ARTIFACTS
from lib.piston_stress import PistonStressFleet
from lib.rid_stressor import ensure_stressor, start_stressor, stop_stressor, stress_alive
from lib.rid_triad import (
    ICUE_SAMPLE_INTERVAL_S,
    RLE_WARN_NORM,
    SensorPair,
    TriadSession,
    format_line,
)
from lib.master_rid import compute_master_rid

VERSION = "1.1.0-pc"
CSV_HEADER = [
    "timestamp",
    "t_s",
    "a_c",
    "b_c",
    "a_label",
    "b_label",
    "ltp",
    "rsr",
    "rle",
    "rle_rate",
    "runtime_rsr",
    "runtime_ltp",
    "runtime_rle",
    "s_n",
    "cpu_load_pct",
    "ram_pct",
    "status",
    "master_s_n",
    "master_rsr",
    "master_ltp",
    "master_rle",
    "cpu_automaton_s_n",
    "piston_s_n",
    "gpu_s_n",
    "coolant_loop_s_n",
]


def _machin_burn() -> None:
    x = 1.0
    for _ in range(50_000):
        x = math.atan(1.0 / (5.0 * (x + 1.0)))


def run(
    *,
    duration: float,
    sample_interval: float,
    print_interval: float,
    stress: bool,
    stress_mode: str,
    cores: int | None,
    pair: SensorPair,
    csv_path: Path,
    log_all: bool,
    publish: bool = True,
) -> dict:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.is_file()
    session = TriadSession(pair=pair)
    procs: list = []
    piston_fleet: PistonStressFleet | None = None
    if stress:
        if stress_mode == "piston":
            piston_fleet = PistonStressFleet()
            alive = piston_fleet.start()
            expected = len(piston_fleet.ctl.pairs)
            print(f"Piston stress: {alive}/{expected} pair burners alive")
        else:
            procs = start_stressor(cores)
            alive = stress_alive(procs)
            expected = cores or multiprocessing.cpu_count()
            print(f"Blast stress: {alive}/{expected} CPU workers alive")
            if alive == 0:
                procs = ensure_stressor(procs, cores)
                alive = stress_alive(procs)
                print(f"Stress restart: {alive} workers alive")
    rle_values: list[float] = []
    master_values: list[float] = []
    subsystem_values: dict[str, list[float]] = {
        "cpu_automaton": [],
        "piston": [],
        "gpu": [],
        "coolant_loop": [],
    }
    samples: list[dict] = []
    polls = 0
    max_load = 0.0

    print(
        f"RID stability PC v{VERSION} — {duration:.0f}s, pair={pair.value}, "
        f"poll={sample_interval:.1f}s, log={'all' if log_all else 'on_change'}, "
        f"stress={stress_mode if stress else 'off'}"
    )
    print(f"Logging -> {csv_path}")
    print(f"{'t(s)':>4s} {'A(C)':>8s} {'B(C)':>8s} {'LTP':>8s} {'RSR':>10s} {'RLE':>10s} {'RLErate':>10s} {'S_n':>6s}")
    print("-" * 78)

    t_end = time.time() + duration
    t0 = time.time()
    last_print = -print_interval
    stress_alive_end = 0
    piston_summary: dict | None = None
    poll_log_path = csv_path.with_suffix(".poll.jsonl")
    poll_log_path.write_text("", encoding="utf-8")

    try:
        with csv_path.open("a", newline="", encoding="utf-8") as fh, poll_log_path.open(
            "a", encoding="utf-8"
        ) as plf:
            w = csv.writer(fh)
            if new_file:
                w.writerow(CSV_HEADER)
            while time.time() < t_end:
                loop_start = time.time()
                if stress:
                    if piston_fleet is not None:
                        piston_fleet.tick()
                        alive_now = piston_fleet.alive()
                    else:
                        procs = ensure_stressor(procs, cores)
                        alive_now = stress_alive(procs)
                else:
                    alive_now = 0
                polls += 1
                sens = session.poll()
                max_load = max(max_load, sens.cpu_load_pct)
                poll_rec = {
                    "t_s": round(loop_start - t0, 3),
                    "poll": polls,
                    "a_c": sens.a_c,
                    "b_c": sens.b_c,
                    "cpu_load_pct": sens.cpu_load_pct,
                    "stress_alive": alive_now,
                    "stress_mode": stress_mode if stress else "off",
                }
                plf.write(json.dumps(poll_rec) + "\n")
                plf.flush()
                if log_all:
                    s = session.commit(sens)
                else:
                    s = session.sample_on_change_from(sens)
                if s is not None:
                    master = compute_master_rid(s)
                    subs = master.subsystems
                    rle_values.append(s.rle)
                    master_values.append(master.master_s_n)
                    for name, bucket in subsystem_values.items():
                        bucket.append(subs[name].s_n)
                    max_load = max(max_load, s.cpu_load_pct)
                    row = [
                        s.timestamp, s.t_s, s.a_c, s.b_c, s.a_label, s.b_label,
                        s.ltp, s.rsr, s.rle, s.rle_rate, s.runtime_rsr, s.runtime_ltp,
                        s.runtime_rle, s.s_n, s.cpu_load_pct, s.ram_pct, s.status,
                        master.master_s_n, master.master_rsr, master.master_ltp,
                        master.master_rle, subs["cpu_automaton"].s_n, subs["piston"].s_n,
                        subs["gpu"].s_n, subs["coolant_loop"].s_n,
                    ]
                    w.writerow(row)
                    fh.flush()
                    samples.append(s.to_dict())

                    if s.t_s - last_print >= print_interval:
                        print(
                            f"{int(s.t_s):4d} {s.a_c:8.2f} {s.b_c:8.2f} {s.ltp:8.2f} "
                            f"{s.rsr:10.1f} {s.rle:10.4f} {s.rle_rate:10.4f} {s.s_n:6.4f}"
                        )
                        last_print = s.t_s
                deadline = t0 + polls * sample_interval
                sleep_s = deadline - time.time()
                if sleep_s > 0:
                    time.sleep(sleep_s)
            if stress:
                if piston_fleet is not None:
                    stress_alive_end = piston_fleet.alive()
                    piston_summary = piston_fleet.summary()
                else:
                    stress_alive_end = stress_alive(procs)
    finally:
        if piston_fleet is not None:
            piston_fleet.stop()
        elif procs:
            stop_stressor(procs)

    summary: dict = {
        "version": VERSION,
        "duration_s": duration,
        "pair": pair.value,
        "stress": stress,
        "stress_mode": stress_mode if stress else "off",
        "sample_interval_s": sample_interval,
        "log_on_change": not log_all,
        "polls": polls,
        "n_logged": len(samples),
        "csv": str(csv_path),
    }
    if stress:
        summary["stress_workers_alive_end"] = stress_alive_end
        summary["cpu_load_max_pct"] = max_load
        summary["poll_log"] = str(poll_log_path)
        if piston_fleet is not None and piston_summary is not None:
            summary["piston_stress"] = piston_summary
    if rle_values:
        summary["rle_min"] = min(rle_values)
        summary["rle_mean"] = sum(rle_values) / len(rle_values)
        summary["s_n_min"] = min(s["s_n"] for s in samples)
        summary["s_n_max"] = max(s["s_n"] for s in samples)
        summary["s_n_mean"] = sum(s["s_n"] for s in samples) / len(samples)
        if master_values:
            summary["master_s_n_min"] = min(master_values)
            summary["master_s_n_max"] = max(master_values)
            summary["master_s_n_mean"] = sum(master_values) / len(master_values)
            for name, vals in subsystem_values.items():
                if vals:
                    summary[f"{name}_s_n_min"] = min(vals)
                    summary[f"{name}_s_n_mean"] = sum(vals) / len(vals)
        warn_pair = pair in (SensorPair.CPU_COOLANT, SensorPair.CORE_SPREAD)
        if warn_pair:
            for s in samples:
                ltp = float(s["ltp"])
                rle = float(s["rle"])
                rle_norm = rle / max(ltp * ltp, 1.0)
                if rle_norm < RLE_WARN_NORM:
                    summary["early_warning_t_s"] = s["t_s"]
                    summary["early_warning_rle_norm"] = rle_norm
                    break
        else:
            summary["early_warning"] = (
                "skipped (cpu_gpu uses different plants — use --pair cpu_coolant for gap warnings)"
            )

    out_json = csv_path.with_suffix(".summary.json")
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["summary_json"] = str(out_json)

    from lib.plant_piston_bridge import publish_capture
    from lib.stability_capture import validate_summary

    verdict = validate_summary(summary, summary_path=out_json)
    if publish:
        publish_capture(summary, verdict)
    summary["capture_verdict"] = verdict.verdict
    summary["capture_reasons"] = verdict.reasons
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n--- Summary ---")
    if rle_values:
        print(
            f"Polls: {polls}  Logged (on change): {len(samples)}  "
            f"RLE min: {summary['rle_min']:.4f}  S_n mean: {summary['s_n_mean']:.4f}"
        )
        if stress:
            print(
                f"CPU load max: {summary.get('cpu_load_max_pct', 0):.0f}%  "
                f"Stress workers alive at end: {summary.get('stress_workers_alive_end', 0)}"
            )
        if summary.get("early_warning_t_s") is not None:
            print(
                f"WARN early warning at t~{summary['early_warning_t_s']:.0f}s "
                f"(RLE_norm={summary['early_warning_rle_norm']:.6f})"
            )
        elif summary.get("early_warning"):
            print(summary["early_warning"])
        else:
            print("No RLE early warning.")
        if publish:
            print(f"Capture verdict: {summary.get('capture_verdict')} -> artifacts/auto/plant/last_stability_capture.json")
        else:
            print(f"Capture verdict: {summary.get('capture_verdict')} (not published)")
        if summary.get("capture_reasons"):
            for r in summary["capture_reasons"]:
                print(f"  - {r}")
    else:
        print("No sensor changes logged.")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RID stability test (PC port of Phone/ridv14.py)")
    ap.add_argument("--seconds", type=float, default=120.0, help="Run duration")
    ap.add_argument(
        "--sample-interval",
        type=float,
        default=ICUE_SAMPLE_INTERVAL_S,
        help="Poll interval in seconds (default 1.0 = iCUE cadence)",
    )
    ap.add_argument("--interval", type=float, default=2.0, help="Console print interval")
    ap.add_argument("--stress", action="store_true")
    ap.add_argument(
        "--stress-mode",
        choices=["blast", "piston"],
        default="blast",
        help="blast=full-core subprocess burners; piston=per-pair affinity via PistonController",
    )
    ap.add_argument("--cores", type=int, default=None)
    ap.add_argument(
        "--pair",
        choices=[p.value for p in SensorPair],
        default=SensorPair.CPU_COOLANT.value,
    )
    ap.add_argument("--csv", type=Path, default=RID_ARTIFACTS / "stability_pc.csv")
    ap.add_argument(
        "--log-all",
        action="store_true",
        help="Log every poll (legacy oversampled mode)",
    )
    ap.add_argument(
        "--no-publish",
        action="store_true",
        help="Do not update artifacts/auto/plant/last_stability_capture.json",
    )
    args = ap.parse_args(argv)
    run(
        duration=args.seconds,
        sample_interval=args.sample_interval,
        print_interval=args.interval,
        stress=args.stress,
        stress_mode=args.stress_mode,
        cores=args.cores,
        pair=SensorPair(args.pair),
        csv_path=args.csv,
        log_all=args.log_all,
        publish=not args.no_publish,
    )
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if multiprocessing.current_process().name == "MainProcess":
        raise SystemExit(main())
