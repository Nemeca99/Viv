"""CPU script prediction sample — guide hint, not oracle.

Uses past PRT cycle after-values (per act) to form an average within the normal
band, then adds intentional noise so the sample is *accurate enough to compare*
but never perfect truth:

  - thermal (°C): ±1.0 degree uniform offset
  - triad (0-1):  ±0.01 band (same spirit — small guide jitter)

She must keep ~50/50 follow vs adapt:
  FOLLOW  — stay near the CPU sample when it was good
  ADAPT   — refine away when plant truth disagrees with the sample
  COPY_BLIND — glued to sample while sample was wrong → soft punish
  SOLO    — ignored a good sample and missed truth → soft punish

Target rolling follow_rate among (FOLLOW+ADAPT) ≈ 0.50.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from lib.paths import ARTIFACTS

PRT_CYCLES_PATH = ARTIFACTS / "models" / "prt_cycles.jsonl"

_TEMP_OFFSET_C = 1.0
_TRIAD_OFFSET = 0.005  # tighter guide — still not oracle; ±1°C on temps
_FOLLOW_TOL_TRIAD = 0.04  # |her - sample| within this → "followed" (aligned to tol widen)
_TARGET_FOLLOW_RATE = 0.50
_FOLLOW_BAND = 0.15  # soft-ok band around 50% (35–65%)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _mean(xs: list[float], default: float) -> float:
    return sum(xs) / len(xs) if xs else float(default)


def _hist_after_means(*, act: str, tail: int = 240, min_n: int = 6) -> dict[str, float]:
    """Mean measured after-state for this act from recent cycles."""
    defaults = {
        "master_rsr": 0.5,
        "master_ltp": 0.45,
        "master_rle": 0.4,
        "master_s_n": 0.45,
        "cpu_temp_c": 55.0,
        "gpu_temp_c": 48.0,
    }
    path = PRT_CYCLES_PATH
    if not path.is_file():
        return defaults
    buckets: dict[str, list[float]] = defaultdict(list)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail:]
    except OSError:
        return defaults
    for ln in lines:
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if row.get("excluded") or not row.get("ok"):
            continue
        act_obj = row.get("act")
        a = act_obj.get("act") if isinstance(act_obj, dict) else act_obj
        if str(a) != str(act):
            continue
        after = row.get("observe_after") or {}
        for k in defaults:
            if after.get(k) is not None:
                try:
                    buckets[k].append(float(after[k]))
                except (TypeError, ValueError):
                    pass
    out = dict(defaults)
    for k, xs in buckets.items():
        if len(xs) >= min_n:
            out[k] = round(sum(xs) / len(xs), 4)
        elif xs:
            out[k] = round(sum(xs) / len(xs), 4)
    out["_n"] = float(max((len(buckets[k]) for k in buckets), default=0))
    return out


def generate_cpu_sample(
    before: dict[str, Any],
    act: str,
    *,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Script prediction: historical average + intentional ±1°C / triad jitter."""
    rng = rng or random.Random()
    hist = _hist_after_means(act=act)
    # Blend history with live before so sample stays in "normal range" for *this* plant
    blend = 0.65  # weight on history after-mean

    def blend_ch(key: str, live_key: str | None = None) -> float:
        live_key = live_key or key
        live = float(before.get(live_key) if before.get(live_key) is not None else hist[key])
        return blend * float(hist[key]) + (1.0 - blend) * live

    rsr = _clamp01(blend_ch("master_rsr") + rng.uniform(-_TRIAD_OFFSET, _TRIAD_OFFSET))
    ltp = _clamp01(blend_ch("master_ltp") + rng.uniform(-_TRIAD_OFFSET, _TRIAD_OFFSET))
    rle = _clamp01(blend_ch("master_rle") + rng.uniform(-_TRIAD_OFFSET, _TRIAD_OFFSET))
    from lib.master_rid import sn_from_channels

    sn = float(sn_from_channels(rsr, ltp, rle))
    cpu_t = blend_ch("cpu_temp_c", "cpu_temp_c") + rng.uniform(-_TEMP_OFFSET_C, _TEMP_OFFSET_C)
    gpu_t = blend_ch("gpu_temp_c", "gpu_temp_c") + rng.uniform(-_TEMP_OFFSET_C, _TEMP_OFFSET_C)

    sample = {
        "source": "cpu_script",
        "act": act,
        "hist_n": int(hist.get("_n") or 0),
        "noise": {"temp_c": _TEMP_OFFSET_C, "triad": _TRIAD_OFFSET},
        "predicted_master_rsr": round(rsr, 4),
        "predicted_master_ltp": round(ltp, 4),
        "predicted_master_rle": round(rle, 4),
        "predicted_master_s_n": round(sn, 4),
        "predicted_cpu_temp_c": round(cpu_t, 2),
        "predicted_gpu_temp_c": round(gpu_t, 2),
        "note": "Guide only (±1°C / ±0.01 triad). Compare — do not always treat as truth.",
    }
    return sample


