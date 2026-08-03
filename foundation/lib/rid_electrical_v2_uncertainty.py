#!/usr/bin/env python3
"""Per-domain V2 empirical error-scale calibration.

Strata:
  cold_load, warm_resident, prompt_short, prompt_long,
  eval_short (t_eval<3.2), eval_long (t_eval>=3.8),
  tail_5s, tail_10s, tail_20s, combined
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_predictor_v2 import clear_candidate_cache, load_candidate, predict_E_action

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
SCALES_PATH = OUT / "V2_UNCERTAINTY_SCALES.json"

STRATA = (
    "cold_load",
    "warm_resident",
    "prompt_short",
    "prompt_long",
    "eval_short",
    "eval_long",
    "tail_5s",
    "tail_10s",
    "tail_20s",
    "combined",
)


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def classify_strata(row: dict[str, Any]) -> list[str]:
    """Return all stratum labels that apply to one graded action."""
    labels: list[str] = ["combined"]
    cold = bool(row.get("cold") or row.get("unload_before"))
    if cold:
        labels.append("cold_load")
    else:
        labels.append("warm_resident")
    variant = str(row.get("prompt_variant") or "")
    if variant == "short":
        labels.append("prompt_short")
    elif variant == "long":
        labels.append("prompt_long")
    te = row.get("t_eval_s")
    if te is None:
        te = (row.get("measured") or {}).get("eval_duration_s")
    if te is not None:
        te = float(te)
        if te < 3.2:
            labels.append("eval_short")
        if te >= 3.8:
            labels.append("eval_long")
    th = row.get("tail_horizon_s") or row.get("tail_tau_s")
    if th is not None:
        th = float(th)
        if abs(th - 5.0) < 0.1:
            labels.append("tail_5s")
        elif abs(th - 10.0) < 0.1:
            labels.append("tail_10s")
        elif abs(th - 20.0) < 0.1:
            labels.append("tail_20s")
    return labels


def _rmse(errs: Sequence[float]) -> float | None:
    if not errs:
        return None
    return math.sqrt(statistics.fmean([e * e for e in errs]))


def prediction_domain_for_row(row: dict[str, Any]) -> str:
    labels = classify_strata(row)
    if "cold_load" in labels:
        return "cold_load"
    if "tail_20s" in labels:
        return "tail_20s"
    if "tail_10s" in labels:
        return "tail_10s"
    if "tail_5s" in labels and ("prompt_short" in labels or "prompt_long" in labels):
        return "warm_prompt_eval"
    if "warm_resident" in labels:
        return "warm_prompt_eval"
    return "combined"


def calibrate_from_graded_rows(
    rows: Sequence[dict[str, Any]],
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Compute RMSE residual scales per stratum from graded actions."""
    buckets: dict[str, list[float]] = {s: [] for s in STRATA}
    usable = 0
    for r in rows:
        # Support prospective graded shape and live-shadow shape
        resid = r.get("residual_j")
        if resid is None:
            resid = r.get("v2_residual")
        if resid is None:
            e_meas = r.get("E_meas_j") or r.get("measured_energy")
            e_hat = r.get("E_hat_j") or r.get("v2_prediction")
            if e_meas is not None and e_hat is not None:
                resid = float(e_meas) - float(e_hat)
        if resid is None:
            continue
        usable += 1
        # enrich timing for classification
        rr = dict(r)
        if "t_eval_s" not in rr:
            rr["t_eval_s"] = (r.get("measured") or {}).get("eval_duration_s")
        if "tail_horizon_s" not in rr:
            plan = r.get("predeclared_plan") or {}
            rr["tail_horizon_s"] = plan.get("tail_tau_s") or r.get("tail_tau_s")
            rr["prompt_variant"] = plan.get("prompt_variant") or r.get("prompt_variant")
            rr["cold"] = r.get("cold")
            if rr.get("cold") is None:
                rr["cold"] = plan.get("residency") == "cold_first" or plan.get(
                    "unload_before"
                )
        for lab in classify_strata(rr):
            buckets[lab].append(float(resid))

    scales: dict[str, Any] = {}
    for s in STRATA:
        errs = buckets[s]
        scales[s] = {
            "n": len(errs),
            "rmse_j": _rmse(errs),
            "mae_j": statistics.fmean([abs(e) for e in errs]) if errs else None,
        }

    # Fallback chain: domain → combined → candidate heldout
    cand = load_candidate()
    fallback = cand.get("heldout_rmse_j") or 30.0
    combined = scales["combined"].get("rmse_j") or fallback

    payload = {
        "ok": True,
        "at": _utc(),
        "n_rows_usable": usable,
        "scales": scales,
        "fallback_rmse_j": float(combined),
        "note": (
            "Domain-specific empirical residual RMSE. Not a coverage prediction interval."
        ),
    }
    path = Path(out_path) if out_path else SCALES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact"] = str(path).replace("\\", "/")
    return payload


def load_scales(*, path: Path | None = None, force: bool = False) -> dict[str, Any]:
    p = Path(path) if path else SCALES_PATH
    if not p.exists():
        return {"ok": False, "scales": {}, "fallback_rmse_j": None}
    return json.loads(p.read_text(encoding="utf-8"))


def scale_for_domain(domain: str, *, scales: dict[str, Any] | None = None) -> float | None:
    data = scales if scales is not None else load_scales()
    block = (data.get("scales") or {}).get(domain) or {}
    if block.get("rmse_j") is not None:
        return float(block["rmse_j"])
    # map prediction_domain names
    aliases = {
        "warm_prompt_eval": "warm_resident",
        "tail_accounting": "combined",
        "prompt_decomp": "combined",
    }
    alt = aliases.get(domain)
    if alt:
        b2 = (data.get("scales") or {}).get(alt) or {}
        if b2.get("rmse_j") is not None:
            return float(b2["rmse_j"])
    fb = data.get("fallback_rmse_j")
    return float(fb) if fb is not None else None


def calibrate_from_artifacts() -> dict[str, Any]:
    """Load prospective (+ optional live shadow) graded rows and write scales."""
    rows: list[dict[str, Any]] = []
    prosp = OUT / "v2_prospective_validation_latest.json"
    if prosp.exists():
        payload = json.loads(prosp.read_text(encoding="utf-8"))
        rows.extend(list(payload.get("actions") or []))
    live = OUT / "v2_live_shadow_campaign_latest.json"
    if live.exists():
        payload = json.loads(live.read_text(encoding="utf-8"))
        rows.extend(list(payload.get("actions") or []))
    return calibrate_from_graded_rows(rows)
