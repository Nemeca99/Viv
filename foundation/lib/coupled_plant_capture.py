"""Validate coupled black-hole runs for AIOS plant evidence."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.coupled_black_hole import COUPLED_LOG_PATH
from lib.plant_piston_bridge import publish_capture
from lib.stability_capture import validate_summary


def coupled_log_summary(log_path: Path, *, n_triad: int) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        return {
            "pair": "cpu_gpu",
            "stress": True,
            "stress_mode": "coupled",
            "polls": 0,
            "n_logged": 0,
            "csv": str(log_path),
        }
    t0 = datetime.fromisoformat(rows[0]["timestamp"])
    t1 = datetime.fromisoformat(rows[-1]["timestamp"])
    duration = max(0.0, (t1 - t0).total_seconds())
    cpu_temps = [float(r["cpu"]["temp_c"]) for r in rows if "cpu" in r]
    gpu_temps = [float(r["gpu"]["temp_c"]) for r in rows if "gpu" in r]
    sn_vals = [float(r.get("coupled_s_n") or 0) for r in rows]
    return {
        "version": "coupled-1.0",
        "duration_s": duration,
        "pair": "cpu_gpu",
        "stress": True,
        "stress_mode": "coupled",
        "polls": len(rows),
        "n_logged": n_triad,
        "csv": str(log_path),
        "cpu_temp_max": max(cpu_temps) if cpu_temps else None,
        "gpu_temp_max": max(gpu_temps) if gpu_temps else None,
        "coupled_s_n_min": min(sn_vals) if sn_vals else None,
        "coupled_s_n_mean": sum(sn_vals) / len(sn_vals) if sn_vals else None,
        "horizon_crossed": any(r.get("cpu", {}).get("collapsed") or r.get("gpu", {}).get("collapsed") for r in rows),
    }


def finalize_coupled_capture(log_path: Path | None = None, *, n_triad: int = 0) -> dict[str, Any]:
    log = log_path or COUPLED_LOG_PATH
    summary = coupled_log_summary(log, n_triad=n_triad)
    summary_path = log.with_suffix(".plant.summary.json")
    verdict = validate_summary(summary, summary_path=summary_path)
    summary["capture_verdict"] = verdict.verdict
    summary["capture_reasons"] = verdict.reasons
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    publish_capture(summary, verdict)
    return {"summary": summary, "verdict": verdict.to_dict(), "summary_path": str(summary_path)}
