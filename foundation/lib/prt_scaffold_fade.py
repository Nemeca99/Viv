"""PRT scaffold fade — Phase 1 full → Phase 2 partial → Phase 3 none.

Phase 1: full value scaffold + prior_fill allowed (content under container).
Phase 2: blank some fields; prior_fill only for shown fields; she must emit blanks.
Phase 3: schema-only; no prior_fill (self-emit full triad).

Not grade inflation — fade the crutch so memory replaces scaffold.
"""
from __future__ import annotations

import json
from typing import Any

PHASE_FULL = 1
PHASE_PARTIAL = 2
PHASE_NONE = 3

_TRIAD_KEYS = (
    "predicted_master_rsr",
    "predicted_master_ltp",
    "predicted_master_rle",
)
_TASK_KEY_BY_ACT = {
    "life": "predicted_live_cells",
    "pulse": "predicted_mean_load_pct",
}
_ALL_PRED_KEYS = _TRIAD_KEYS + ("predicted_live_cells", "predicted_mean_load_pct")


def normalize_phase(raw: Any) -> int:
    try:
        p = int(raw)
    except (TypeError, ValueError):
        return PHASE_FULL
    if p in (PHASE_FULL, PHASE_PARTIAL, PHASE_NONE):
        return p
    return PHASE_FULL


def blank_keys_for_cycle(
    *,
    phase: int,
    act: str,
    round_i: int = 0,
) -> list[str]:
    """Which prediction fields are withheld from the scaffold this cycle."""
    phase = normalize_phase(phase)
    if phase == PHASE_FULL:
        return []
    pool = list(_TRIAD_KEYS)
    task_key = _TASK_KEY_BY_ACT.get(act)
    if task_key:
        pool.append(task_key)
    if phase == PHASE_NONE:
        return list(pool)
    # Phase 2: withhold 1 field (rotate); task acts alternate blanking their scalar
    if task_key and (round_i % 2 == 1):
        return [task_key]
    return [pool[round_i % len(_TRIAD_KEYS)]]


def build_scaffold_spec(
    prior: dict[str, Any],
    *,
    phase: int,
    act: str,
    round_i: int = 0,
) -> dict[str, Any]:
    """Build prompt scaffold + fill policy for this cycle."""
    phase = normalize_phase(phase)
    blanked = blank_keys_for_cycle(phase=phase, act=act, round_i=round_i)
    shown: dict[str, Any] = {"confidence": "medium"}
    for key in _TRIAD_KEYS:
        if key in blanked:
            shown[key] = None
        else:
            shown[key] = prior.get(key)
    task_key = _TASK_KEY_BY_ACT.get(act)
    if task_key:
        if task_key in blanked:
            shown[task_key] = None
        elif prior.get(task_key) is not None:
            shown[task_key] = prior.get(task_key)

    # prior_fill may restore only fields we actually showed
    fillable = [k for k in _ALL_PRED_KEYS if k not in blanked and shown.get(k) is not None]
    if phase == PHASE_NONE:
        fillable = []

    prefix = _prefix_through_first_blank(shown, blanked)
    return {
        "phase": phase,
        "blanked": blanked,
        "shown": shown,
        "fillable": fillable,
        "scaffold_json": json.dumps(shown, separators=(",", ":")),
        "completion_prefix": prefix,
        "note": {
            PHASE_FULL: "full scaffold; prior_fill ok",
            PHASE_PARTIAL: "partial scaffold; emit null fields yourself",
            PHASE_NONE: "no value scaffold; self-emit full JSON",
        }.get(phase, ""),
    }


def _prefix_through_first_blank(shown: dict[str, Any], blanked: list[str]) -> str:
    """Open JSON through the first blank key so decode must supply the value."""
    if not blanked:
        return json.dumps(shown, separators=(",", ":"))
    # Emit keys in stable order until first blank
    order = [k for k in ("predicted_master_rsr", "predicted_master_ltp", "predicted_master_rle", "predicted_live_cells", "predicted_mean_load_pct", "confidence") if k in shown]
    parts: list[str] = []
    for key in order:
        if key in blanked:
            parts.append(f'"{key}":')
            return "{" + ",".join(parts)
        val = shown[key]
        parts.append(f'"{key}":{json.dumps(val, separators=(",", ":"))}')
    return "{" + ",".join(parts) + "}"


def apply_prior_fill_policy(
    parsed: dict[str, Any],
    prior: dict[str, Any],
    *,
    fillable: list[str],
) -> dict[str, Any]:
    """Fill missing channels only if policy allows (Phase 2+ refuses blanked keys)."""
    out = dict(parsed)
    filled: list[str] = []
    for key in fillable:
        if out.get(key) is None and prior.get(key) is not None:
            if key == "predicted_live_cells":
                out[key] = int(prior[key])
            else:
                out[key] = float(prior[key])
            filled.append(key)
    if (
        out.get("predicted_master_rsr") is not None
        and out.get("predicted_master_ltp") is not None
        and out.get("predicted_master_rle") is not None
    ):
        from lib.master_rid import sn_from_channels

        out["predicted_master_s_n"] = round(
            float(
                sn_from_channels(
                    float(out["predicted_master_rsr"]),
                    float(out["predicted_master_ltp"]),
                    float(out["predicted_master_rle"]),
                )
            ),
            4,
        )
        out["triad_complete"] = True
    if filled:
        out["prior_filled"] = filled
        out["parse"] = f"{out.get('parse', 'unknown')}+prior_fill"
    return out


def self_emit_report(parsed: dict[str, Any], blanked: list[str]) -> dict[str, Any]:
    """Did she supply the withheld fields without prior_fill?"""
    prior_filled = set(parsed.get("prior_filled") or [])
    emitted = []
    missing = []
    for key in blanked:
        if parsed.get(key) is not None and key not in prior_filled:
            emitted.append(key)
        else:
            missing.append(key)
    return {
        "blanked": blanked,
        "self_emitted": emitted,
        "missing_or_filled": missing,
        "self_emit_ok": len(blanked) > 0 and len(missing) == 0,
        "all_blanked_self_emitted": bool(blanked) and not missing,
    }
