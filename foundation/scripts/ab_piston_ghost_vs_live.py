#!/usr/bin/env python3
"""A/B report: ghost (stale piston) vs live (piston_background) Stage-2 PRT windows.

Writes machine-readable JSON + human summary per ab-test-runner skill.
Run after ghost overnight completes; rerun after live overnight for full deltas.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lib.prt_cycle import PRT_CYCLES_PATH  # noqa: E402
from lib.prt_stage import (  # noqa: E402
    _cycle_blanked,
    _cycle_self_emit_ok,
    load_state,
    stage_def,
    telemetry_epoch_start,
)

EXPERIMENT_ID = "ab_piston_ghost_vs_live_v1"
AUDIT = _ROOT / "artifacts" / "audit"
OUT_JSON = AUDIT / f"{EXPERIMENT_ID}.json"
OUT_MD = AUDIT / f"{EXPERIMENT_ID}.md"
GHOST_SUMMARY = AUDIT / "prt_overnight_ghost_baseline_summary.json"
OVERNIGHT_STATE = _ROOT / "artifacts" / "auto" / "prt_overnight_state.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_cycles() -> list[dict]:
    rows: list[dict] = []
    if not PRT_CYCLES_PATH.is_file():
        return rows
    for ln in PRT_CYCLES_PATH.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("_type") == "prt_cycle" and r.get("ok") and not r.get("excluded"):
            rows.append(r)
    return rows


def _window_metrics(rows: list[dict], *, phase: int) -> dict:
    phase_rows = [r for r in rows if int(r.get("scaffold_phase") or 1) == phase]
    n = len(phase_rows)
    labels = Counter((r.get("score") or {}).get("label") or "?" for r in phase_rows)
    blanked = [r for r in phase_rows if _cycle_blanked(r)]
    emit_hits = sum(1 for r in blanked if _cycle_self_emit_ok(r))
    by_act = Counter((r.get("act") or {}).get("act") or "?" for r in phase_rows)
    trust_modes = Counter(
        ((r.get("score") or {}).get("trust") or {}).get("mode") or "none" for r in phase_rows
    )
    fa = trust_modes.get("FOLLOW", 0) + trust_modes.get("ADAPT", 0)
    follow_rate = round(trust_modes.get("FOLLOW", 0) / fa, 4) if fa else None
    return {
        "cycle_n": n,
        "labels": dict(labels),
        "reward_rate": round(labels.get("REWARD", 0) / n, 4) if n else 0.0,
        "neutral_rate": round(labels.get("NEUTRAL", 0) / n, 4) if n else 0.0,
        "punish_rate": round(labels.get("PUNISH", 0) / n, 4) if n else 0.0,
        "self_emit_rate": round(emit_hits / len(blanked), 4) if blanked else 0.0,
        "self_emit_hits": emit_hits,
        "self_emit_n": len(blanked),
        "by_act": dict(by_act),
        "trust_modes": dict(trust_modes),
        "follow_rate_among_fa": follow_rate,
        "first_ts": phase_rows[0].get("timestamp") if phase_rows else None,
        "last_ts": phase_rows[-1].get("timestamp") if phase_rows else None,
    }


def _delta(pilot: dict, baseline: dict, key: str) -> float | None:
    if not pilot.get("cycle_n") or not baseline.get("cycle_n"):
        return None
    return round(float(pilot.get(key) or 0) - float(baseline.get(key) or 0), 4)


def build_report() -> dict:
    state = load_state()
    stage = int(state.get("stage") or 2)
    sdef = stage_def(stage)
    phase = int(sdef["scaffold_phase"])
    epoch = telemetry_epoch_start()

    all_rows = _load_cycles()
    ghost_rows = all_rows if not epoch else [r for r in all_rows if (r.get("timestamp") or "") < epoch]
    live_rows = [] if not epoch else [r for r in all_rows if (r.get("timestamp") or "") >= epoch]

    baseline = _window_metrics(ghost_rows, phase=phase)
    pilot = _window_metrics(live_rows, phase=phase)

    overnight: dict = {}
    if OVERNIGHT_STATE.is_file():
        try:
            overnight = json.loads(OVERNIGHT_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    valid_baseline = baseline["cycle_n"] >= int(sdef["min_window"])
    valid_pilot = pilot["cycle_n"] >= int(sdef["min_window"])
    if not valid_pilot:
        verdict = "BASELINE_ONLY" if valid_baseline else "INCONCLUSIVE"
    elif not valid_baseline:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "COMPARABLE"

    report = {
        "experiment_id": EXPERIMENT_ID,
        "timestamp": _utc(),
        "verdict": verdict,
        "stage": stage,
        "scaffold_phase": phase,
        "telemetry_epoch_start": epoch,
        "stage_state_path": str(_ROOT / "artifacts" / "auto" / "prt_stage_state.json").replace("\\", "/"),
        "ghost_baseline_run": state.get("ghost_baseline_run"),
        "overnight_last": {
            "status": overnight.get("status"),
            "rounds_done": overnight.get("rounds_done"),
            "elapsed_h": overnight.get("elapsed_h"),
            "reason": overnight.get("reason"),
        },
        "baseline": {
            "label": "ghost_stale_piston",
            "valid_sample": valid_baseline,
            "min_window": sdef["min_window"],
            **baseline,
        },
        "pilot": {
            "label": "live_piston_background",
            "valid_sample": valid_pilot,
            "min_window": sdef["min_window"],
            **pilot,
        },
        "deltas_pilot_minus_baseline": {
            "reward_rate": _delta(pilot, baseline, "reward_rate"),
            "self_emit_rate": _delta(pilot, baseline, "self_emit_rate"),
            "punish_rate": _delta(pilot, baseline, "punish_rate"),
        },
        "runtime_health": {
            "note": "Ghost window uses stale piston_state.json anchor; pilot requires piston_background.",
            "overnight_config_path": str(_ROOT / "artifacts" / "models" / "prt_overnight_config.json").replace("\\", "/"),
        },
    }
    return report


def write_report(report: dict) -> tuple[Path, Path]:
    AUDIT.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    GHOST_SUMMARY.write_text(
        json.dumps(
            {
                "timestamp": report["timestamp"],
                "experiment_id": report["experiment_id"],
                "ghost_baseline": report["baseline"],
                "overnight_last": report["overnight_last"],
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    b, p, d = report["baseline"], report["pilot"], report["deltas_pilot_minus_baseline"]
    md = f"""# A/B: Piston Ghost vs Live (`{EXPERIMENT_ID}`)

