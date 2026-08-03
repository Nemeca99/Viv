"""PRT growth-stage ladder — train to apex, then tighten (Architect doctrine).

Version-update-by-growth: hold difficulty until she reaches apex at the current
stage, then promote (tighten tolerance / fade scaffold) and snapshot the adapter
as a stage release. Never tighten ahead of capability — that was the original
failure (tolerances tighter than her accuracy).

Promotion is evidence-gated:
  - rolling window of scored cycles at the CURRENT stage
  - reward_rate >= apex_reward_rate
  - if scaffold_phase >= 2: self_emit_rate >= apex_self_emit_rate
No auto-demote. Demotion/rollback is operator-only.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.paths import ARTIFACTS, FOUNDATION_ROOT

STAGE_STATE_PATH = ARTIFACTS / "auto" / "prt_stage_state.json"
STAGE_EVENTS_PATH = ARTIFACTS / "auto" / "prt_stage_events.jsonl"
ADAPTER_DIR = FOUNDATION_ROOT / "models" / "gpu" / "viv_voice_lora"

# Ladder: tighten only after apex at previous stage.
STAGES: list[dict[str, Any]] = [
    {"stage": 1, "scaffold_phase": 1, "reward_tol": 0.05, "punish_tol": 0.15,
     "apex_reward_rate": 0.5, "apex_self_emit_rate": 0.0, "min_window": 20},
    {"stage": 2, "scaffold_phase": 2, "reward_tol": 0.05, "punish_tol": 0.15,
     "apex_reward_rate": 0.4, "apex_self_emit_rate": 0.5, "min_window": 30},
    {"stage": 3, "scaffold_phase": 2, "reward_tol": 0.035, "punish_tol": 0.12,
     "apex_reward_rate": 0.4, "apex_self_emit_rate": 0.7, "min_window": 30},
    {"stage": 4, "scaffold_phase": 3, "reward_tol": 0.035, "punish_tol": 0.12,
     "apex_reward_rate": 0.35, "apex_self_emit_rate": 0.7, "min_window": 40},
    {"stage": 5, "scaffold_phase": 3, "reward_tol": 0.025, "punish_tol": 0.10,
     "apex_reward_rate": 0.35, "apex_self_emit_rate": 0.8, "min_window": 40},
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(kind: str, payload: dict[str, Any]) -> None:
    STAGE_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STAGE_EVENTS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": _utc(), "kind": kind, **payload}, default=str) + "\n")


def stage_def(stage: int) -> dict[str, Any]:
    for s in STAGES:
        if s["stage"] == int(stage):
            return dict(s)
    return dict(STAGES[0])


def load_state() -> dict[str, Any]:
    if STAGE_STATE_PATH.is_file():
        try:
            st = json.loads(STAGE_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(st, dict) and st.get("stage"):
                return st
        except (json.JSONDecodeError, OSError):
            pass
    # Bootstrap: Phase-1 apex already demonstrated (reward_rate 0.73 on 26 cycles)
    return {
        "stage": 2,
        "since": _utc(),
        "note": "bootstrap at stage 2 (phase-1 apex proven 2026-07-16)",
        "releases": [],
    }


def save_state(state: dict[str, Any]) -> Path:
    STAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STAGE_STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    return STAGE_STATE_PATH


def telemetry_epoch_start() -> str | None:
    """ISO timestamp when live-telemetry epoch began (excludes prior ghost cycles)."""
    raw = load_state().get("telemetry_epoch_start")
    return str(raw) if raw else None


def begin_live_telemetry_epoch(
    *,
    note: str = "",
    ghost_baseline_path: str | None = None,
) -> dict[str, Any]:
    """Soft epoch boundary — promotion metrics count only cycles at/after this ts."""
    state = load_state()
    ts = _utc()
    state["telemetry_epoch_start"] = ts
    state["telemetry_epoch"] = "live"
    if note:
        state["telemetry_note"] = note
    if ghost_baseline_path:
        state["ghost_baseline_run"] = ghost_baseline_path.replace("\\", "/")
    save_state(state)
    _event(
        "telemetry_epoch_begin",
        {"epoch_start": ts, "note": note, "ghost_baseline_run": ghost_baseline_path},
    )
    return state


def _cycle_self_emit_ok(row: dict[str, Any]) -> bool:
    emit = row.get("self_emit") or (row.get("predict") or {}).get("self_emit") or {}
    return bool(emit.get("self_emit_ok") or emit.get("all_blanked_self_emitted"))


def _cycle_blanked(row: dict[str, Any]) -> list[str]:
    sc = row.get("scaffold") or {}
    blanked = sc.get("blanked")
    if blanked:
        return list(blanked)
    pred = row.get("predict") or {}
    return list(pred.get("scaffold_blanked") or [])


def rolling_stage_metrics(*, stage: int, tail: int = 400) -> dict[str, Any]:
    """Reward + self-emit rates over recent cycles recorded at this stage's phase."""
    from lib.prt_cycle import PRT_CYCLES_PATH

    sdef = stage_def(stage)
    phase = int(sdef["scaffold_phase"])
    window = int(sdef["min_window"])
    epoch_start = telemetry_epoch_start()
    rows: list[dict[str, Any]] = []
    if PRT_CYCLES_PATH.is_file():
        for ln in PRT_CYCLES_PATH.read_text(encoding="utf-8").splitlines()[-tail:]:
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if r.get("_type") != "prt_cycle" or r.get("excluded") or not r.get("ok"):
                continue
            if int(r.get("scaffold_phase") or 1) != phase:
                continue
            if epoch_start and (r.get("timestamp") or "") < epoch_start:
                continue
            rows.append(r)
    rows = rows[-window:]
    n = len(rows)
    reward = sum(1 for r in rows if (r.get("score") or {}).get("label") == "REWARD")
    blanked_rows = [r for r in rows if _cycle_blanked(r)]
    emit_hits = sum(1 for r in blanked_rows if _cycle_self_emit_ok(r))
    return {
        "stage": stage,
        "scaffold_phase": phase,
        "telemetry_epoch_start": epoch_start,
        "window_filled": n,
        "window_required": window,
        "reward_rate": round(reward / n, 4) if n else 0.0,
        "self_emit_rate": round(emit_hits / len(blanked_rows), 4) if blanked_rows else 0.0,
        "self_emit_n": len(blanked_rows),
        "reward_n": reward,
    }


