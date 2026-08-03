#!/usr/bin/env python3
"""Unit tests for production accounting registry (no plant run)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_accounting_registry_release import (  # noqa: E402
    RELEASE_ID,
    RegistryReleaseImmutabilityError,
    load_registry_release,
)
from lib.rid_electrical_energy_ledger import append_action_row, load_actions  # noqa: E402
from lib.rid_electrical_policy import policy_stamp  # noqa: E402
from lib.rid_electrical_predictor import PLANT_CONFIG_ID  # noqa: E402
from lib.rid_electrical_predictor_registry import (  # noqa: E402
    estimate_action,
    map_request_component,
    select_predictor,
)
from lib.rid_electrical_registry_health import evaluate_registry_health  # noqa: E402
import lib.rid_electrical_policy as _policy  # noqa: E402


def main() -> int:
    stamp = policy_stamp()
    assert stamp["accounting_predictor_v2_approved"] is True
    assert "load" in stamp["v2_approved_components"]

    # --- Freeze immutability ---
    rel = load_registry_release()
    assert rel["release_id"] == RELEASE_ID
    assert rel["immutable"] is True
    assert rel["silent_mutate_forbidden"] is True
    try:
        rel["release_id"] = "mutated"
        raise AssertionError("expected RegistryReleaseImmutabilityError")
    except RegistryReleaseImmutabilityError:
        pass

    # --- Rejected strata → null, no nearby fallback ---
    assert map_request_component(
        residency="warm_repeat",
        request_tail_accounting=True,
        tail_horizon_s=5.0,
    ) == "tail_5"
    assert map_request_component(
        residency="warm_repeat",
        request_prompt_decomposition=True,
        request_tail_accounting=False,
    ) == "warm_prompt_eval"

    t5 = estimate_action(
        t_eval_s=3.5,
        t_prompt_s=0.2,
        tail_horizon_s=5.0,
        residency="warm_repeat",
        request_tail_accounting=True,
        request_prompt_decomposition=False,
        plant_config_id=PLANT_CONFIG_ID,
        measured_E_net_j=500.0,
        measured_E_tail_j=600.0,
    )
    assert t5["registry_selected_predictor"] is None
    assert t5["predicted_E_j"] is None
    assert t5["confidence"] == "rejected_stratum"
    assert "rejected_stratum:tail_5" in str(t5["selection_reason"])
    assert t5["registry_release_id"] == RELEASE_ID

    wpe = estimate_action(
        t_eval_s=3.5,
        t_prompt_s=1.0,
        tail_horizon_s=None,
        residency="warm_repeat",
        request_tail_accounting=False,
        request_prompt_decomposition=True,
        plant_config_id=PLANT_CONFIG_ID,
        measured_E_net_j=400.0,
    )
    assert wpe["registry_selected_predictor"] is None
    assert wpe["predicted_E_j"] is None
    assert wpe["confidence"] == "rejected_stratum"

    # Approved tail_10 still selectable (not nearby fallback from tail_5)
    t10 = select_predictor(
        t_eval_s=3.5,
        residency="warm_repeat",
        request_tail_accounting=True,
        tail_horizon_s=10.0,
    )
    assert t10["selected"] == "V2"
    assert t10["request_component"] == "tail_10"

    # Cold load approved even with 5s measured horizon when not requesting warm tail_5
    cold = select_predictor(
        t_eval_s=3.5,
        residency="cold_first",
        request_tail_accounting=False,
        request_prompt_decomposition=True,
        tail_horizon_s=5.0,
    )
    assert cold["selected"] == "V2"
    assert cold["request_component"] in {"load", "prompt_eval"}

    # --- V2 stale leaves V1 ---
    prev_stale = _policy.PREDICTOR_V2_STALE
    try:
        _policy.PREDICTOR_V2_STALE = True
        stale_exp = select_predictor(
            t_eval_s=3.5,
            residency="cold_first",
            request_tail_accounting=False,
        )
        assert stale_exp["selected"] is None
        assert "v2_stale" in str(stale_exp["selection_reason"])
        v1_ok = select_predictor(
            t_eval_s=3.5,
            residency="warm_repeat",
            request_tail_accounting=False,
            request_prompt_decomposition=False,
        )
        assert v1_ok["selected"] == "V1"
    finally:
        _policy.PREDICTOR_V2_STALE = prev_stale

    # --- Ledger persists registry fields ---
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "actions.jsonl"
        append_action_row(
            {
                "action_id": "r1",
                "session_id": "s1",
                "model": "viv-voice-qwen",
                "residency_state": "warm_repeat",
                "measured_E_net_j": 100.0,
                "selected_predictor": None,
                "registry_selected_predictor": None,
                "selection_reason": "rejected_stratum:tail_5",
                "request_component": "tail_5",
                "predicted_E_j": None,
                "measured_E_j": 100.0,
                "residual_j": None,
                "prediction_domain": "rejected_stratum",
                "drift_state_v1": "ok",
                "drift_state_v2": "ok",
                "registry_release_id": RELEASE_ID,
                "plant_config_id": PLANT_CONFIG_ID,
                "confidence": "rejected_stratum",
            },
            path=p,
        )
        rows = load_actions(p)
        assert len(rows) == 1
        assert rows[0]["registry_release_id"] == RELEASE_ID
        assert rows[0]["selection_reason"] == "rejected_stratum:tail_5"
        assert rows[0]["request_component"] == "tail_5"
        assert rows[0]["drift_state_v1"] == "ok"

    # --- Health gates fail closed on rejected-stratum leakage ---
    leak_rows = [
        {
            "registry_selected_predictor": "V2",
            "selected_predictor": "V2",
            "request_component": "tail_5",
            "predicted_E_j": 999.0,
            "measured_E_j": 1000.0,
            "selection_reason": "expanded_coverage:tail_accounting",
            "prediction_domain": "tail_accounting",
            "drift_state_v1": "ok",
            "drift_state_v2": "ok",
            "registry_release_id": RELEASE_ID,
            "plant_config_id": PLANT_CONFIG_ID,
        }
    ] + [
        {
            "registry_selected_predictor": "V1",
            "selected_predictor": "V1",
            "request_component": None,
            "predicted_E_j": 480.0,
            "measured_E_j": 500.0,
            "measured_E_net_j": 500.0,
            "selection_reason": "warm_eval_only_v1_specialty",
            "prediction_domain": "warm_eval_net",
            "drift_state_v1": "ok",
            "drift_state_v2": "ok",
            "registry_release_id": RELEASE_ID,
            "plant_config_id": PLANT_CONFIG_ID,
        }
        for _ in range(40)
    ]
    bad = evaluate_registry_health(leak_rows)
    assert bad["gates"]["rejected_stratum_null_fidelity"]["pass"] is False
    assert bad["status"] == "production_accounting_registry_incomplete"

    # Closed strata artifact
    closed = (
        FOUNDATION
        / "artifacts"
        / "auto"
        / "rid_electrical"
        / "ledger_campaign"
        / "CLOSED_REJECTED_STRATA_V1.json"
    )
    assert closed.exists(), "CLOSED_REJECTED_STRATA_V1.json missing"
    cdata = json.loads(closed.read_text(encoding="utf-8"))
    assert cdata["strata"]["tail_5"]["status"] == "closed_negative"
    assert cdata["strata"]["warm_prompt_eval"]["status"] == "closed_negative"

    print(json.dumps({"ok": True, "tests": "pass"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
