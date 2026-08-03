"""Post-run coupled black hole report — trajectory + cpu_gpu triad plot."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.coupled_black_hole import COUPLED_LOG_PATH, COUPLED_ARTIFACTS
from lib.rid_trajectory_plot import main as trajectory_plot
from lib.rid_triad import sensor_triad


def coupled_log_to_cpu_gpu_triad_csv(log_path: Path, out_csv: Path) -> int:
    """Extract cpu temp vs gpu die from coupled log -> triad CSV (on change only)."""
    rows_out: list[dict[str, Any]] = []
    prev_rle: float | None = None
    prev_ts: datetime | None = None
    t0: datetime | None = None
    last_ab: tuple[float, float] | None = None

    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        ts = datetime.fromisoformat(row["timestamp"])
        if t0 is None:
            t0 = ts
        dt = (ts - prev_ts).total_seconds() if prev_ts else 0.0
        prev_ts = ts
        a = float(row["cpu"]["temp_c"])
        b = float(row["gpu"]["temp_c"])
        if last_ab is not None and (round(a, 2), round(b, 2)) == last_ab:
            continue
        last_ab = (round(a, 2), round(b, 2))
        ltp, rsr, rle, rle_rate = sensor_triad(a, b, prev_rle, dt)
        prev_rle = rle
        rows_out.append({
            "t_s": round((ts - t0).total_seconds(), 3),
            "a_c": a,
            "b_c": b,
            "a_label": "cpu_package_c",
            "b_label": "gpu_die_c",
            "ltp": round(ltp, 4),
            "rsr": round(rsr, 4),
            "rle": round(rle, 6),
            "rle_rate": round(rle_rate, 6),
            "coupled_s_n": row.get("coupled_s_n"),
            "regime": row.get("regime"),
        })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if not rows_out:
        out_csv.write_text("", encoding="utf-8")
        return 0
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    return len(rows_out)


def generate_coupled_reports(
    log_path: Path | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    log = log_path or COUPLED_LOG_PATH
    out = out_dir or (COUPLED_ARTIFACTS / "reports")
    out.mkdir(parents=True, exist_ok=True)

    traj = trajectory_plot(log, out / "trajectory")
    triad_csv = out / "cpu_gpu_triad.csv"
    n_triad = coupled_log_to_cpu_gpu_triad_csv(log, triad_csv)

    plot_png = out / "cpu_gpu_triad_plot.png"
    plotted = False
    if n_triad > 0:
        import rid_plot_main as rpm
        plotted = rpm.plot_csv(triad_csv, plot_png)

    report = {
        "log": str(log),
        "trajectory": traj,
        "cpu_gpu_triad_csv": str(triad_csv),
        "cpu_gpu_triad_points": n_triad,
        "cpu_gpu_triad_png": str(plot_png) if plotted else None,
        "out_dir": str(out),
    }
    from lib.coupled_plant_capture import finalize_coupled_capture

    report["plant_capture"] = finalize_coupled_capture(log, n_triad=n_triad)
    (out / "coupled_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
