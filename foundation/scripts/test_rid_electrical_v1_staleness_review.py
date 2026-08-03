#!/usr/bin/env python3
"""Unit tests for V1 staleness review (no plant run)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_drift_check import (  # noqa: E402
    PLANT_CONFIG_ID,
    audit_drift_eligibility,
    classify_drift_record,
    evaluate_live_accounting,
)
from lib.rid_electrical_predictor import ALPHA, BETA  # noqa: E402
from lib.rid_electrical_predictor_registry import estimate_action, select_predictor  # noqa: E402
from lib.rid_electrical_v1_staleness_review import (  # noqa: E402
    containment_probes,
    decide,
    localize_cause,
)
import lib.rid_electrical_policy as _policy  # noqa: E402


def main() -> int:
    # Cold residency excluded
    cold = {
        "in_domain": True,
        "plant_config_id": PLANT_CONFIG_ID,
        "residency": "cold_first",
        "eval_duration_s": 3.5,
        "measured_E_net_j": 700.0,
        "residual_j": 200.0,
        "confidence": "ok",
    }
    ok, reason = classify_drift_record(cold)
    assert ok is False and reason == "non_warm_residency"

    # Timing-only excluded
    timing = {
        **cold,
        "residency": "warm_repeat",
        "measurement_state": "timing_only",
        "residual_j": 5.0,
    }
    ok2, reason2 = classify_drift_record(timing)
    assert ok2 is False and reason2 == "timing_only"

    # Warm measured eligible
    warm = {
        "in_domain": True,
        "plant_config_id": PLANT_CONFIG_ID,
        "residency": "warm_repeat",
        "eval_duration_s": 3.5,
        "measured_E_net_j": ALPHA + BETA * 3.5 + 2.0,
        "residual_j": 2.0,
        "confidence": "ok",
        "revalidation_fingerprint": None,
    }
    ok3, reason3 = classify_drift_record(warm)
    assert ok3 is True and reason3 == "eligible"

    # Exact false-stale case: 25 warm @ 16.041 J + 3 cold_first @ 143.434 J
    from lib.rid_electrical_pre_action_monitor_lock import (  # noqa: E402
        assert_false_stale_rmse,
        build_false_stale_regression_rows,
    )

    rows = build_false_stale_regression_rows()
    audit = audit_drift_eligibility(rows)
    assert audit["speech_contaminated"] is False
    assert audit["n_eligible"] == 25
    assert audit["by_reason"].get("non_warm_residency") == 3
    reg = assert_false_stale_rmse(audit)
    assert abs(reg["pooled_legacy_rmse_j"] - 49.336) < 0.002
    assert abs(reg["eligible_rmse_j"] - 16.041) < 0.002
    assert audit["eligible_passes_gate"] is True
    # Pooled path would look stale; eligible replay validates
    assert reg["legacy_would_be_stale"] is True
    replay = evaluate_live_accounting(rows)
    assert replay["status"] == "live_accounting_validated"
    assert replay["predictor_stale"] is False

    # Stale V1 null; no V2 warm substitute
    contain = containment_probes()
    assert contain["pass"] is True, contain

    prev = _policy.PREDICTOR_STALE
    try:
        _policy.PREDICTOR_STALE = True
        est = estimate_action(
            t_eval_s=3.5,
            residency="warm_repeat",
            plant_config_id=PLANT_CONFIG_ID,
            measured_E_net_j=480.0,
        )
        assert est["registry_selected_predictor"] is None
        assert est["predicted_E_j"] is None
        assert select_predictor(t_eval_s=3.5, residency="warm_repeat").get("selected") != "V2"
    finally:
        _policy.PREDICTOR_STALE = prev

    cause = localize_cause(rows, audit=audit)
    assert cause["cause_class"] == "monitor_or_receipt_semantics_fault"
    assert cause["updates_v1"] is False

    lock = decide(
        cause=cause,
        audit=audit,
        replay=replay,
        revalidation={"skipped": True, "reason": "eligible_replay_clears_stale_or_insufficient"},
    )
    assert lock["v1_coefficients_mutated"] is False
    assert lock["auto_refit"] is False
    assert lock["locked_alpha_j"] == ALPHA
    assert lock["locked_beta_j_per_s"] == BETA
    assert lock["authority"]["auto_admit"] is False

    # Synchronized ops status after monitor lock writer
    from lib.rid_electrical_pre_action_monitor_lock import (  # noqa: E402
        verify_monitor_lock_consistency,
        write_monitor_lock,
    )

    mon = write_monitor_lock(reconcile=True, regression_check=True)
    assert mon.get("ok") is True
    assert mon.get("reconcile_ok") is True
    verify = verify_monitor_lock_consistency()
    assert verify.get("ok") is True, verify

    print(json.dumps({"ok": True, "tests": "pass"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
