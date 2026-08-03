#!/usr/bin/env python3
"""Tests for calibrated action-cost ledger accounting."""
from __future__ import annotations

import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical_outcomes import (  # noqa: E402
    WARN_MIN_DURATION_S,
    cost_profiles_from_actions,
    integrate_energy_j,
    ledger_from_session,
    overload_with_duration,
    validated_energy,
)


def _samp(mono: float, w_cpu: float, w_gpu: float, phase: str, **kw):
    row = {
        "mono_s": mono,
        "at": f"2026-07-27T00:00:{int(mono):02d}Z",
        "phase": phase,
        "workload": "gpu_infer",
        "session_id": "test_sess",
        "sensor_age_s": 0.2,
        "P_rails": {"w_cpu": w_cpu, "w_gpu": w_gpu, "pcie_w": 5.0, "pin8_w": w_gpu * 0.8},
        "coolant_c": 38.0,
    }
    row.update(kw)
    return row


def main() -> int:
    # Constant 100 W for 10 s → 1000 J gross
    e = integrate_energy_j([0.0, 5.0, 10.0], [100.0, 100.0, 100.0])
    assert e["ok"] and abs(float(e["E_j"]) - 1000.0) < 1e-6

    # Validated: idle 20 W then load 120 W
    samples = []
    for i in range(0, 5):
        samples.append(_samp(float(i), 10.0, 10.0, "idle"))  # 20 W board
    for i in range(5, 15):
        samples.append(_samp(float(i), 60.0, 60.0, "sustained"))  # 120 W
    v = validated_energy(samples)
    assert v["confidence"] in {"valid", "degraded"}
    assert v["E_gross_j"] is not None
    assert v["E_net_j"] is not None
    # Sanity: E ≈ P_mean * dt
    assert v["quality"]["sanity_ok"] is True
    assert v["P_idle_baseline_w"] is not None
    assert abs(float(v["E_net_j"]) - (float(v["E_gross_j"]) - float(v["P_idle_baseline_w"]) * float(v["duration_s"]))) < 1e-6

    # Instantaneous spike should NOT warn with τ=3s
    times = [float(i) for i in range(10)]
    powers = [100.0] * 10
    powers[5] = 300.0  # single spike
    ov = overload_with_duration(times, powers, min_duration_s=WARN_MIN_DURATION_S, warn_w=250.0)
    assert ov["level"] == "ok", ov
    assert "below_min_duration" in ov["reason"] or "not_warned" in ov["reason"]

    # Sustained high power should warn
    powers2 = [280.0] * 10
    ov2 = overload_with_duration(times, powers2, min_duration_s=3.0, warn_w=250.0)
    assert ov2["level"] == "warn", ov2

    # Ledger attribution
    meta = {"session_id": "test_sess", "workload": "gpu_infer", "events": [{"model": "viv-voice-qwen"}]}
    led = ledger_from_session(samples, meta)
    assert led["n_actions"] >= 2
    active = [a for a in led["actions"] if a["action_type"] == "active_load"]
    assert len(active) == 1
    assert active[0]["E_net_j"] is not None
    assert active[0]["human_summary"]
    assert "token_count_not_instrumented" in (active[0].get("task_size_note") or "")

    # Profiles
    rows = []
    for k in range(3):
        rows.append(
            {
                "action_type": "active_load",
                "workload": "gpu_infer",
                "E_net_j": 2000.0 + k * 50,
                "P_peak_w": 160.0 + k,
                "J_per_second": 20.0,
                "confidence": "valid",
                "overload_level": "ok",
                "human_summary": f"ex{k}",
            }
        )
    prof = cost_profiles_from_actions(rows)
    assert "gpu_infer" in prof["profiles"]
    assert prof["profiles"]["gpu_infer"]["n"] == 3
    assert prof["profiles"]["gpu_infer"]["repeatable_signature"] is True

    print("PASS test_rid_electrical_outcomes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
