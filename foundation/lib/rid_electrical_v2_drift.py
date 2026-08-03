#!/usr/bin/env python3
"""V2 live drift / revocation (separate from V1).

RMSE_V2,live > 1.5 * RMSE_V2,validated → V2 stale.
When stale: expanded-domain estimates null; V1 domain intact; no auto-refit.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from lib.paths import AUTO_ARTIFACTS
from lib.rid_electrical_policy import apply_v2_live_verdict
from lib.rid_electrical_v2_shadow import SHADOW_LOG

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
BASELINE_PATH = OUT / "V2_VALIDATED_RMSE.json"
DRIFT_RMSE_MULT = 1.5
MIN_LIVE_N = 20


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_validated_baseline(
    *,
    rmse_j: float,
    n: int,
    per_component: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "ok": True,
        "at": _utc(),
        "validated_rmse_j": float(rmse_j),
        "n": int(n),
        "drift_mult": DRIFT_RMSE_MULT,
        "stale_threshold_j": float(rmse_j) * DRIFT_RMSE_MULT,
        "per_component": per_component or {},
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact"] = str(BASELINE_PATH).replace("\\", "/")
    return payload


def load_validated_baseline() -> dict[str, Any]:
    if not BASELINE_PATH.exists():
        # fallback to candidate heldout
        cand = OUT / "PREDICTOR_CANDIDATE_V2.json"
        if cand.exists():
            data = json.loads(cand.read_text(encoding="utf-8"))
            rmse = data.get("heldout_rmse_j") or (data.get("coefficients") or {}).get(
                "heldout_rmse_j"
            )
            if rmse is not None:
                return {
                    "ok": True,
                    "validated_rmse_j": float(rmse),
                    "stale_threshold_j": float(rmse) * DRIFT_RMSE_MULT,
                    "source": "candidate_heldout",
                }
        return {"ok": False, "validated_rmse_j": None}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def load_v2_shadow_residuals(*, path: Path | None = None) -> list[float]:
    p = Path(path) if path else SHADOW_LOG
    if not p.exists():
        return []
    errs: list[float] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        resid = row.get("residual_j")
        if resid is None:
            continue
        if row.get("confidence") not in {None, "ok"}:
            continue
        errs.append(float(resid))
    return errs


def evaluate_v2_drift(
    residuals: Sequence[float] | None = None,
    *,
    apply_policy: bool = True,
) -> dict[str, Any]:
    base = load_validated_baseline()
    validated = base.get("validated_rmse_j")
    thr = base.get("stale_threshold_j")
    if thr is None and validated is not None:
        thr = float(validated) * DRIFT_RMSE_MULT
    errs = list(residuals) if residuals is not None else load_v2_shadow_residuals()
    n = len(errs)
    rmse = None
    if n >= 2:
        rmse = math.sqrt(statistics.fmean([e * e for e in errs]))
    if n < MIN_LIVE_N:
        status = "insufficient_v2_live_sample"
    elif validated is None or thr is None or rmse is None:
        status = "insufficient_v2_baseline"
    elif rmse > float(thr):
        status = "v2_stale_revalidation_required"
    else:
        status = "v2_live_shadow_validated"

    if apply_policy and status in {
        "v2_stale_revalidation_required",
        "v2_live_shadow_validated",
    }:
        apply_v2_live_verdict(status)

    return {
        "ok": True,
        "at": _utc(),
        "status": status,
        "n": n,
        "min_n": MIN_LIVE_N,
        "rmse_live_j": rmse,
        "validated_rmse_j": validated,
        "stale_threshold_j": thr,
        "drift_mult": DRIFT_RMSE_MULT,
        "operational_authority": False,
        "auto_refit": False,
        "note": (
            "When V2 stale: expanded-domain estimates null; V1 domain remains usable."
        ),
    }
