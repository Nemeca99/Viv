#!/usr/bin/env python3
"""Unit tests for V2 accounting approval stack (no plant)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_action_receipt import format_action_receipt  # noqa: E402
from lib.rid_electrical_policy import (  # noqa: E402
    ACCOUNTING_PREDICTOR_V2_APPROVED,
    PREDICTOR_V1_FROZEN,
    PREDICTOR_V2_STALE,
    apply_v2_approval_verdict,
    apply_v2_live_verdict,
)
from lib.rid_electrical_predictor import ALPHA, BETA  # noqa: E402
from lib.rid_electrical_predictor_registry import estimate_action, select_predictor  # noqa: E402
from lib.rid_electrical_predictor_v2 import clear_candidate_cache, predict_E_action  # noqa: E402
from lib.rid_electrical_v2_drift import evaluate_v2_drift, write_validated_baseline  # noqa: E402
from lib.rid_electrical_v2_live_shadow_eval import evaluate_live_shadow  # noqa: E402
import lib.rid_electrical_policy as policy  # noqa: E402


def test_registry_matrix() -> None:
    s1 = select_predictor(t_eval_s=3.5, residency="warm_repeat")
    assert s1["selected"] == "V1"
    s2 = select_predictor(
        t_eval_s=3.5, residency="cold_first", request_tail_accounting=True
    )
    assert s2["selected"] == "V2"
    s3 = select_predictor(t_eval_s=1.0, residency="warm_repeat")
    assert s3["selected"] is None
    s4 = select_predictor(
        t_eval_s=3.5,
        residency="warm_repeat",
        request_prompt_decomposition=True,
        request_tail_accounting=True,
    )
    assert s4["selected"] == "V2"


def test_v2_stale_nulls_expanded() -> None:
    apply_v2_live_verdict("v2_stale_revalidation_required")
    assert policy.PREDICTOR_V2_STALE is True
    s = select_predictor(
        t_eval_s=3.5, residency="cold_first", request_tail_accounting=True
    )
    assert s["selected"] is None
    assert "stale" in s["selection_reason"]
    # V1 specialty still selectable
    s1 = select_predictor(t_eval_s=3.5, residency="warm_repeat")
    assert s1["selected"] == "V1"
    apply_v2_live_verdict("v2_live_shadow_validated")


def test_v1_coeffs_unchanged() -> None:
    a0, b0 = ALPHA, BETA
    assert PREDICTOR_V1_FROZEN is True
    clear_candidate_cache()
    predict_E_action(
        t_eval_s=3.5, t_prompt_s=0.2, tail_horizon_s=5.0, residency="warm_repeat"
    )
    assert ALPHA == a0 and BETA == b0


def test_stratum_fail_hides_global() -> None:
    # Build synthetic: global looks ok but cold stratum fails
    actions = []
    for i in range(50):
        cold = i < 12
        # good warm residuals, bad cold
        meas = 1000.0
        hat = 1000.0 if not cold else 1000.0 * 0.5  # 50% error on cold
        actions.append(
            {
                "cold": cold,
                "prompt_variant": "short" if i % 2 == 0 else "long",
                "t_eval_s": 2.8 if i % 3 == 0 else 4.0,
                "tail_horizon_s": [5.0, 10.0, 20.0][i % 3],
                "measured_energy": meas if not cold else meas,
                "v2_prediction": hat,
                "v1_prediction": 480.0,
                "measured_E_net_j": 480.0,
                "registry_selected_predictor": "V2" if cold else "V1",
                "registry_predicted_E_j": 480.0,
            }
        )
    # Ensure stratum labels
    from lib.rid_electrical_v2_uncertainty import classify_strata

    for a in actions:
        a["strata"] = classify_strata(a)
    ev = evaluate_live_shadow(actions)
    # Cold should be rejected component
    assert "load" in (ev.get("rejected_components") or []) or not ev.get("full_approval")


def test_receipt_and_authority() -> None:
    text = format_action_receipt(
        {
            "component_estimates": {
                "E_load_j": 312,
                "E_prompt_j": 48,
                "E_eval_j": 481,
                "E_tail_j": 206,
            },
            "measured_energy": 1041,
            "predicted_E_j": 1022,
            "registry_selected_predictor": "V2",
            "confidence": "ok",
        }
    )
    assert "Model load:" in text
    assert "Predictor: V2" in text
    est = estimate_action(
        t_eval_s=3.5,
        t_prompt_s=0.2,
        tail_horizon_s=5.0,
        residency="warm_repeat",
        request_tail_accounting=True,
    )
    assert est.get("operational_authority") is False
    assert est.get("auto_admit") is False


def test_approval_verdict() -> None:
    r = apply_v2_approval_verdict(
        approved_components=["load", "prompt_eval", "tail_5"],
        full_approval=True,
    )
    assert r["accounting_predictor_v2_approved"] is True
    assert r["operational_authority"] is False
    # reset
    apply_v2_approval_verdict(approved_components=[], full_approval=False)
    assert policy.ACCOUNTING_PREDICTOR_V2_APPROVED is False


def test_drift_baseline() -> None:
    write_validated_baseline(rmse_j=50.0, n=40)
    # small residuals → validated
    ev = evaluate_v2_drift([1.0] * 25, apply_policy=False)
    assert ev["status"] in {
        "v2_live_shadow_validated",
        "insufficient_v2_live_sample",
    }
    # huge residuals → stale
    ev2 = evaluate_v2_drift([200.0] * 25, apply_policy=False)
    assert ev2["status"] == "v2_stale_revalidation_required"


def main() -> int:
    test_registry_matrix()
    test_v2_stale_nulls_expanded()
    test_v1_coeffs_unchanged()
    test_stratum_fail_hides_global()
    test_receipt_and_authority()
    test_approval_verdict()
    test_drift_baseline()
    print(json.dumps({"ok": True, "tests": "v2_accounting_approval"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