def format_cpu_sample_block(sample: dict[str, Any] | None) -> str:
    if not sample:
        return ""
    return (
        f"[TAG:cpu_sample] script guide (past avg + noise) act={sample.get('act')} "
        f"n={sample.get('hist_n')} "
        f"rsr={sample.get('predicted_master_rsr')} ltp={sample.get('predicted_master_ltp')} "
        f"rle={sample.get('predicted_master_rle')} s_n={sample.get('predicted_master_s_n')} "
        f"cpu_c={sample.get('predicted_cpu_temp_c')} gpu_c={sample.get('predicted_gpu_temp_c')}\n"
        "[TAG:cpu_sample_rule] Compare your prediction to cpu_sample. "
        "Target ~50/50: sometimes trust the guide, sometimes refine when plant disagrees. "
        "Never always-copy. Never always-solo.\n"
    )


def _channel_val(blob: dict[str, Any], key: str) -> float | None:
    """Read master_* or predicted_master_* interchangeably. key like master_rsr."""
    short = key.replace("master_", "")
    candidates = (
        f"predicted_master_{short}",
        f"master_{short}",
        key,
        f"predicted_{key}",
    )
    for k in candidates:
        if blob.get(k) is None:
            continue
        try:
            v = float(blob[k])
        except (TypeError, ValueError):
            continue
        if v != v:
            continue
        return v
    return None


def _triad_dist(a: dict[str, Any], b: dict[str, Any]) -> tuple[float | None, list[str]]:
    """Mean |Δ| over channels present on BOTH sides (Phase-2 blanks OK).

    Falls back to S_n-only if no triad channel pair exists.
    """
    keys = ("master_rsr", "master_ltp", "master_rle")
    vals: list[float] = []
    used: list[str] = []
    for k in keys:
        av = _channel_val(a, k)
        bv = _channel_val(b, k)
        if av is None or bv is None:
            continue
        vals.append(abs(av - bv))
        used.append(k)
    if vals:
        return sum(vals) / len(vals), used
    # S_n fallback — Phase 2 often emits composite when a blank is open
    asn = _channel_val(a, "master_s_n")
    bsn = _channel_val(b, "master_s_n")
    if asn is None or bsn is None:
        return None, []
    return abs(asn - bsn), ["master_s_n"]