**Verdict:** {report["verdict"]}  
**Generated:** {report["timestamp"]}  
**Telemetry epoch start:** {report.get("telemetry_epoch_start") or "(not set — ghost-only)"}

## Baseline (ghost / stale piston)

| Metric | Value |
|--------|-------|
| Cycles | {b["cycle_n"]} (valid sample: {b["valid_sample"]}) |
| REWARD rate | {b["reward_rate"]} |
| Self-emit rate | {b["self_emit_rate"]} ({b["self_emit_hits"]}/{b["self_emit_n"]}) |
| PUNISH rate | {b["punish_rate"]} |
| Window | {b.get("first_ts")} → {b.get("last_ts")} |

## Pilot (live piston_background)

| Metric | Value |
|--------|-------|
| Cycles | {p["cycle_n"]} (valid sample: {p["valid_sample"]}) |
| REWARD rate | {p["reward_rate"]} |
| Self-emit rate | {p["self_emit_rate"]} ({p["self_emit_hits"]}/{p["self_emit_n"]}) |
| PUNISH rate | {p["punish_rate"]} |
| Trust modes | {p.get("trust_modes")} |
| Follow rate (FOLLOW/(FOLLOW+ADAPT)) | {p.get("follow_rate_among_fa")} |

## Deltas (pilot − baseline)

- reward_rate: {d["reward_rate"]}
- self_emit_rate: {d["self_emit_rate"]}
- punish_rate: {d["punish_rate"]}

## Notes

- Promotion metrics use `telemetry_epoch_start` filter in `lib/prt_stage.py`.
- Do not claim improvement until pilot window has ≥ {p["min_window"]} Phase-{report["scaffold_phase"]} cycles.
"""
    OUT_MD.write_text(md, encoding="utf-8")
    return OUT_JSON, OUT_MD


def main() -> int:
    report = build_report()
    jpath, mpath = write_report(report)
    print(json.dumps({"ok": True, "verdict": report["verdict"], "json": str(jpath), "md": str(mpath)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
