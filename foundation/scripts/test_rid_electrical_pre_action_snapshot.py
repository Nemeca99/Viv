#!/usr/bin/env python3
"""Unit tests for PreActionSnapshotV1 contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_pre_action_snapshot import (  # noqa: E402
    FORBIDDEN_FEATURE_KEYS,
    capture_pre_action_snapshot,
    compute_snapshot_hash,
    feature_leakage_audit,
    join_pre_action_outcome,
    predict_pre_action_E_net,
    required_features_present,
    verify_snapshot_integrity,
)
from lib.rid_electrical_predictor import PLANT_CONFIG_ID  # noqa: E402


def main() -> int:
    snap = capture_pre_action_snapshot(
        action_id="test_a1",
        num_predict=360,
        prompt="Explain GPU power briefly.",
        gpu_temp_start_c=48.0,
        settled_idle_power_w=54.0,
        trailing_throughput_tps=103.0,
        throughput_history_count=20,
        collection_session_id="test_sess",
        collection_group=1,
        prompt_variant="medium",
        persist=False,
    )
    ok, reason = verify_snapshot_integrity(snap)
    assert ok and reason == "ok"
    # Tamper detection
    bad = dict(snap)
    bad["num_predict"] = 999
    ok2, reason2 = verify_snapshot_integrity(bad)
    assert ok2 is False and reason2 == "snapshot_hash_mismatch"

    ok_f, missing = required_features_present(snap)
    assert ok_f and not missing

    # Forbidden feature leakage
    leak = feature_leakage_audit(
        [{"features": {"num_predict": 1, "prompt_eval_count": 12}, "snapshot": snap}]
    )
    assert leak["ok"] is False
    assert any(x["field"] == "prompt_eval_count" for x in leak["leaks"])

    # Join outcome
    snap_join = dict(snap)
    snap_join["at"] = "2099-01-01T00:00:00+00:00"
    snap_join["day_id"] = "2099-01-01"
    snap_join["snapshot_hash"] = compute_snapshot_hash(snap_join)
    row = join_pre_action_outcome(
        snap_join["snapshot_id"],
        {
            "at": "2099-01-01T00:00:10+00:00",
            "E_net_raw_j": 400.0,
            "measurement_state": "measured",
            "SNR_net": 5.0,
            "settle_ok": True,
            "integration_ok": True,
            "plant_config_id": PLANT_CONFIG_ID,
        },
        snapshot=snap_join,
        persist=False,
    )
    assert row["eligible"] is True
    assert row["features"] is not None

    # Timing-only ineligible
    row2 = join_pre_action_outcome(
        snap_join["snapshot_id"],
        {
            "at": "2099-01-01T00:00:10+00:00",
            "E_net_raw_j": 400.0,
            "measurement_state": "timing_only",
            "SNR_net": 5.0,
            "settle_ok": True,
            "integration_ok": True,
            "plant_config_id": PLANT_CONFIG_ID,
        },
        snapshot=snap_join,
        persist=False,
    )
    assert row2["eligible"] is False
    assert "timing_only" in row2["eligibility_reasons"]

    # Predict null on config mismatch
    pred = predict_pre_action_E_net(
        {
            "num_predict": 360,
            "trailing_throughput_tps": 103.0,
            "throughput_history_count": 20,
        },
        plant_config_id="wrong-config",
    )
    assert pred["predicted_E_net_j"] is None
    assert pred["confidence"] == "config_mismatch"
    assert pred["gates_action"] is False

    # Hash recomputed
    h = compute_snapshot_hash(snap)
    assert h == snap["snapshot_hash"]
    assert "prompt_eval_count" in FORBIDDEN_FEATURE_KEYS

    print(json.dumps({"ok": True, "tests": "pre_action_snapshot_pass"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
