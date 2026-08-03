#!/usr/bin/env python3
"""Tests for auditable energy ledger stack (no plant run)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_action_accounting import (  # noqa: E402
    account_gpu_inference,
    format_accounting_report,
)
from lib.rid_electrical_cost_decomposition import campaign_manifest  # noqa: E402
from lib.rid_electrical_energy_ledger import (  # noqa: E402
    append_action_row,
    joules_to_kwh,
    load_actions,
    summarize_daily,
    summarize_sessions,
)
from lib.rid_electrical_policy import PREDICTOR_V1_FROZEN, policy_stamp  # noqa: E402
from lib.rid_electrical_predictor import ALPHA, BETA, PLANT_CONFIG_ID  # noqa: E402


def main() -> int:
    assert PREDICTOR_V1_FROZEN is True
    stamp = policy_stamp()
    assert stamp["predictor_v1_frozen"] is True
    assert stamp["master_weight_enabled"] is False
    assert stamp["advisory_routing_enabled"] is False

    # Accounting report fields + authority false
    t = 3.5
    measured = ALPHA + BETA * t - 9.0
    rep = account_gpu_inference(
        action_id="test_action_1",
        model="viv-voice-qwen",
        eval_duration_s=t,
        measured_E_net_j=measured,
        actual_eval_tokens=360,
        session_id="test_session_ledger",
        plant_config_id=PLANT_CONFIG_ID,
        gpu_temp_start_c=44.0,
        gpu_temp_end_c=48.0,
        residency_state="warm_repeat",
        refresh_drift=True,
        append_drift_log=True,
    )
    assert rep["gates_action"] is False
    assert rep["operational_authority"] is False
    assert rep["master_routing_authorized"] is False
    assert rep["auto_admit"] is False
    assert "human_report" in rep
    text = format_accounting_report(rep)
    assert "GPU inference accounting" in text
    assert "Estimated:" in text

    # Ledger aggregation math
    tmp = FOUNDATION / "artifacts" / "auto" / "rid_electrical" / "energy_ledger" / "_test_actions.jsonl"
    if tmp.exists():
        tmp.unlink()
    r1 = append_action_row(
        {
            "action_id": "a1",
            "session_id": "s1",
            "action_type": "controlled_generate_v2",
            "model": "viv-voice-qwen",
            "residency_state": "warm_repeat",
            "measured_E_net_j": 100.0,
            "predicted_E_net_j": 110.0,
            "residual_j": -10.0,
            "executor": "gpu",
            "at": "2026-07-27T08:00:00+00:00",
        },
        path=tmp,
    )
    append_action_row(
        {
            "action_id": "a2",
            "session_id": "s1",
            "action_type": "controlled_generate_v2",
            "model": "viv-voice-qwen",
            "residency_state": "warm_repeat",
            "measured_E_net_j": 200.0,
            "executor": "gpu",
            "at": "2026-07-27T08:01:00+00:00",
        },
        path=tmp,
    )
    append_action_row(
        {
            "action_id": "a3",
            "session_id": "s2",
            "action_type": "controlled_generate_v2",
            "model": "viv-voice-qwen",
            "residency_state": "cold_first",
            "measured_E_net_j": 50.0,
            "executor": "gpu",
            "at": "2026-07-28T08:00:00+00:00",
        },
        path=tmp,
    )
    rows = load_actions(tmp)
    sess = summarize_sessions(rows)
    daily = summarize_daily(rows)
    assert sess["n_sessions"] == 2
    s1 = next(s for s in sess["sessions"] if s["session_id"] == "s1")
    assert abs(s1["E_session_j"] - 300.0) < 1e-9
    assert abs(s1["E_session_kWh"] - joules_to_kwh(300.0)) < 1e-12
    d27 = next(d for d in daily["days"] if d["date"] == "2026-07-27")
    assert abs(d27["E_daily_j"] - 300.0) < 1e-9
    assert sess["authority"]["operational_authority"] is False
    assert r1["gates_action"] is False
    tmp.unlink(missing_ok=True)

    # Decomposition scaffold
    man = campaign_manifest()
    assert man["v2_fit_authorized"] is False
    assert "load_residency" in man["families"]
    assert "prompt_eval" in man["families"]
    assert "post_action_tail" in man["families"]
    assert man["authority"]["auto_admit"] is False

    # Freeze artifact presence after runner (optional if already frozen)
    freeze_path = (
        FOUNDATION
        / "artifacts"
        / "auto"
        / "rid_electrical"
        / "ledger_campaign"
        / "PREDICTOR_V1_BASELINE_FROZEN.json"
    )
    if freeze_path.exists():
        fr = json.loads(freeze_path.read_text(encoding="utf-8"))
        assert fr.get("refit_forbidden") is True
        assert "checksums_sha256" in fr

    print("PASS test_rid_electrical_auditable_ledger")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
