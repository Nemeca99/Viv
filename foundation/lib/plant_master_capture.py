"""Plant captures with hierarchical Master S_n — coupled cpu_gpu and core_spread."""
from __future__ import annotations

import csv
import json
import multiprocessing
import time
from pathlib import Path
from typing import Any, Literal

from lib.gpu_plant import read_gpu
from lib.gpu_stress import launch_gpu_stress, stop_gpu_stress
from lib.master_rid import compute_master_rid, publish_master_rid
from lib.paths import RID_ARTIFACTS
from lib.piston_background import read_piston_snapshot, start_piston_background, stop_piston_background
from lib.plant_piston_bridge import publish_capture
from lib.rid_stressor import ensure_stressor, start_stressor, stop_stressor, stress_alive
from lib.rid_triad import ICUE_SAMPLE_INTERVAL_S, SensorPair, TriadSession
from lib.stability_capture import validate_summary

VERSION = "1.1.0"
CaptureKind = Literal["coupled", "core_spread"]

CSV_HEADER = [
    "timestamp",
    "t_s",
    "master_s_n",
    "master_rsr",
    "master_ltp",
    "master_rle",
    "master_status",
    "cpu_automaton_s_n",
    "piston_s_n",
    "gpu_s_n",
    "coolant_loop_s_n",
    "cpu_load_pct",
    "gpu_util_pct",
    "gpu_temp_c",
    "a_c",
    "b_c",
    "n_subsystems",
]


def _default_csv(kind: CaptureKind, seconds: float) -> Path:
    tag = "coupled_master" if kind == "coupled" else "core_spread_master"
    return RID_ARTIFACTS / f"{tag}_{int(seconds)}s_v1.csv"


