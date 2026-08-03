#!/usr/bin/env python3
"""V2 physical action-energy predictor (candidate / shadow only).

Predeclared model:

  E_action_hat = E_load(r) + beta_prompt * t_prompt + beta_eval * t_eval + E_tail(h)

- r: cold vs warm residency (unload → cold)
- t_prompt: infer.prompt_eval_duration_s
- t_eval: infer.eval_duration_s
- h: tail_tau_s; E_tail from non-negative horizon lookup / piecewise-linear interp

Coefficients are loaded from PREDICTOR_CANDIDATE_V2.json when present; module
defaults are unset (null predictions) until a candidate is written by the fit
review. V1 remains frozen and is never modified here.

No operational authority. No Master/routing/auto-admit. Not accounting-approved.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_predictor import PLANT_CONFIG_ID as V1_PLANT_CONFIG_ID

PREDICTOR_VERSION = "action_energy_v2_candidate"
OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
CANDIDATE_PATH = OUT / "PREDICTOR_CANDIDATE_V2.json"

# Validated feature domains (expanded vs V1); guards are soft bounds from corpus.
T_EVAL_MIN_S = 2.0
T_EVAL_MAX_S = 5.5
T_PROMPT_MIN_S = 0.0
T_PROMPT_MAX_S = 2.0
TAIL_HORIZONS_S = (5.0, 10.0, 20.0)

PLANT_CONFIG_ID = V1_PLANT_CONFIG_ID  # same plant; different model identity

_AUTHORITY_FIELDS: dict[str, bool] = {
    "operational_authority": False,
    "master_routing_authorized": False,
    "auto_admit": False,
    "accounting_predictor_v2_approved": False,
}

COVERAGE_NOTE = (
    "Empirical error scale from V2 holdout RMSE. Not a validated frequentist "
    "prediction interval."
)

# Runtime-loaded candidate (None until freeze+fit writes artifact)
_CANDIDATE: dict[str, Any] | None = None


def _default_coeffs() -> dict[str, Any]:
    return {
        "E_load_cold_j": None,
        "beta_prompt_j_per_s": None,
        "beta_eval_j_per_s": None,
        "E_tail_by_horizon_j": {str(h): None for h in TAIL_HORIZONS_S},
        "heldout_rmse_j": None,
        "formula": (
            "E_action = E_load(cold) + beta_prompt*t_prompt + beta_eval*t_eval + E_tail(h)"
        ),
    }


def load_candidate(*, path: Path | None = None, force: bool = False) -> dict[str, Any]:
    """Load candidate coefficients from disk (cached)."""
    global _CANDIDATE
    if _CANDIDATE is not None and not force:
        return _CANDIDATE
    p = Path(path) if path else CANDIDATE_PATH
    if not p.exists():
        _CANDIDATE = {
            "ok": False,
            "loaded": False,
            "coefficients": _default_coeffs(),
            "reason": "candidate_missing",
        }
        return _CANDIDATE
    payload = json.loads(p.read_text(encoding="utf-8"))
    coeffs = dict(_default_coeffs())
    src = payload.get("coefficients") or {}
    coeffs.update({k: src.get(k, coeffs.get(k)) for k in coeffs})
    if "E_tail_by_horizon_j" in src and isinstance(src["E_tail_by_horizon_j"], dict):
        coeffs["E_tail_by_horizon_j"] = {
            str(k): src["E_tail_by_horizon_j"].get(k)
            for k in [str(h) for h in TAIL_HORIZONS_S]
        }
        # preserve any extra keys
        for k, v in src["E_tail_by_horizon_j"].items():
            coeffs["E_tail_by_horizon_j"][str(k)] = v
    _CANDIDATE = {
        "ok": bool(payload.get("ok", True)),
        "loaded": True,
        "coefficients": coeffs,
        "heldout_rmse_j": payload.get("heldout_rmse_j")
        or (src.get("heldout_rmse_j")),
        "decision": payload.get("decision"),
        "predictor_version": payload.get("predictor_version", PREDICTOR_VERSION),
        "path": str(p).replace("\\", "/"),
        "payload": payload,
    }
    return _CANDIDATE


def clear_candidate_cache() -> None:
    global _CANDIDATE
    _CANDIDATE = None


def residency_is_cold(
    residency: str | None,
    *,
    unload_before: bool = False,
    cell_id: str | None = None,
) -> bool:
    if unload_before:
        return True
    r = str(residency or "")
    if r == "cold_first":
        return True
    cid = str(cell_id or "")
    if "cold" in cid or "unload" in cid:
        return True
    return False


def interpolate_tail(h: float, tail_by_h: dict[str, float | None]) -> float | None:
    """Piecewise-linear monotonic interpolation over known horizons."""
    pts: list[tuple[float, float]] = []
    for hs in TAIL_HORIZONS_S:
        v = tail_by_h.get(str(hs))
        if v is None:
            v = tail_by_h.get(hs)  # type: ignore[arg-type]
        if v is not None:
            pts.append((float(hs), float(v)))
    if not pts:
        return None
    pts.sort(key=lambda x: x[0])
    if h <= pts[0][0]:
        return pts[0][1]
    if h >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        h0, y0 = pts[i]
        h1, y1 = pts[i + 1]
        if h0 <= h <= h1:
            if abs(h1 - h0) < 1e-12:
                return y0
            w = (h - h0) / (h1 - h0)
            return y0 + w * (y1 - y0)
    return pts[-1][1]


def _sanitize_nonneg(t: float) -> str | None:
    if math.isnan(t) or math.isinf(t) or t < 0:
        return "invalid_input"
    return None


def predict_E_action(
    *,
    t_eval_s: float,
    t_prompt_s: float,
    tail_horizon_s: float,
    residency: str = "warm_repeat",
    unload_before: bool = False,
    cell_id: str | None = None,
    plant_config_id: str | None = None,
    candidate_path: Path | None = None,
) -> dict[str, Any]:
    """Predict full action energy E_net + E_tail under V2 decomposition."""
    cand = load_candidate(path=candidate_path)
    coeffs = cand.get("coefficients") or _default_coeffs()
    rmse = cand.get("heldout_rmse_j") or coeffs.get("heldout_rmse_j")

    base: dict[str, Any] = {
        "predicted_E_action_j": None,
        "predicted_E_load_j": None,
        "predicted_E_prompt_j": None,
        "predicted_E_eval_j": None,
        "predicted_E_tail_j": None,
        "predicted_E_net_j": None,
        "t_eval_s": None,
        "t_prompt_s": None,
        "tail_horizon_s": float(tail_horizon_s) if tail_horizon_s is not None else None,
        "residency_cold": residency_is_cold(
            residency, unload_before=unload_before, cell_id=cell_id
        ),
        "validated_domain_t_eval": [T_EVAL_MIN_S, T_EVAL_MAX_S],
        "validated_domain_t_prompt": [T_PROMPT_MIN_S, T_PROMPT_MAX_S],
        "in_domain": False,
        "plant_configuration_id": PLANT_CONFIG_ID,
        "confidence": "candidate_missing",
        "predictor_version": PREDICTOR_VERSION,
        "empirical_error_scale_j": rmse,
        "heldout_rmse_j": rmse,
        "coverage_note": COVERAGE_NOTE,
        "formula": coeffs.get("formula"),
        **dict(_AUTHORITY_FIELDS),
    }

    try:
        te = float(t_eval_s)
        tp = float(t_prompt_s)
        th = float(tail_horizon_s)
    except (TypeError, ValueError):
        base["confidence"] = "invalid_input"
        return base

    base["t_eval_s"] = te
    base["t_prompt_s"] = tp
    base["tail_horizon_s"] = th

    err = _sanitize_nonneg(te) or _sanitize_nonneg(tp) or _sanitize_nonneg(th)
    if err:
        base["confidence"] = err
        return base

    cfg = plant_config_id or PLANT_CONFIG_ID
    if plant_config_id is not None and plant_config_id != PLANT_CONFIG_ID:
        base["confidence"] = "config_mismatch"
        base["plant_configuration_id"] = str(plant_config_id)
        return base
    base["plant_configuration_id"] = cfg

    if not cand.get("loaded"):
        return base

    e_load_c = coeffs.get("E_load_cold_j")
    bp = coeffs.get("beta_prompt_j_per_s")
    be = coeffs.get("beta_eval_j_per_s")
    tails = coeffs.get("E_tail_by_horizon_j") or {}
    if any(x is None for x in (e_load_c, bp, be)):
        base["confidence"] = "coefficients_incomplete"
        return base

    in_dom = (
        T_EVAL_MIN_S <= te <= T_EVAL_MAX_S and T_PROMPT_MIN_S <= tp <= T_PROMPT_MAX_S
    )
    base["in_domain"] = in_dom
    if not in_dom:
        base["confidence"] = "out_of_validated_domain"
        return base

    cold = base["residency_cold"]
    e_load = float(e_load_c) if cold else 0.0
    e_prompt = float(bp) * tp
    e_eval = float(be) * te
    e_tail = interpolate_tail(th, tails)
    if e_tail is None:
        base["confidence"] = "tail_horizon_unavailable"
        return base

    e_net = e_load + e_prompt + e_eval
    e_action = e_net + float(e_tail)

    # Domain-specific empirical error scale
    if cold:
        pred_domain = "cold_load"
    elif abs(th - 20.0) < 0.1:
        pred_domain = "tail_20s"
    elif abs(th - 10.0) < 0.1:
        pred_domain = "tail_10s"
    else:
        pred_domain = "warm_prompt_eval"

    # Stale V2: withhold expanded-domain estimates
    try:
        from lib.rid_electrical_policy import PREDICTOR_V2_STALE

        if PREDICTOR_V2_STALE:
            base.update(
                {
                    "prediction_domain": pred_domain,
                    "component_estimates": {
                        "E_load_j": e_load,
                        "E_prompt_j": e_prompt,
                        "E_eval_j": e_eval,
                        "E_tail_j": float(e_tail),
                    },
                    "confidence": "v2_stale",
                    "predicted_E_j": None,
                }
            )
            return base
    except Exception:  # noqa: BLE001
        pass

    domain_scale = rmse
    try:
        from lib.rid_electrical_v2_uncertainty import scale_for_domain

        ds = scale_for_domain(pred_domain)
        if ds is not None:
            domain_scale = ds
    except Exception:  # noqa: BLE001
        pass

    components = {
        "E_load_j": e_load,
        "E_prompt_j": e_prompt,
        "E_eval_j": e_eval,
        "E_tail_j": float(e_tail),
    }
    base.update(
        {
            "predicted_E_load_j": e_load,
            "predicted_E_prompt_j": e_prompt,
            "predicted_E_eval_j": e_eval,
            "predicted_E_tail_j": float(e_tail),
            "predicted_E_net_j": e_net,
            "predicted_E_action_j": e_action,
            "predicted_E_j": e_action,
            "component_estimates": components,
            "prediction_domain": pred_domain,
            "empirical_error_scale_j": domain_scale,
            "heldout_rmse_j": domain_scale,
            "config_id": cfg,
            "confidence": "ok",
        }
    )
    return base


def predict_E_net_overlap(
    *,
    t_eval_s: float,
    t_prompt_s: float = 0.0,
    residency: str = "warm_repeat",
    unload_before: bool = False,
    plant_config_id: str | None = None,
    candidate_path: Path | None = None,
) -> dict[str, Any]:
    """Warm-domain net-only prediction for fair V1 overlap comparison (no tail)."""
    # Use a dummy in-domain tail to reuse guards, then strip tail from output.
    full = predict_E_action(
        t_eval_s=t_eval_s,
        t_prompt_s=t_prompt_s,
        tail_horizon_s=5.0,
        residency=residency,
        unload_before=unload_before,
        plant_config_id=plant_config_id,
        candidate_path=candidate_path,
    )
    out = dict(full)
    if full.get("predicted_E_net_j") is not None:
        out["predicted_E_net_j"] = float(full["predicted_E_net_j"])
        # For warm overlap, load should be 0; keep as predicted.
    out["predicted_E_action_j"] = None
    out["predicted_E_tail_j"] = None
    out["overlap_compare_mode"] = True
    return out
