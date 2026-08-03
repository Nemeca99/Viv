#!/usr/bin/env python3
"""Tests for session eval, routing quality, canary math, ablation helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.rid_electrical import choose_route_quality, routing_quality  # noqa: E402
from lib.rid_electrical_session_eval import (  # noqa: E402
    clean_improvement,
    evaluate_feature_on_holdout,
    split_train_test_sessions,
)

spec = importlib.util.spec_from_file_location(
    "rid_electrical_master_canary",
    FOUNDATION / "scripts" / "rid_electrical_master_canary.py",
)
assert spec and spec.loader
canary_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary_mod)


def _synth_session(workload: str, n: int, master0: float, drift: float) -> dict:
    samples = []
    for i in range(n):
        m = master0 + drift * i
        samples.append(
            {
                "master_s_n": m,
                "S_electrical": max(0.05, m * 0.8),
                "P_rails": {"w_cpu": 50 + i, "w_gpu": 20 + i * 0.5},
                "V_rails": {"v_cpu": 1.2, "v_gpu": 0.7},
                "I_derived": {"i_cpu": 40.0, "i_gpu": 1.5},
                "cadence_s": 1.0,
                "collect_overhead_ms": 2.0,
                "workload": workload,
            }
        )
    return {
        "session_id": f"{workload}_synth",
        "workload": workload,
        "samples": samples,
        "dynamic": True,
        "master_var": 0.01,
        "meta": {"duration_s": float(n)},
    }


def main() -> int:
    # Routing Q_i
    q = routing_quality(10.0, predicted_joules=2.0, predicted_stability_loss=1.0, latency=1.0)
    assert abs(q - 10.0 / 4.0) < 1e-9
    route = choose_route_quality(
        {
            "CPU": {"useful_work": 1.0, "joules": 40.0, "stability_loss": 0.2, "latency": 1.0},
            "GPU": {"useful_work": 1.4, "joules": 120.0, "stability_loss": 0.5, "latency": 1.2},
        }
    )
    assert route["ok"] is True
    assert route["choice"] in {"CPU", "GPU"}
    assert route["advisory"] is True

    # Canary math
    m = canary_mod.canary_master(0.5, 0.5, 0.05)
    assert 0.0 < m <= 1.0

    # Session holdout split + feature eval
    sessions = [
        _synth_session("cpu_ramp", 20, 0.5, -0.01),
        _synth_session("gpu_infer", 20, 0.45, -0.008),
        _synth_session("mixed", 20, 0.4, -0.012),
    ]
    train, test = split_train_test_sessions(sessions)
    assert len(train) >= 1 and len(test) >= 1
    abl = evaluate_feature_on_holdout(train, test, "S_electrical")
    assert abl["test_n"] > 0
    assert "delta_info" in abl

    # Clean improvement rejects high FA
    assert clean_improvement(0.01, {"false_warning_rate": 0.1}) is True
    assert clean_improvement(0.01, {"false_warning_rate": 0.9}) is False
    assert clean_improvement(0.001, {"false_warning_rate": 0.0}) is False

    print("PASS test_rid_electrical_info_gain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