def run_plant_master_capture(
    *,
    kind: CaptureKind = "coupled",
    duration: float = 120.0,
    sample_interval: float = ICUE_SAMPLE_INTERVAL_S,
    cores: int | None = None,
    gpu_stress: str = "rtx",
    csv_path: Path | None = None,
    warmup: float = 4.0,
    piston_background: bool = True,
    piston_interval: float = 1.0,
    publish: bool = True,
) -> dict[str, Any]:
    """Stress plant, poll Master S_n at 1 Hz, publish verdict. Piston runs in background."""
    pair = SensorPair.CPU_GPU if kind == "coupled" else SensorPair.CORE_SPREAD
    csv_path = csv_path or _default_csv(kind, duration)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not csv_path.is_file()
    poll_log_path = csv_path.with_suffix(".poll.jsonl")
    poll_log_path.write_text("", encoding="utf-8")

    session = TriadSession(pair=pair)
    cpu_procs = start_stressor(cores)
    gpu_procs: list = []
    if kind == "coupled":
        gpu_procs = launch_gpu_stress(gpu_stress)
    expected_cpu = cores or multiprocessing.cpu_count()

    piston_started = False
    if piston_background:
        piston_started = start_piston_background(interval=piston_interval, journal=False)

    print(
        f"Plant Master RID capture v{VERSION} ({kind}) — {duration:.0f}s @ {sample_interval:.1f}Hz "
        f"pair={pair.value} cpu_workers={expected_cpu}"
        + (f" gpu_stress={gpu_stress}" if kind == "coupled" else "")
        + (f" piston_bg={'on' if piston_started else 'off'}" if piston_background else "")
    )
    print(f"Logging -> {csv_path}")
    time.sleep(warmup)

    rows: list[dict[str, Any]] = []
    polls = 0
    max_load = 0.0
    max_gpu_util = 0.0
    t0 = time.monotonic()
    t_end = t0 + duration
    cpu_alive_end = 0
    gpu_alive_end = 0
    loop_times: list[float] = []

    try:
        with csv_path.open("a", newline="", encoding="utf-8") as fh, poll_log_path.open(
            "a", encoding="utf-8"
        ) as plf:
            w = csv.writer(fh)
            if new_file:
                w.writerow(CSV_HEADER)
            while time.monotonic() < t_end:
                iter_start = time.monotonic()
                cpu_procs = ensure_stressor(cpu_procs, cores)
                cpu_alive = stress_alive(cpu_procs)
                gpu_alive = sum(1 for p in gpu_procs if p.is_alive()) if gpu_procs else 0
                polls += 1

                sample = session.commit(session.poll())
                master = compute_master_rid(sample)

                gpu_util = 0.0
                gpu_temp = 0.0
                if kind == "coupled":
                    try:
                        g = read_gpu(0)
                        gpu_util = float(g.util_pct)
                        gpu_temp = float(g.temp_c)
                    except Exception:
                        pass
                max_load = max(max_load, sample.cpu_load_pct)
                max_gpu_util = max(max_gpu_util, gpu_util)

                subs = master.subsystems
                row = {
                    "timestamp": sample.timestamp,
                    "t_s": round(iter_start - t0, 3),
                    "master_s_n": master.master_s_n,
                    "master_rsr": master.master_rsr,
                    "master_ltp": master.master_ltp,
                    "master_rle": master.master_rle,
                    "master_status": master.status,
                    "cpu_automaton_s_n": subs["cpu_automaton"].s_n,
                    "piston_s_n": subs["piston"].s_n,
                    "gpu_s_n": subs["gpu"].s_n,
                    "coolant_loop_s_n": subs["coolant_loop"].s_n,
                    "cpu_load_pct": sample.cpu_load_pct,
                    "gpu_util_pct": gpu_util,
                    "gpu_temp_c": gpu_temp,
                    "a_c": sample.a_c,
                    "b_c": sample.b_c,
                    "n_subsystems": master.n_subsystems,
                }
                rows.append(row)
                w.writerow([row[h] for h in CSV_HEADER])

                poll_rec = {
                    **row,
                    "poll": polls,
                    "stress_alive": cpu_alive,
                    "gpu_stress_alive": gpu_alive,
                    "stress_mode": kind,
                    "loop_ms": round((time.monotonic() - iter_start) * 1000, 1),
                }
                plf.write(json.dumps(poll_rec) + "\n")

                if polls % 10 == 0 or polls == 1:
                    print(
                        f"  poll={polls:3d} Master_S_n={master.master_s_n:.4f} "
                        f"cpu={subs['cpu_automaton'].s_n:.3f} pis={subs['piston'].s_n:.3f} "
                        f"gpu={subs['gpu'].s_n:.3f} coo={subs['coolant_loop'].s_n:.3f} "
                        f"load={sample.cpu_load_pct:.0f}%"
                        + (f" gutil={gpu_util:.0f}%" if kind == "coupled" else "")
                    )

                cpu_alive_end = cpu_alive
                gpu_alive_end = gpu_alive
                loop_times.append(time.monotonic() - iter_start)

                deadline = t0 + polls * sample_interval
                sleep_s = deadline - time.monotonic()
                if sleep_s > 0:
                    time.sleep(sleep_s)
    finally:
        stop_stressor(cpu_procs)
        if gpu_procs:
            stop_gpu_stress(gpu_procs)
        if piston_background and piston_started:
            stop_piston_background()

    if rows:
        last_master = compute_master_rid(session.commit(session.poll()))
        publish_master_rid(last_master, patch_supervisor=True)

    wall_s = time.monotonic() - t0
    master_sns = [float(r["master_s_n"]) for r in rows]
    expected_polls = max(1, int(duration / sample_interval))
    actual_hz = polls / wall_s if wall_s > 0 else 0.0
    mean_loop_ms = (sum(loop_times) / len(loop_times) * 1000) if loop_times else 0.0

    summary: dict[str, Any] = {
        "version": VERSION,
        "capture_kind": kind,
        "duration_s": duration,
        "pair": pair.value,
        "stress": True,
        "stress_mode": kind,
        "sample_interval_s": sample_interval,
        "polls": polls,
        "expected_polls": expected_polls,
        "poll_ratio": round(polls / expected_polls, 3) if expected_polls else 0,
        "actual_hz": round(actual_hz, 3),
        "mean_loop_ms": round(mean_loop_ms, 1),
        "wall_s": round(wall_s, 2),
        "piston_background": piston_background and piston_started,
        "n_logged": len(rows),
        "csv": str(csv_path),
        "poll_log": str(poll_log_path),
        "cpu_load_max_pct": max_load,
        "gpu_util_max_pct": max_gpu_util if kind == "coupled" else None,
        "stress_workers_alive_end": cpu_alive_end,
        "gpu_stress_alive_end": gpu_alive_end if kind == "coupled" else None,
        "master_s_n_min": min(master_sns) if master_sns else None,
        "master_s_n_max": max(master_sns) if master_sns else None,
        "master_s_n_mean": sum(master_sns) / len(master_sns) if master_sns else None,
        "s_n_mean": sum(master_sns) / len(master_sns) if master_sns else None,
        "s_n_min": min(master_sns) if master_sns else None,
        "canonical": polls >= int(expected_polls * 0.9),
    }
    if rows:
        for key in ("cpu_automaton_s_n", "piston_s_n", "gpu_s_n", "coolant_loop_s_n"):
            vals = [float(r[key]) for r in rows]
            summary[f"{key}_mean"] = sum(vals) / len(vals)
            summary[f"{key}_min"] = min(vals)

    out_json = csv_path.with_suffix(".summary.json")
    verdict = validate_summary(summary, summary_path=out_json)
    summary["capture_verdict"] = verdict.verdict
    summary["capture_reasons"] = verdict.reasons
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if publish:
        publish_capture(summary, verdict)

    print("\n--- Plant Master RID summary ---")
    print(
        f"Polls: {polls}/{expected_polls} ({actual_hz:.2f} Hz)  "
        f"mean_loop={mean_loop_ms:.0f}ms  canonical={summary['canonical']}"
    )
    print(
        f"Master_S_n mean: {summary.get('master_s_n_mean', 0):.4f}  "
        f"min: {summary.get('master_s_n_min', 0):.4f}"
    )
    print(
        f"CPU load max: {max_load:.0f}%"
        + (f"  GPU util max: {max_gpu_util:.0f}%" if kind == "coupled" else "")
        + f"  workers end: cpu={cpu_alive_end}"
        + (f" gpu={gpu_alive_end}" if kind == "coupled" else "")
    )
    if publish:
        print(f"Verdict: {verdict.verdict} -> artifacts/auto/plant/last_stability_capture.json")
    else:
        print(f"Verdict: {verdict.verdict} (not published)")
    for r in verdict.reasons:
        print(f"  - {r}")
    return summary


def run_coupled_rid_capture(**kwargs: Any) -> dict[str, Any]:
    return run_plant_master_capture(kind="coupled", **kwargs)


def run_core_spread_capture(**kwargs: Any) -> dict[str, Any]:
    return run_plant_master_capture(kind="core_spread", **kwargs)