def check_promotion(*, tail: int = 400) -> dict[str, Any]:
    """Evidence-gated promotion check. Returns decision; does not mutate state."""
    state = load_state()
    stage = int(state["stage"])
    sdef = stage_def(stage)
    metrics = rolling_stage_metrics(stage=stage, tail=tail)
    is_last = stage >= STAGES[-1]["stage"]
    window_ok = metrics["window_filled"] >= sdef["min_window"]
    reward_ok = metrics["reward_rate"] >= float(sdef["apex_reward_rate"])
    emit_ok = (
        float(sdef["apex_self_emit_rate"]) <= 0.0
        or metrics["self_emit_rate"] >= float(sdef["apex_self_emit_rate"])
    )
    eligible = window_ok and reward_ok and emit_ok and not is_last
    reason = (
        "at_top_stage" if is_last
        else "window_unfilled" if not window_ok
        else "reward_below_apex" if not reward_ok
        else "self_emit_below_apex" if not emit_ok
        else "apex_reached"
    )
    return {
        "ok": True,
        "stage": stage,
        "stage_def": sdef,
        "metrics": metrics,
        "eligible": eligible,
        "reason": reason,
        "inconclusive": not window_ok,
    }


def promote(*, operator: bool = False, tail: int = 400) -> dict[str, Any]:
    """Promote one stage if apex reached (or operator forces). Snapshots adapter."""
    decision = check_promotion(tail=tail)
    state = load_state()
    if not decision["eligible"] and not operator:
        _event("promotion_denied", {"decision": {k: decision[k] for k in ("stage", "reason", "metrics")}})
        return {**decision, "promoted": False}
    old_stage = int(state["stage"])
    new_stage = min(old_stage + 1, STAGES[-1]["stage"])
    release = snapshot_release(stage=old_stage)
    state.update({
        "stage": new_stage,
        "since": _utc(),
        "note": f"promoted {old_stage}->{new_stage} ({'operator' if operator else 'apex'})",
    })
    state.setdefault("releases", []).append(release)
    save_state(state)
    _event("promoted", {"from": old_stage, "to": new_stage, "operator": operator, "release": release})
    return {**decision, "promoted": True, "from": old_stage, "to": new_stage, "release": release}


def snapshot_release(*, stage: int) -> dict[str, Any]:
    """Copy live adapter as an immutable stage release (the 'model update')."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = ADAPTER_DIR.parent / f"viv_voice_lora_stage{stage}_{ts}"
    files = 0
    if ADAPTER_DIR.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        for item in ADAPTER_DIR.iterdir():
            if item.is_file():
                shutil.copy2(item, dest / item.name)
                files += 1
    rel = {
        "stage": stage,
        "path": str(dest).replace("\\", "/"),
        "files": files,
        "created": _utc(),
    }
    _event("release_snapshot", rel)
    return rel


def current_run_params() -> dict[str, Any]:
    """Stage-derived runtime params for cycles (phase + tolerances)."""
    state = load_state()
    sdef = stage_def(int(state["stage"]))
    return {
        "stage": int(state["stage"]),
        "scaffold_phase": int(sdef["scaffold_phase"]),
        "reward_tol": float(sdef["reward_tol"]),
        "punish_tol": float(sdef["punish_tol"]),
    }
