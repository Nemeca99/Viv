#!/usr/bin/env python3
"""Separate review runner for eval_duration_v1 accounting predictor."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_drift_check import compute_drift_summary  # noqa: E402
from lib.rid_electrical_policy import policy_stamp  # noqa: E402
from lib.rid_electrical_predictor import (  # noqa: E402
    ALPHA,
    BETA,
    COVERAGE_NOTE,
    DOMAIN_MAX_S,
    DOMAIN_MIN_S,
    PLANT_CONFIG_ID,
    _AUTHORITY_FIELDS,
    predict_E_net,
)
from lib.rid_electrical_predictor_revalidation import (  # noqa: E402
    REVALIDATION_TRIGGERS,
    check_config_drift,
)

OUT = AUTO_ARTIFACTS / "rid_electrical" / "ledger_campaign"
LOCKED = OUT / "PREDICTOR_LOCKED_EVAL_DURATION_V1.json"
REVIEW_JSON = OUT / "PREDICTOR_REVIEW_V1.json"
REVIEW_MD = OUT / "PREDICTOR_REVIEW_V1.md"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _check_deterministic_against_lock(lock: dict) -> dict:
    c = lock.get("coefficients") or {}
    ok = (
        abs(float(c.get("alpha_j")) - ALPHA) < 1e-9
        and abs(float(c.get("beta_j_per_s")) - BETA) < 1e-9
        and float((lock.get("domain") or {}).get("min_eval_duration_s")) == DOMAIN_MIN_S
        and float((lock.get("domain") or {}).get("max_eval_duration_s")) == DOMAIN_MAX_S
    )
    return {"ok": bool(ok)}


def _check_adversarial_inputs() -> dict:
    cases = [float("nan"), float("inf"), float("-inf"), -1.0, "abc", "", None]
    rows = []
    ok = True
    for x in cases:
        r = predict_E_net(x)  # type: ignore[arg-type]
        this_ok = r.get("predicted_E_net_j") is None and r.get("confidence") == "invalid_input"
        ok = ok and this_ok
        rows.append({"input": str(x), "ok": this_ok, "confidence": r.get("confidence")})
    # boundary checks
    r_eps = predict_E_net(2.5 - 1e-15)
    r_low = predict_E_net(2.4999)
    b_ok = (
        r_eps.get("in_domain") is False or r_eps.get("in_domain") is True
    ) and r_low.get("confidence") == "out_of_validated_domain"
    ok = ok and b_ok
    rows.append({"input": "2.5-1e-15", "confidence": r_eps.get("confidence"), "ok": True})
    rows.append({"input": "2.4999", "confidence": r_low.get("confidence"), "ok": b_ok})
    # forged config
    forged = predict_E_net(3.0, plant_config_id="forged")
    forged_ok = forged.get("confidence") == "config_mismatch" and forged.get("predicted_E_net_j") is None
    ok = ok and forged_ok
    rows.append({"input": "config=forged", "confidence": forged.get("confidence"), "ok": forged_ok})
    return {"ok": ok, "cases": rows}


def _check_authority_immutability() -> dict:
    samples = [
        predict_E_net(3.0),
        predict_E_net(9.0),
        predict_E_net("abc"),  # type: ignore[arg-type]
        predict_E_net(3.0, plant_config_id="forged"),
    ]
    ok = True
    for s in samples:
        for k, v in _AUTHORITY_FIELDS.items():
            if s.get(k) is not v:
                ok = False
    return {"ok": ok, "authority_fields": dict(_AUTHORITY_FIELDS)}


def _check_uncertainty_naming() -> dict:
    r = predict_E_net(3.0)
    ok = (
        "heldout_rmse_j" in r
        and "empirical_error_scale_j" in r
        and "prediction_interval_j" not in r
        and r.get("coverage_note") == COVERAGE_NOTE
    )
    return {"ok": ok, "coverage_note": r.get("coverage_note")}


def _check_revalidation_registry() -> dict:
    need = {
        "model_or_quantization_change",
        "hardware_change_cpu_gpu",
        "driver_or_firmware_change",
        "telemetry_cadence_change",
        "baseline_recipe_change",
        "thermal_protocol_change",
        "executor_change",
        "residency_mode_change",
    }
    have = {t.get("trigger_id") for t in REVALIDATION_TRIGGERS}
    drift_ok = check_config_drift(PLANT_CONFIG_ID).get("match") is True
    mismatch_ok = check_config_drift("forged").get("action") == "revalidate_before_use"
    ok = need.issubset(have) and drift_ok and mismatch_ok
    return {"ok": ok, "count": len(REVALIDATION_TRIGGERS)}


def _check_drift_scaffold() -> dict:
    quiet = [{"residual_j": 5.0}, {"residual_j": -8.0}, {"residual_j": 6.0}]
    noisy = [{"residual_j": 60.0}, {"residual_j": -45.0}, {"residual_j": 50.0}]
    s_quiet = compute_drift_summary(quiet)
    s_noisy = compute_drift_summary(noisy)
    ok = (s_quiet.get("drift_alert") is False) and (s_noisy.get("drift_alert") is True)
    return {"ok": ok, "quiet": s_quiet, "noisy": s_noisy}


def main() -> int:
    if not LOCKED.exists():
        print(json.dumps({"error": "missing_locked_predictor", "path": str(LOCKED)}))
        return 1
    lock = json.loads(LOCKED.read_text(encoding="utf-8"))

    checks = {
        "deterministic_output": _check_deterministic_against_lock(lock),
        "adversarial_inputs": _check_adversarial_inputs(),
        "authority_immutability": _check_authority_immutability(),
        "uncertainty_naming": _check_uncertainty_naming(),
        "revalidation_registry": _check_revalidation_registry(),
        "drift_scaffold": _check_drift_scaffold(),
    }
    all_ok = all(v.get("ok") for v in checks.values())
    verdict = "accounting_predictor_approved" if all_ok else "review_failed"
    review = {
        "ok": all_ok,
        "at": _utc(),
        "predictor_version": lock.get("predictor_version"),
        "verdict": verdict,
        "checks": checks,
        "revalidation_triggers": list(REVALIDATION_TRIGGERS),
        "authority": {
            "accounting_only_estimates_authorized": bool(all_ok),
            "operational_authority": False,
            "master_routing_authorized": False,
            "auto_admit": False,
        },
        "policy": policy_stamp(),
    }
    REVIEW_JSON.write_text(json.dumps(review, indent=2), encoding="utf-8")
    lines = [
        "# Predictor separate review",
        "",
        f"- verdict: `{verdict}`",
        f"- all_checks_passed: `{all_ok}`",
        "- operational_authority: `false`",
        "- master_routing_authorized: `false`",
        "- auto_admit: `false`",
        "",
        "## Checks",
        "",
    ]
    for name, ck in checks.items():
        lines.append(f"- `{name}`: ok=`{ck.get('ok')}`")
    lines.append("")
    REVIEW_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"verdict": verdict, "artifact": str(REVIEW_JSON).replace("\\", "/")}, indent=2))
    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

