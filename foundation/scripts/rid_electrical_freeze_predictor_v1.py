#!/usr/bin/env python3
"""Freeze validated eval_duration_v1 as immutable baseline.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_freeze_predictor_v1.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_drift_check import LOCKED_REVALIDATION_FINGERPRINT  # noqa: E402
from lib.rid_electrical_policy import policy_stamp  # noqa: E402
from lib.rid_electrical_predictor import (  # noqa: E402
    ALPHA,
    BETA,
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    HELD_OUT_RMSE_J,
    MAX_ABS_RESIDUAL_J,
    PLANT_CONFIG_ID,
    PREDICTOR_VERSION,
    PROVENANCE,
)

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
PREDICTOR_PY = FOUNDATION / "lib" / "rid_electrical_predictor.py"
LOCKED = OUT / "PREDICTOR_LOCKED_EVAL_DURATION_V1.json"
REVIEW = OUT / "PREDICTOR_REVIEW_V1.json"
LIVE = OUT / "live_accounting_validation_latest.json"
FREEZE = OUT / "PREDICTOR_V1_BASELINE_FROZEN.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main() -> int:
    missing = [p for p in (LOCKED, REVIEW, LIVE, PREDICTOR_PY) if not p.exists()]
    if missing:
        print(json.dumps({"error": "missing_required_artifacts", "missing": [str(m) for m in missing]}))
        return 1

    live = json.loads(LIVE.read_text(encoding="utf-8"))
    live_ev = live.get("evaluation") or {}
    locked = json.loads(LOCKED.read_text(encoding="utf-8"))

    # Verify coefficients still match locked artifact
    c = locked.get("coefficients") or {}
    if abs(float(c.get("alpha_j")) - ALPHA) > 1e-9 or abs(float(c.get("beta_j_per_s")) - BETA) > 1e-9:
        print(json.dumps({"error": "coefficient_mismatch_vs_locked"}))
        return 1

    freeze = {
        "ok": True,
        "at": _utc(),
        "predictor_version": PREDICTOR_VERSION,
        "baseline_id": "eval_duration_v1_frozen_baseline",
        "refit_forbidden": True,
        "next_model_id": "eval_duration_v2_requires_separate_review",
        "coefficients": {
            "alpha_j": ALPHA,
            "beta_j_per_s": BETA,
            "formula": "E_net_hat = alpha + beta * eval_duration_s",
        },
        "domain": {
            "min_eval_duration_s": DOMAIN_MIN_S,
            "max_eval_duration_s": DOMAIN_MAX_S,
        },
        "plant_config_id": PLANT_CONFIG_ID,
        "revalidation_fingerprint": LOCKED_REVALIDATION_FINGERPRINT,
        "uncertainty": {
            "heldout_rmse_j": HELD_OUT_RMSE_J,
            "max_abs_residual_j": MAX_ABS_RESIDUAL_J,
            "live_rmse_j": live_ev.get("rmse_live_j"),
            "live_n_usable": live_ev.get("n_usable"),
            "live_status": live_ev.get("status"),
        },
        "provenance": PROVENANCE,
        "artifacts": {
            "locked": str(LOCKED).replace("\\", "/"),
            "review": str(REVIEW).replace("\\", "/"),
            "live_validation": str(LIVE).replace("\\", "/"),
            "predictor_source": str(PREDICTOR_PY).replace("\\", "/"),
        },
        "checksums_sha256": {
            "rid_electrical_predictor.py": _sha256(PREDICTOR_PY),
            "PREDICTOR_LOCKED_EVAL_DURATION_V1.json": _sha256(LOCKED),
            "PREDICTOR_REVIEW_V1.json": _sha256(REVIEW),
            "live_accounting_validation_latest.json": _sha256(LIVE),
        },
        "future_config_registry_schema": [
            "hardware",
            "gpu_driver",
            "model",
            "quantization",
            "executor",
            "residency_state",
            "telemetry_cadence",
            "thermal_protocol",
        ],
        "authority": {
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
            "accounting_estimates_authorized": True,
        },
        "policy": policy_stamp(),
    }
    FREEZE.write_text(json.dumps(freeze, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "baseline_id": freeze["baseline_id"],
                "refit_forbidden": True,
                "artifact": str(FREEZE).replace("\\", "/"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
