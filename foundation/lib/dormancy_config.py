"""Plant-calibrated Master S_n dormancy threshold (CPU config + Security Law 5).

Architect doctrine: raise toward 1 = tighten; lower = more room (never below floor).
Auto-benchmark proposes; --apply writes shared JSON that Rust + Python both read.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS, FOUNDATION_ROOT

THRESHOLD_PATH = AUTO_ARTIFACTS / "dormancy_threshold.json"
BENCHMARK_LATEST = AUTO_ARTIFACTS / "dormancy_benchmark_latest.json"
DEFAULT = 0.45
FLOOR = 0.32  # hard — never auto-loosen below this
CEILING = 0.65  # hard — never auto-tighten absurdly without Architect


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp_threshold(x: float) -> float:
    return float(max(FLOOR, min(CEILING, round(float(x), 4))))


def load_threshold() -> float:
    """Effective dormancy used by Python status gates."""
    if THRESHOLD_PATH.is_file():
        try:
            data = json.loads(THRESHOLD_PATH.read_text(encoding="utf-8"))
            return clamp_threshold(float(data.get("dormancy_threshold") or DEFAULT))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    cfg = FOUNDATION_ROOT / "cpu_config.json"
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if "dormancy_threshold" in data:
                return clamp_threshold(float(data["dormancy_threshold"]))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return DEFAULT


def write_threshold(
    value: float,
    *,
    source: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thr = clamp_threshold(value)
    payload = {
        "dormancy_threshold": thr,
        "floor": FLOOR,
        "ceiling": CEILING,
        "default_doctrine": DEFAULT,
        "source": source,
        "updated_at": _utc(),
        "evidence": evidence or {},
        "note": "Shared by Python status + Rust Law 5 (security_core reads this file).",
    }
    THRESHOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLD_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Mirror into cpu_config for operators
    cfg_path = FOUNDATION_ROOT / "cpu_config.json"
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg["dormancy_threshold"] = thr
            cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    return payload


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return DEFAULT
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _history_master_sn(limit: int = 200) -> list[float]:
    """Pull past Master S_n from pulse / autonomous / integrity if present."""
    vals: list[float] = []
    candidates = [
        AUTO_ARTIFACTS / "pulse.json",
        AUTO_ARTIFACTS / "autonomous_session.jsonl",
        AUTO_ARTIFACTS / "voice_events.jsonl",
    ]
    # pulse is single object
    pulse = AUTO_ARTIFACTS / "pulse.json"
    if pulse.is_file():
        try:
            data = json.loads(pulse.read_text(encoding="utf-8"))
            sn = data.get("master_s_n") or (data.get("sample") or {}).get("s_n")
            if sn is not None:
                vals.append(float(sn))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    for path in (
        AUTO_ARTIFACTS / "autonomous_session.jsonl",
        FOUNDATION_ROOT / "artifacts" / "models" / "prt_cycles.jsonl",
    ):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            for key in ("master_s_n", "s_n"):
                if key in row:
                    try:
                        vals.append(float(row[key]))
                    except (TypeError, ValueError):
                        pass
            before = (row.get("observe_before") or {}).get("master_s_n")
            after = (row.get("observe_after") or {}).get("master_s_n")
            for v in (before, after):
                if v is not None:
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        pass
            beat = row.get("report") or row.get("beat") or {}
            if isinstance(beat, dict) and beat.get("master_s_n") is not None:
                try:
                    vals.append(float(beat["master_s_n"]))
                except (TypeError, ValueError):
                    pass
    return vals


def live_benchmark(*, seconds: float = 20.0, interval: float = 1.0) -> dict[str, Any]:
    """Idle plant samples — no GPU load (safe while not training speak)."""
    from lib.master_rid import compute_master_rid
    from lib.rid_telemetry import sample_once

    n = max(3, int(seconds / max(0.5, interval)))
    samples: list[float] = []
    plant: list[float] = []
    for _ in range(n):
        sample = sample_once()
        master = compute_master_rid(sample)
        samples.append(float(master.master_s_n))
        plant.append(float(sample.s_n))
        time.sleep(interval)
    samples_sorted = sorted(samples)
    hist = _history_master_sn(250)
    hist_sorted = sorted(hist) if hist else []

    idle_p10 = _percentile(samples_sorted, 10)
    idle_p25 = _percentile(samples_sorted, 25)
    idle_med = _percentile(samples_sorted, 50)
    idle_mean = sum(samples) / len(samples)

    # Prefer p25 − margin so we don't slam to the hard floor on noisy/low idle.
    # Cap loosening: one auto-apply may not drop more than 0.08 below doctrine 0.45
    # without Architect --force (keeps alignment from free-falling to FLOOR).
    margin = 0.04
    proposed_raw = idle_p25 - margin
    if idle_med >= 0.55:
        proposed_raw = max(proposed_raw, min(DEFAULT, idle_p10 - 0.03))
    if hist_sorted:
        hist_p25 = _percentile(hist_sorted, 25)
        proposed_raw = 0.55 * proposed_raw + 0.45 * (hist_p25 - margin)
    max_auto_loosen = DEFAULT - 0.08  # 0.37
    if proposed_raw < max_auto_loosen:
        proposed_raw = max_auto_loosen
    proposed = clamp_threshold(proposed_raw)
    current = load_threshold()

    report = {
        "timestamp": _utc(),
        "current_threshold": current,
        "proposed_threshold": proposed,
        "delta": round(proposed - current, 4),
        "live": {
            "n": len(samples),
            "seconds": seconds,
            "master_s_n_mean": round(idle_mean, 4),
            "master_s_n_p10": round(idle_p10, 4),
            "master_s_n_p25": round(idle_p25, 4),
            "master_s_n_median": round(idle_med, 4),
            "master_s_n_min": round(min(samples), 4),
            "master_s_n_max": round(max(samples), 4),
            "plant_s_n_mean": round(sum(plant) / len(plant), 4) if plant else None,
        },
        "history": {
            "n": len(hist),
            "p10": round(_percentile(hist_sorted, 10), 4) if hist_sorted else None,
            "median": round(_percentile(hist_sorted, 50), 4) if hist_sorted else None,
        },
        "bounds": {"floor": FLOOR, "ceiling": CEILING, "doctrine_default": DEFAULT},
        "rationale": (
            "Dormancy ≈ idle_p10 − margin, blended with history, clamped. "
            "Lowers floor only when this plant's healthy idle sits near 0.45 "
            "(GPU speak dips would otherwise permanently Law-5). "
            "Raise toward 1 only when idle clearly supports tighter alignment."
        ),
        "path": str(THRESHOLD_PATH).replace("\\", "/"),
        "requires_rust_reload": True,
        "apply_hint": "dormancy_main.py apply --from-benchmark  (rebuild security_core if .pyd stale)",
    }
    BENCHMARK_LATEST.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
