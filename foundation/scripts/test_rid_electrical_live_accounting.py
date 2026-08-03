#!/usr/bin/env python3
"""Unit tests for live accounting validation (no plant run)."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_drift_check import (  # noqa: E402
    MIN_LIVE_N,
    PLANT_CONFIG_ID,
    evaluate_live_accounting,
    record_accounting_use,
)
from lib.rid_electrical_policy import (  # noqa: E402
    PREDICTOR_BLOCKED,
    apply_live_accounting_verdict,
    policy_stamp,
)
from lib.rid_electrical_predictor import ALPHA, BETA  # noqa: E402


def _synth_records(n: int, *, noise: float = 2.0) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        t = 2.5 + (i % 5) * 0.5
        predicted = ALPHA + BETA * t
        measured = predicted + ((-1) ** i) * noise
        rec = record_accounting_use(
            t,
            measured,
            session_id=f"synth_{i}",
            plant_config_id=PLANT_CONFIG_ID,
            gpu_temp_settle_c=45.0,
            residency="warm_repeat",
            append=False,
        )
        rows.append(rec)
    return rows


def main() -> int:
    # insufficient sample
    short = _synth_records(MIN_LIVE_N - 1, noise=2.0)
    v1 = evaluate_live_accounting(short)
    assert v1["status"] == "insufficient_live_sample", v1
    assert v1["live_accounting_validated"] is False
    assert v1["predictor_stale"] is False
    assert v1["operational_authority"] is False
    assert v1["master_routing_authorized"] is False
    assert v1["auto_admit"] is False

    # validated
    good = _synth_records(MIN_LIVE_N, noise=2.0)
    v2 = evaluate_live_accounting(good)
    assert v2["status"] == "live_accounting_validated", v2
    assert v2["live_accounting_validated"] is True
    assert v2["predictor_stale"] is False
    assert v2["n_usable"] >= MIN_LIVE_N

    # stale
    bad = _synth_records(MIN_LIVE_N, noise=80.0)
    v3 = evaluate_live_accounting(bad)
    assert v3["status"] == "predictor_stale_revalidation_required", v3
    assert v3["predictor_stale"] is True
    assert v3["live_accounting_validated"] is False

    # Authority never granted by policy apply
    for status in (
        "insufficient_live_sample",
        "live_accounting_validated",
        "predictor_stale_revalidation_required",
    ):
        upd = apply_live_accounting_verdict(status)
        assert upd["operational_authority"] is False
        assert upd["master_routing_authorized"] is False
        assert upd["auto_admit"] is False

    stamp = policy_stamp()
    assert stamp["predictor_blocked"] is True
    assert PREDICTOR_BLOCKED is True
    assert stamp["predictor_blocked_meaning"] == (
        "blocked_from_operational_control_not_guarded_accounting"
    )
    assert stamp["master_weight_enabled"] is False
    assert stamp["advisory_routing_enabled"] is False

    print("PASS test_rid_electrical_live_accounting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
