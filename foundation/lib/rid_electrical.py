"""CPU↔GPU electrical coupling math — observe-only helpers.

Pure functions for r_W/r_V/r_I, C_electrical, S_electrical, and active-set
geometric means. Does not invent meters and does not mutate Master RID.
See RID_EQUATIONS.md Part B.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

FLAG_NAME = "rid_electrical_observe_v1"
DEFAULT_ROUTING_EPS = 1e-6
DEFAULT_OHM_TOL = 1e-6


def _clamp01(x: float) -> float:
    if math.isnan(x) or math.isinf(x):
        return 0.0
    return max(0.0, min(1.0, float(x)))


def ratio(
    a: float | None,
    b: float | None,
    *,
    required: bool = True,
    both_intentionally_inactive: bool = False,
) -> float:
    """Piecewise r_X = min/max with fail-closed cases.

    - max>0: min/max
    - both intentionally inactive and not required: 1.0 (local placeholder only)
    - required but missing/failed: 0.0
    - both zero/None when required: 0.0
    """
    if both_intentionally_inactive and not required:
        return 1.0
    if a is None or b is None:
        return 0.0 if required else 1.0
    try:
        fa = float(a)
        fb = float(b)
    except (TypeError, ValueError):
        return 0.0 if required else 1.0
    if math.isnan(fa) or math.isnan(fb) or math.isinf(fa) or math.isinf(fb):
        return 0.0 if required else 1.0
    if fa < 0 or fb < 0:
        return 0.0 if required else 1.0
    mx = max(fa, fb)
    if mx > 0.0:
        return _clamp01(min(fa, fb) / mx)
    # both zero
    if required:
        return 0.0
    return 1.0


def coupling_product(r_w: float, r_v: float, r_i: float) -> float:
    """C_electrical = r_W * r_V * r_I."""
    return _clamp01(float(r_w)) * _clamp01(float(r_v)) * _clamp01(float(r_i))


def s_electrical(r_w: float, r_v: float, r_i: float) -> float:
    """S_electrical = (r_W * r_V * r_I)^(1/3)."""
    c = coupling_product(r_w, r_v, r_i)
    if c <= 0.0:
        return 0.0
    return _clamp01(c ** (1.0 / 3.0))


def ohm_consistent(
    w: float,
    v: float,
    i: float,
    *,
    tol: float = DEFAULT_OHM_TOL,
) -> bool:
    """True when W ≈ V*I within relative/absolute tolerance (one side)."""
    try:
        fw, fv, fi = float(w), float(v), float(i)
    except (TypeError, ValueError):
        return False
    if any(math.isnan(x) or math.isinf(x) for x in (fw, fv, fi)):
        return False
    expected = fv * fi
    scale = max(abs(fw), abs(expected), 1.0)
    return abs(fw - expected) <= max(float(tol), float(tol) * scale)


def active_set_master(
    s_map: Mapping[str, float],
    active_names: Sequence[str],
) -> float:
    """Geometric mean over named active subsystems only (exclude sleepers)."""
    vals: list[float] = []
    for name in active_names:
        if name not in s_map:
            continue
        vals.append(_clamp01(float(s_map[name])))
    if not vals:
        return 0.0
    prod = 1.0
    for v in vals:
        prod *= max(v, 1e-6)
    return _clamp01(prod ** (1.0 / len(vals)))


def weighted_geom_mean(
    values: Sequence[float],
    weights: Sequence[float],
) -> float:
    """(prod S_k^{w_k})^(1/sum w)."""
    if len(values) != len(weights) or not values:
        return 0.0
    wsum = 0.0
    log_acc = 0.0
    for s, w in zip(values, weights):
        ww = float(w)
        if ww <= 0.0:
            continue
        ss = max(_clamp01(float(s)), 1e-6)
        wsum += ww
        log_acc += ww * math.log(ss)
    if wsum <= 0.0:
        return 0.0
    return _clamp01(math.exp(log_acc / wsum))


def routing_score(
    useful_work: float,
    delta_s_n: float,
    *,
    eps: float = DEFAULT_ROUTING_EPS,
) -> float:
    """work / max(eps, delta_s_n); +inf when delta_s_n <= 0 (neutral/improving)."""
    work = float(useful_work)
    dsn = float(delta_s_n)
    if math.isnan(work) or math.isinf(work) or work < 0:
        return float("-inf")
    if math.isnan(dsn) or math.isinf(dsn):
        return float("-inf")
    if dsn <= 0.0:
        return float("inf")
    return work / max(float(eps), dsn)


def choose_route(
    candidates: Mapping[str, tuple[float, float]],
    *,
    eps: float = DEFAULT_ROUTING_EPS,
) -> dict[str, Any]:
    """Argmax routing over {name: (useful_work, predicted_delta_s_n)}.

    Raises ValueError if eps <= 0 (denominator floor required).
    """
    if float(eps) <= 0.0:
        raise ValueError("routing_eps_must_be_positive")
    if not candidates:
        return {"ok": False, "error": "no_candidates", "choice": None, "scores": {}}
    scores: dict[str, float] = {}
    for name, pair in candidates.items():
        work, dsn = pair
        scores[name] = routing_score(work, dsn, eps=eps)
    # Prefer finite best; among +inf (non-positive delta), max work
    inf_names = [n for n, s in scores.items() if math.isinf(s) and s > 0]
    if inf_names:
        choice = max(inf_names, key=lambda n: float(candidates[n][0]))
    else:
        choice = max(scores.keys(), key=lambda n: scores[n])
    return {"ok": True, "choice": choice, "scores": scores, "eps": float(eps)}


def routing_quality(
    useful_work: float,
    *,
    predicted_joules: float,
    predicted_stability_loss: float,
    latency: float,
    eps: float = DEFAULT_ROUTING_EPS,
) -> float:
    """Q_i = useful_work / (joules + stability_loss + latency) with eps floor on denom."""
    work = float(useful_work)
    if math.isnan(work) or math.isinf(work) or work < 0:
        return float("-inf")
    denom = float(predicted_joules) + float(predicted_stability_loss) + float(latency)
    if math.isnan(denom) or math.isinf(denom):
        return float("-inf")
    return work / max(float(eps), denom)


def choose_route_quality(
    candidates: Mapping[str, Mapping[str, float]],
    *,
    eps: float = DEFAULT_ROUTING_EPS,
) -> dict[str, Any]:
    """Argmax Q_i over {name: {useful_work, joules, stability_loss, latency}}."""
    if float(eps) <= 0.0:
        raise ValueError("routing_eps_must_be_positive")
    if not candidates:
        return {"ok": False, "error": "no_candidates", "choice": None, "scores": {}}
    scores: dict[str, float] = {}
    for name, row in candidates.items():
        scores[name] = routing_quality(
            float(row.get("useful_work", 0.0)),
            predicted_joules=float(row.get("joules", 0.0)),
            predicted_stability_loss=float(row.get("stability_loss", 0.0)),
            latency=float(row.get("latency", 0.0)),
            eps=eps,
        )
    choice = max(scores.keys(), key=lambda n: scores[n])
    return {"ok": True, "choice": choice, "scores": scores, "eps": float(eps), "advisory": True}


def triad_availability(
    *,
    w_cpu: float | None,
    w_gpu: float | None,
    v_cpu: float | None,
    v_gpu: float | None,
    i_cpu: float | None,
    i_gpu: float | None,
) -> dict[str, Any]:
    """Report which ratio pairs can be formed; no fabricated fills."""
    present = {
        "w_cpu": w_cpu is not None,
        "w_gpu": w_gpu is not None,
        "v_cpu": v_cpu is not None,
        "v_gpu": v_gpu is not None,
        "i_cpu": i_cpu is not None,
        "i_gpu": i_gpu is not None,
    }
    missing = [k for k, ok in present.items() if not ok]
    can_r_w = present["w_cpu"] and present["w_gpu"]
    can_r_v = present["v_cpu"] and present["v_gpu"]
    can_r_i = present["i_cpu"] and present["i_gpu"]
    complete = can_r_w and can_r_v and can_r_i
    out: dict[str, Any] = {
        "present": present,
        "missing_channels": missing,
        "can_compute": {"r_w": can_r_w, "r_v": can_r_v, "r_i": can_r_i},
        "available": complete,
        "s_electrical": None,
        "r_w": None,
        "r_v": None,
        "r_i": None,
        "c_electrical": None,
        "reason": None if complete else "incomplete_channels",
    }
    if can_r_w:
        out["r_w"] = ratio(w_cpu, w_gpu, required=True)
    if can_r_v:
        out["r_v"] = ratio(v_cpu, v_gpu, required=True)
    if can_r_i:
        out["r_i"] = ratio(i_cpu, i_gpu, required=True)
    if complete:
        rw, rv, ri = float(out["r_w"]), float(out["r_v"]), float(out["r_i"])
        out["c_electrical"] = coupling_product(rw, rv, ri)
        out["s_electrical"] = s_electrical(rw, rv, ri)
        out["reason"] = None
    return out


def reject_derived_live_axes(
    *,
    w: float | None,
    v: float | None,
    i: float | None,
    i_was_derived_from_w_over_v: bool,
) -> dict[str, Any]:
    """Honesty guard: derived I=W/V must not count as an independent live axis."""
    if i_was_derived_from_w_over_v:
        return {
            "ok": False,
            "admissible_as_independent_axis": False,
            "reason": "derived_I_from_W_over_V_forbidden_as_live_axis",
            "w": w,
            "v": v,
            "i": i,
        }
    return {
        "ok": True,
        "admissible_as_independent_axis": i is not None and w is not None and v is not None,
        "reason": None,
        "w": w,
        "v": v,
        "i": i,
    }


def rle_identity(a: float, b: float) -> dict[str, float]:
    """Canonical dual-sensor channels + algebraic identity check residual."""
    ltp = (a + b) / 2.0
    rsr = a * b
    rle = rsr - ltp**2
    alt = -((a - b) ** 2) / 4.0
    return {
        "ltp": ltp,
        "rsr": rsr,
        "rle": rle,
        "rle_alt": alt,
        "residual": rle - alt,
    }
