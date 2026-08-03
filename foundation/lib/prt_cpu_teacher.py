"""CPU-first RID teacher — Mad Libs / hold targets built on CPU (no GPU required).

GPU only consumes these packets. Plant still grades final measure.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.prt_cpu_judge import madlibs_options

_TRIAD_KEYS = (
    ("rsr", "predicted_master_rsr", "master_rsr"),
    ("ltp", "predicted_master_ltp", "master_ltp"),
    ("rle", "predicted_master_rle", "master_rle"),
)

CPU_TEACH_GOLD = AUTO_ARTIFACTS / "cpu_teach_gold.jsonl"


def hold_triad_from_before(before: dict[str, Any]) -> dict[str, float]:
    """CPU hold teacher: next-step guess = current measured triad."""
    out: dict[str, float] = {}
    for _short, pk, ak in _TRIAD_KEYS:
        if before.get(ak) is not None:
            out[pk] = round(float(before[ak]), 4)
    return out


def momentum_triad_from_before(
    before: dict[str, Any],
    *,
    blend: float = 0.85,
) -> dict[str, float]:
    """Hold blended with last after-tick (slight continuity) — still CPU-only."""
    hold = hold_triad_from_before(before)
    if len(hold) < 3:
        return hold
    latest = AUTO_ARTIFACTS / "cpu_rid_tick_latest.json"
    if not latest.is_file():
        return hold
    try:
        row = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return hold
    # Use previous after S_n channels if present on observe_after style keys — tick stores s_n only.
    # Soft nudge: pull hold S_n toward last after by tiny channel-equal blend.
    try:
        prev_sn = float(row.get("master_s_n_after"))
        cur_sn = float(
            (max(hold["predicted_master_rsr"], 1e-9)
             * max(hold["predicted_master_ltp"], 1e-9)
             * max(hold["predicted_master_rle"], 1e-9))
            ** (1.0 / 3.0)
        )
    except (TypeError, ValueError, KeyError):
        return hold
    if cur_sn <= 0:
        return hold
    # Scale channels toward previous after S_n without inventing channel-specific drift.
    scale = (blend * 1.0) + ((1.0 - blend) * (prev_sn / cur_sn))
    scale = max(0.92, min(1.08, scale))
    return {k: round(max(0.0, min(1.0, v * scale)), 4) for k, v in hold.items()}


def format_cpu_madlibs_block(
    before: dict[str, Any],
    *,
    round_i: int = 0,
    seed: int | None = None,
    full_triad: bool = True,
) -> dict[str, Any]:
    """Always-on CPU teach packet: Mad Libs from live plant hold (1 or all channels)."""
    hold = momentum_triad_from_before(before) or hold_triad_from_before(before)
    if not hold:
        return {"ok": False, "block": "", "channel": None}
    channels = [
        pk
        for pk in ("predicted_master_rsr", "predicted_master_ltp", "predicted_master_rle")
        if pk in hold
    ]
    rng = random.Random(
        seed if seed is not None else (round_i * 1009 + int(sum(hold.values()) * 1e4))
    )
    lines = [
        "[TAG:cpu_teach] RID Mad Libs — CPU built from live plant hold (this host).",
        "Fill the triad by choosing the best option per channel; emit full triad JSON.",
        f"Host hold triad: {json.dumps(hold, separators=(',', ':'))}",
    ]
    channel_packs: list[dict[str, Any]] = []
    use = channels if full_triad else [channels[int(round_i) % len(channels)]]
    for pk in use:
        correct = float(hold[pk])
        opts = madlibs_options(correct, rng=rng)
        lines.append(f"{pk}:")
        for lab, val in zip("ABCD", opts):
            lines.append(f"  {lab}) {val}")
        channel_packs.append({"channel": pk, "correct": correct, "options": opts})
    lines.append("Emit numeric values in JSON (not only letters).")
    primary = use[0]
    return {
        "ok": True,
        "block": "\n".join(lines) + "\n",
        "channel": primary,
        "correct": float(hold[primary]),
        "options": channel_packs[0]["options"] if channel_packs else [],
        "channels": channel_packs,
        "hold": hold,
        "full_triad": full_triad,
    }


def cpu_hold_prediction(before: dict[str, Any], *, use_momentum: bool = True) -> dict[str, Any]:
    """Pure-CPU observe prediction (no GPU) — baseline teacher for RID mastery."""
    hold = (
        momentum_triad_from_before(before)
        if use_momentum
        else hold_triad_from_before(before)
    )
    if len(hold) < 3:
        return {"ok": False, "reason": "incomplete_before", "prediction": None}
    rsr, ltp, rle = (
        hold["predicted_master_rsr"],
        hold["predicted_master_ltp"],
        hold["predicted_master_rle"],
    )
    sn = round((max(rsr, 1e-9) * max(ltp, 1e-9) * max(rle, 1e-9)) ** (1.0 / 3.0), 4)
    return {
        "ok": True,
        "reason": "cpu_hold_momentum" if use_momentum else "cpu_hold",
        "prediction": {
            **hold,
            "predicted_master_s_n": sn,
            "confidence": "high",
            "triad_complete": True,
            "parse": "cpu_hold",
            "raw": "cpu_hold",
        },
    }


def append_cpu_teach_gold(row: dict[str, Any]) -> None:
    """Append a successful CPU teach/grade row for offline curriculum."""
    AUTO_ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with CPU_TEACH_GOLD.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
