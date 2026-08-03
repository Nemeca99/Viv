"""Cascade chamber ledger — phone sim experts counter remade for Viv.

Not a real MoE router yet. Tracks intended chamber count under Architect
ceilings so Phase-2 MoE can inherit a continuous bottle book without
inventing a new soul.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from lib.growth_strain import load_growth_config, load_policy, save_growth_config, _emit
from lib.paths import AUTO_ARTIFACTS

CHAMBERS_PATH = AUTO_ARTIFACTS / "growth_chambers.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_chambers() -> dict[str, Any]:
    cfg = load_growth_config()
    policy = load_policy()
    defaults = {
        "version": "1.0.0",
        "cascade_experts": int(cfg.get("cascade_experts") or 8),
        "max_cascade_experts": int(policy.get("max_cascade_experts") or 32),
        "real_moe": False,
        "note": "Ledger only until moe_chamber_add is implemented. Phone sim grew virtual experts.",
        "events": [],
    }
    if CHAMBERS_PATH.is_file():
        try:
            data = json.loads(CHAMBERS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                defaults.update({k: v for k, v in data.items() if k != "events"})
                ev = data.get("events")
                if isinstance(ev, list):
                    defaults["events"] = ev[-50:]
        except (OSError, json.JSONDecodeError):
            pass
    defaults["cascade_experts"] = int(cfg.get("cascade_experts") or defaults["cascade_experts"])
    defaults["max_cascade_experts"] = int(policy.get("max_cascade_experts") or 32)
    return defaults


def save_chambers(state: dict[str, Any]) -> None:
    CHAMBERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = dict(state)
    out["updated_at"] = _utc()
    events = out.get("events") or []
    if isinstance(events, list) and len(events) > 50:
        out["events"] = events[-50:]
    CHAMBERS_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")


def bump_chambers(*, delta: int, reason: str, linked_actuator: str = "lora_widen") -> dict[str, Any]:
    """Increment cascade_experts under max ceiling. Ledger only — no MoE weights."""
    delta = max(0, int(delta))
    state = load_chambers()
    policy = load_policy()
    cur = int(state.get("cascade_experts") or 8)
    cap = int(policy.get("max_cascade_experts") or state.get("max_cascade_experts") or 32)
    if delta <= 0:
        return {"ok": True, "changed": False, "cascade_experts": cur, "max": cap}
    if cur >= cap:
        _emit("chamber_ceiling", current=cur, max=cap, reason=reason)
        return {"ok": False, "reason": "max_cascade_experts_ceiling", "cascade_experts": cur, "max": cap}

    new = min(cap, cur + delta)
    added = new - cur
    state["cascade_experts"] = new
    state["max_cascade_experts"] = cap
    state["real_moe"] = False
    ev = list(state.get("events") or [])
    ev.append(
        {
            "timestamp": _utc(),
            "old": cur,
            "new": new,
            "delta": added,
            "reason": reason,
            "linked_actuator": linked_actuator,
        }
    )
    state["events"] = ev
    save_chambers(state)

    gcfg = load_growth_config()
    gcfg["cascade_experts"] = new
    save_growth_config(gcfg)
    _emit("chamber_bump", old=cur, new=new, delta=added, reason=reason)
    return {
        "ok": True,
        "changed": True,
        "old": cur,
        "new": new,
        "delta": added,
        "max": cap,
        "real_moe": False,
        "path": str(CHAMBERS_PATH).replace("\\", "/"),
    }