def score_trust_balance(
    prediction: dict[str, Any],
    cpu_sample: dict[str, Any],
    after: dict[str, Any],
    *,
    follow_tol: float = _FOLLOW_TOL_TRIAD,
) -> dict[str, Any]:
    """Classify follow / adapt / copy_blind / solo vs CPU sample + plant truth."""
    d_her_sample, used_hs = _triad_dist(prediction, cpu_sample)
    d_sample_truth, used_st = _triad_dist(cpu_sample, after)
    d_her_truth, used_ht = _triad_dist(prediction, after)
    if d_her_sample is None or d_sample_truth is None or d_her_truth is None:
        return {
            "ok": False,
            "mode": "incomplete",
            "label": "NEUTRAL",
            "reason": "no_overlapping_channels",
            "used_her_sample": used_hs,
            "used_sample_truth": used_st,
            "used_her_truth": used_ht,
        }

    sample_good = d_sample_truth <= follow_tol * 1.5  # sample landed near truth
    followed = d_her_sample <= follow_tol
    better_than_sample = d_her_truth + 1e-9 < d_sample_truth

    if followed and sample_good:
        mode = "FOLLOW"
        label = "REWARD"  # trusted good help
    elif (not followed) and better_than_sample and not sample_good:
        mode = "ADAPT"
        label = "REWARD"  # correctly refined away from bad/noisy sample
    elif followed and not sample_good and d_her_truth >= d_sample_truth:
        mode = "COPY_BLIND"
        label = "PUNISH"  # glued to wrong guide
    elif (not followed) and sample_good and d_her_truth > d_sample_truth + follow_tol:
        mode = "SOLO"
        label = "PUNISH"  # ignored good help and missed
    elif better_than_sample:
        mode = "ADAPT"
        label = "NEUTRAL"
    elif followed:
        mode = "FOLLOW"
        label = "NEUTRAL"
    else:
        mode = "MIXED"
        label = "NEUTRAL"

    return {
        "ok": True,
        "mode": mode,
        "label": label,
        "d_her_sample": round(d_her_sample, 6),
        "d_sample_truth": round(d_sample_truth, 6),
        "d_her_truth": round(d_her_truth, 6),
        "channels_used": {
            "her_sample": used_hs,
            "sample_truth": used_st,
            "her_truth": used_ht,
        },
        "sample_good": sample_good,
        "followed": followed,
        "target_follow_rate": _TARGET_FOLLOW_RATE,
        "follow_band": _FOLLOW_BAND,
        "note": "50/50 follow↔adapt; soft-punish only if trust_soft_punish=true",
    }


def rolling_follow_rate(*, tail: int = 60) -> dict[str, Any]:
    """Among FOLLOW+ADAPT modes, fraction FOLLOW — target ~0.50."""
    path = PRT_CYCLES_PATH
    if not path.is_file():
        return {"ok": False, "follow_rate": None, "n": 0}
    modes: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail * 3 :]
    except OSError:
        return {"ok": False, "follow_rate": None, "n": 0}
    for ln in lines:
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        trust = (row.get("score") or {}).get("trust") or row.get("trust") or {}
        m = trust.get("mode")
        if m in ("FOLLOW", "ADAPT"):
            modes.append(m)
    modes = modes[-tail:]
    n = len(modes)
    if n < 8:
        return {"ok": False, "follow_rate": None, "n": n, "inconclusive": True}
    follow = sum(1 for m in modes if m == "FOLLOW")
    rate = follow / n
    in_band = abs(rate - _TARGET_FOLLOW_RATE) <= _FOLLOW_BAND
    return {
        "ok": True,
        "follow_rate": round(rate, 4),
        "n": n,
        "target": _TARGET_FOLLOW_RATE,
        "in_band": in_band,
        "verdict": "BALANCED" if in_band else ("OVER_TRUST" if rate > _TARGET_FOLLOW_RATE else "UNDER_TRUST"),
    }


def apply_trust_to_combined(
    combined: str,
    trust: dict[str, Any],
    *,
    soft_punish: bool = False,
) -> str:
    """Soft gate: blind copy / solo omniscience cannot keep full REWARD.

    When soft_punish=False (default / diagnostic), trust is logged only —
    physics REWARD is not downgraded. Re-enable after trust scoring is healthy
    and follow_rate has a valid sample.
    """
    if not soft_punish:
        return combined
    if not trust.get("ok"):
        return combined
    mode = trust.get("mode")
    if mode in ("COPY_BLIND", "SOLO") and combined == "REWARD":
        return "NEUTRAL"
    return combined
