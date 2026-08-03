"""RID 3D trajectory plotter — PC port using lib/rid_triad (Phone math)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from lib.rid_triad import sensor_triad


@dataclass
class TriadPoint:
    t_s: float
    beat: int
    a: float
    b: float
    input_cmd: float
    output_meas: float
    gap: float
    ltp: float
    rsr: float
    rle: float
    rle_rate: float
    s_n: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def phone_triad(a: float, b: float, prev_rle: float | None, dt: float) -> tuple[float, float, float, float, float]:
    ltp, rsr, rle, rle_rate = sensor_triad(a, b, prev_rle, dt)
    scale = max(abs(ltp), abs(rsr), abs(rle), 1e-6)
    na, nb, nc = abs(ltp) / scale, abs(rsr) / scale, abs(rle) / scale
    s_n = (na * nb * nc) ** (1.0 / 3.0) if na > 0 and nb > 0 and nc > 0 else 0.0
    return ltp, rsr, rle, rle_rate, s_n


def load_coupled_log(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def trajectory_from_coupled_log(rows: Iterable[dict[str, Any]]) -> list[TriadPoint]:
    points: list[TriadPoint] = []
    prev_rle: float | None = None
    prev_ts: datetime | None = None
    t0: datetime | None = None

    for row in rows:
        ts = datetime.fromisoformat(row["timestamp"])
        if t0 is None:
            t0 = ts
        dt = (ts - prev_ts).total_seconds() if prev_ts else 0.0
        prev_ts = ts

        cpu = row["cpu"]
        gpu = row["gpu"]
        a = float(cpu["temp_c"])
        b = float(gpu["temp_c"])
        input_cmd = (float(cpu.get("density", 0)) + float(gpu.get("density", 0))) / 2.0
        output_meas = (a + b) / 2.0
        gap = output_meas - input_cmd

        ltp, rsr, rle, rle_rate, s_n = phone_triad(a, b, prev_rle, dt)
        prev_rle = rle

        points.append(
            TriadPoint(
                t_s=(ts - t0).total_seconds(),
                beat=int(row["beat"]),
                a=a,
                b=b,
                input_cmd=input_cmd,
                output_meas=output_meas,
                gap=gap,
                ltp=ltp,
                rsr=rsr,
                rle=rle,
                rle_rate=rle_rate,
                s_n=s_n,
            )
        )
    return points


def write_csv(path: Path, points: list[TriadPoint]) -> None:
    header = (
        "t_s,beat,a,b,input_cmd,output_meas,gap,ltp,rsr,rle,rle_rate,s_n\n"
    )
    lines = [header]
    for p in points:
        lines.append(
            f"{p.t_s:.3f},{p.beat},{p.a:.4f},{p.b:.4f},"
            f"{p.input_cmd:.4f},{p.output_meas:.4f},{p.gap:.4f},"
            f"{p.ltp:.4f},{p.rsr:.4f},{p.rle:.4f},{p.rle_rate:.6f},{p.s_n:.4f}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")


def plot_trajectory(path: Path, points: list[TriadPoint]) -> bool:
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    except ImportError:
        return False

    if not points:
        return False

    xs = [p.ltp for p in points]
    ys = [p.rle for p in points]
    zs = [p.t_s for p in points]
    colors = [p.s_n for p in points]

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    sc = ax.scatter(xs, ys, zs, c=colors, cmap="RdYlGn", s=20, depthshade=True)
    ax.plot(xs, ys, zs, color="gray", alpha=0.35, linewidth=0.8)
    ax.set_xlabel("Input — LTP (A+B)/2")
    ax.set_ylabel("Gap — RLE (A×B − expected²)")
    ax.set_zlabel("Time (s)")
    ax.set_title("RID trajectory — L:/Phone dual-sensor triad on coupled collapse log")
    fig.colorbar(sc, ax=ax, label="S_n (Phone geom. mean)")
    plt.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def summarize(points: list[TriadPoint]) -> dict[str, Any]:
    if not points:
        return {"n": 0}
    gaps = [p.gap for p in points]
    sns = [p.s_n for p in points]
    return {
        "n": len(points),
        "duration_s": points[-1].t_s,
        "input_cmd_range": [min(p.input_cmd for p in points), max(p.input_cmd for p in points)],
        "output_meas_range": [min(p.output_meas for p in points), max(p.output_meas for p in points)],
        "gap_min": min(gaps),
        "gap_max": max(gaps),
        "s_n_min": min(sns),
        "s_n_max": max(sns),
        "s_n_mean": sum(sns) / len(sns),
        "source_math": "L:/Phone/ridv14.py + ridplot.py",
        "axes": {"x": "LTP (input, add)", "y": "RLE (gap, sub)", "z": "time"},
    }


def main(log_path: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = load_coupled_log(log_path)
    points = trajectory_from_coupled_log(rows)
    csv_path = out_dir / "rid_trajectory.csv"
    png_path = out_dir / "rid_trajectory_3d.png"
    json_path = out_dir / "rid_trajectory_summary.json"

    write_csv(csv_path, points)
    plotted = plot_trajectory(png_path, points)
    summary = summarize(points)
    summary["log"] = str(log_path)
    summary["csv"] = str(csv_path)
    summary["png"] = str(png_path) if plotted else None
    summary["plotted"] = plotted
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    import argparse

    default_log = Path(__file__).resolve().parents[1] / "artifacts" / "auto" / "black_hole" / "coupled" / "collapse_log.jsonl"
    default_out = Path(__file__).resolve().parents[1] / "artifacts" / "rid" / "trajectory"
    ap = argparse.ArgumentParser(description="Plot RID 3D trajectory from Phone triad math")
    ap.add_argument("--log", type=Path, default=default_log)
    ap.add_argument("--out", type=Path, default=default_out)
    args = ap.parse_args()
    result = main(args.log, args.out)
    print(json.dumps(result, indent=2))
