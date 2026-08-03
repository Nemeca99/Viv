"""CPU past-log integrity review — 'am I still good?' from artifacts (no GPU).

Reads recent pulse / PRT / voice egress. Does not load hf_lora.
Safe to run while PRT train occupies the GPU.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.dormancy_config import load_threshold
from lib.paths import ARTIFACTS, AUTO_ARTIFACTS, FOUNDATION_ROOT
from lib.prt_cycle import PRT_CYCLES_PATH, observe_state

INTEGRITY_LATEST = ARTIFACTS / "auto" / "integrity_review_latest.json"
VOICE_EVENTS = AUTO_ARTIFACTS / "voice_events.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tail_jsonl(path: Path, n: int = 40) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-max(1, n) :]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _prt_tail_stats(n: int = 40) -> dict[str, Any]:
    rows = [r for r in _tail_jsonl(PRT_CYCLES_PATH, n) if r.get("_type") == "prt_cycle"]
    labels: dict[str, int] = {}
    spoke = 0
    excluded = 0
    for r in rows:
        lab = str((r.get("score") or {}).get("label") or r.get("reason") or "?")
        labels[lab] = labels.get(lab, 0) + 1
        if (r.get("act") or {}).get("spoke"):
            spoke += 1
        if r.get("excluded"):
            excluded += 1
    reward = int(labels.get("REWARD") or 0)
    speak_rows = [r for r in rows if (r.get("act") or {}).get("act") == "speak" or (r.get("act") or {}).get("spoke")]
    speak_reward = sum(
        1 for r in speak_rows if (r.get("score") or {}).get("label") == "REWARD"
    )
    return {
        "cycles_scanned": len(rows),
        "labels": labels,
        "spoke_acts": spoke,
        "excluded": excluded,
        "reward_rate": (reward / len(rows)) if rows else None,
        "speak_cycles": len(speak_rows),
        "speak_reward_rate": (speak_reward / len(speak_rows)) if speak_rows else None,
    }


def _voice_egress_stats(n: int = 30) -> dict[str, Any]:
    rows = _tail_jsonl(VOICE_EVENTS, n)
    blocked = 0
    dormancy_blocks = 0
    ok = 0
    for r in rows:
        eg = r.get("egress") or {}
        blocked_flag = eg.get("allowed") is False or r.get("blocked") is True
        reason = str(eg.get("reason") or r.get("reason") or r.get("text_preview") or "")
        try:
            ev_sn = float(r.get("s_n")) if r.get("s_n") is not None else None
        except (TypeError, ValueError):
            ev_sn = None
        if blocked_flag:
            blocked += 1
            if (
                "LAW 5" in reason
                or "dormancy" in reason.lower()
                or "Forced dormancy" in reason
                or (ev_sn is not None and ev_sn < load_threshold())
            ):
                dormancy_blocks += 1
        elif r.get("ok") and not r.get("blocked"):
            ok += 1
    return {
        "events_scanned": len(rows),
        "ok": ok,
        "blocked": blocked,
        "law5_dormancy_blocks": dormancy_blocks,
    }


def review(*, prt_tail: int = 40, voice_tail: int = 30) -> dict[str, Any]:
    """Build integrity report from past artifacts + live Master S_n."""
    dormancy = load_threshold()

    now = observe_state()
    sn = float(now.get("master_s_n") or 0.0)
    prt = _prt_tail_stats(prt_tail)
    voice = _voice_egress_stats(voice_tail)

    flags: list[str] = []
    if sn < dormancy:
        flags.append("live_dormant")
    if sn <= 0.05:
        flags.append("near_dead")
    if (prt.get("reward_rate") or 1) < 0.4 and (prt.get("cycles_scanned") or 0) >= 10:
        flags.append("prt_reward_weak")
    if voice.get("law5_dormancy_blocks", 0) > 0:
        flags.append("recent_law5_no")

    # Soft bar for future SPRT (doc SPRT_V0_CONTRACT.md)
    speak_rr = prt.get("speak_reward_rate")
    sprt_ready = bool(
        speak_rr is not None
        and speak_rr >= 0.6
        and (prt.get("speak_cycles") or 0) >= 10
        and sn >= dormancy
    )

    report = {
        "timestamp": _utc(),
        "ok": True,
        "gpu_touched": False,
        "live": {
            "master_s_n": sn,
            "status": now.get("status"),
            "dormancy_threshold": dormancy,
            "active": sn >= dormancy,
        },
        "prt_past": prt,
        "voice_past": voice,
        "flags": flags,
        "sprt_v0_ready_soft": sprt_ready,
        "verdict": (
            "DORMANT — stay quiet; protect host"
            if sn < dormancy
            else ("STILL_GOOD — ACTIVE; past PRT soft-ok" if not flags else "ACTIVE_WITH_FLAGS")
        ),
        "note": "CPU-only integrity. Past informs present. No GPU.",
    }
    INTEGRITY_LATEST.parent.mkdir(parents=True, exist_ok=True)
    INTEGRITY_LATEST.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
