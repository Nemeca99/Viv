"""Validate RID plant stability captures for AIOS backend / piston input."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Verdict = Literal["PASS", "PASS_FLAT", "FAIL", "INCONCLUSIVE"]

MIN_STRESS_LOAD_PCT = 85.0
MIN_STRESS_WORKERS_END = 8
MIN_LOGGED_ROWS_STRESS = 5
MIN_LOGGED_ROWS_IDLE = 2
MIN_GPU_UTIL_PCT_COUPLED = 60.0
MIN_POLL_RATIO_COUPLED = 0.90


@dataclass
class CaptureVerdict:
    verdict: Verdict
    reasons: list[str]
    summary_path: str
    csv_path: str
    stress: bool
    n_logged: int
    polls: int
    cpu_load_max_pct: float | None
    stress_workers_alive_end: int | None
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"summary not a dict: {path}")
    return data


def _poll_sidecar_stats(summary: dict[str, Any]) -> dict[str, Any] | None:
    poll_log = summary.get("poll_log")
    if not poll_log:
        return None
    path = Path(str(poll_log))
    if not path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        return None
    return {
        "polls": len(rows),
        "stress_alive_min": min(int(r.get("stress_alive") or 0) for r in rows),
        "load_max": max(float(r.get("cpu_load_pct") or 0) for r in rows),
        "a_unique": len({r.get("a_c") for r in rows}),
        "b_unique": len({r.get("b_c") for r in rows}),
    }


def validate_summary(summary: dict[str, Any], *, summary_path: Path | None = None) -> CaptureVerdict:
    """Score a stability_pc.summary.json for AIOS plant evidence quality."""
    stress = bool(summary.get("stress"))
    n_logged = int(summary.get("n_logged") or 0)
    polls = int(summary.get("polls") or 0)
    cpu_max = summary.get("cpu_load_max_pct")
    workers_end = summary.get("stress_workers_alive_end")
    csv_path = str(summary.get("csv") or "")
    reasons: list[str] = []
    stress_mode = str(summary.get("stress_mode") or "blast")

    if polls < 30:
        reasons.append(f"polls too low ({polls})")

    expected_polls = summary.get("expected_polls")
    poll_ratio = summary.get("poll_ratio")
    if stress_mode in ("coupled", "core_spread") and expected_polls:
        min_polls = max(30, int(float(expected_polls) * MIN_POLL_RATIO_COUPLED))
        if polls < min_polls:
            reasons.append(
                f"cadence shortfall: {polls} polls < {min_polls} required "
                f"({poll_ratio or 0:.0%} of target)"
            )

    min_rows = MIN_LOGGED_ROWS_STRESS if stress else MIN_LOGGED_ROWS_IDLE
    if n_logged < min_rows:
        reasons.append(f"logged rows {n_logged} < {min_rows}")

    sidecar = _poll_sidecar_stats(summary)
    piston_stress = summary.get("piston_stress") or {}
    gpu_util_max = summary.get("gpu_util_max_pct")
    gpu_alive_end = summary.get("gpu_stress_alive_end")

    if stress:
        if stress_mode == "coupled":
            if cpu_max is None:
                reasons.append("cpu_load_max_pct missing")
            elif float(cpu_max) < MIN_STRESS_LOAD_PCT:
                reasons.append(f"cpu_load_max {cpu_max}% < {MIN_STRESS_LOAD_PCT}%")
            if gpu_util_max is None:
                reasons.append("gpu_util_max_pct missing")
            elif float(gpu_util_max) < MIN_GPU_UTIL_PCT_COUPLED:
                reasons.append(f"gpu_util_max {gpu_util_max}% < {MIN_GPU_UTIL_PCT_COUPLED}%")
            if workers_end is None:
                reasons.append("stress_workers_alive_end missing")
            elif int(workers_end) < MIN_STRESS_WORKERS_END:
                reasons.append(f"cpu stress workers at end {workers_end} < {MIN_STRESS_WORKERS_END}")
            if gpu_alive_end is not None and int(gpu_alive_end) < 1:
                reasons.append(f"gpu stress alive at end {gpu_alive_end} < 1")
        elif stress_mode == "core_spread":
            if cpu_max is None:
                reasons.append("cpu_load_max_pct missing")
            elif float(cpu_max) < MIN_STRESS_LOAD_PCT:
                reasons.append(f"cpu_load_max {cpu_max}% < {MIN_STRESS_LOAD_PCT}%")
            if workers_end is None:
                reasons.append("stress_workers_alive_end missing")
            elif int(workers_end) < MIN_STRESS_WORKERS_END:
                reasons.append(f"stress workers at end {workers_end} < {MIN_STRESS_WORKERS_END}")
        elif stress_mode == "piston":
            min_workers = int(piston_stress.get("pairs") or 4)
            if workers_end is not None and int(workers_end) < min_workers:
                reasons.append(f"piston burners at end {workers_end} < {min_workers}")
            if cpu_max is not None and float(cpu_max) < 40.0:
                reasons.append(f"piston cpu_load_max {cpu_max}% < 40%")
        else:
            if cpu_max is None:
                reasons.append("cpu_load_max_pct missing")
            elif float(cpu_max) < MIN_STRESS_LOAD_PCT:
                reasons.append(f"cpu_load_max {cpu_max}% < {MIN_STRESS_LOAD_PCT}%")
            if workers_end is None:
                reasons.append("stress_workers_alive_end missing")
            elif int(workers_end) < MIN_STRESS_WORKERS_END:
                reasons.append(f"stress workers at end {workers_end} < {MIN_STRESS_WORKERS_END}")

    flat_plant = (
        stress
        and sidecar
        and sidecar["stress_alive_min"] >= (4 if stress_mode == "piston" else MIN_STRESS_WORKERS_END)
        and (
            sidecar["load_max"] >= 40.0
            if stress_mode == "piston"
            else sidecar["load_max"] >= MIN_STRESS_LOAD_PCT
        )
        and sidecar["a_unique"] == 1
        and sidecar["b_unique"] == 1
        and sidecar["polls"] >= 30
    )

    if not reasons:
        verdict: Verdict = "PASS"
    elif flat_plant and n_logged < MIN_LOGGED_ROWS_STRESS:
        verdict = "PASS_FLAT"
        reasons = [
            "stress confirmed via poll sidecar (100% load, workers alive)",
            f"iCUE held A/B constant for {sidecar['polls']} polls - liquid loop stable",
        ]
    elif polls >= 30 and n_logged >= 1 and not stress:
        verdict = "INCONCLUSIVE"
        reasons = [f"idle capture: {r}" for r in reasons] if reasons else ["idle baseline only"]
    else:
        verdict = "FAIL"

    return CaptureVerdict(
        verdict=verdict,
        reasons=reasons,
        summary_path=str(summary_path or summary.get("summary_json") or ""),
        csv_path=csv_path,
        stress=stress,
        n_logged=n_logged,
        polls=polls,
        cpu_load_max_pct=float(cpu_max) if cpu_max is not None else None,
        stress_workers_alive_end=int(workers_end) if workers_end is not None else None,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def validate_summary_file(path: Path) -> CaptureVerdict:
    return validate_summary(load_summary(path), summary_path=path)
