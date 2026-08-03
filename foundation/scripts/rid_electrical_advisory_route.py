#!/usr/bin/env python3
"""Advisory routing sidecar — DISABLED for operational use after negative evidence.

May still emit diagnostic rail snapshots. Does not change Master/PRT behavior.
Predictor/routing recommendations are marked non-operational.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_advisory_route.py --once
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FOUNDATION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOUNDATION))

from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical import choose_route_quality  # noqa: E402
from lib.rid_electrical_capture import collect_sample  # noqa: E402
from lib.rid_electrical_policy import (  # noqa: E402
    LIFECYCLE,
    RAIL_ROLE,
    gate_advisory_behavior,
    policy_stamp,
)

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
FLAG = "rid_electrical_advisory_route_v1"


def advise_once() -> dict[str, Any]:
    gate = gate_advisory_behavior(request_behavior_change=False)
    sample = collect_sample(
        session_id="advisory_once",
        workload="advisory",
        phase="observe",
        sample_i=0,
        cadence_s=1.0,
        t0_mono=0.0,
    )
    p = sample.get("P_rails") or {}
    w_cpu = float(p.get("w_cpu") or 0.0)
    w_gpu = float(p.get("w_gpu") or 0.0)
    s_el = sample.get("S_electrical")
    master = sample.get("master_s_n")
    coolant = sample.get("coolant_c")

    # Archival Q_i computation retained as evidence scaffold — non-operational.
    cpu_headroom = 1.0
    if coolant is not None:
        cpu_headroom = max(0.2, min(1.5, (45.0 - float(coolant)) / 20.0 + 1.0))
    stability_loss_cpu = max(0.0, 1.0 - float(master)) if master is not None else 0.5
    stability_loss_gpu = stability_loss_cpu
    if s_el is not None:
        stability_loss_gpu = max(stability_loss_gpu, 1.0 - float(s_el))
    candidates = {
        "CPU": {
            "useful_work": 1.0 * cpu_headroom,
            "joules": max(1.0, w_cpu),
            "stability_loss": stability_loss_cpu,
            "latency": 1.0,
        },
        "GPU": {
            "useful_work": 1.4,
            "joules": max(1.0, w_gpu),
            "stability_loss": stability_loss_gpu,
            "latency": 1.2,
        },
    }
    route = choose_route_quality(candidates)

    payload = {
        "ok": True,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "flag": FLAG,
        "flag_enabled": False,
        "authority": gate["authority"],
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "advisory_routing_enabled": False,
        "predictor_operational": False,
        "admission_granted": False,
        "electrical_in_A_t": False,
        "sample": {
            "w_cpu": w_cpu,
            "w_gpu": w_gpu,
            "S_electrical": s_el,
            "master_s_n": master,
            "coolant_c": coolant,
        },
        "diagnostics": {
            "board_power_w": {"cpu": w_cpu, "gpu": w_gpu},
            "note": "Diagnostic snapshot only — not a routing decision.",
        },
        "candidates": candidates,
        "route_archival_non_operational": route,
        "recommendation": None,
        "advice": (
            "Advisory routing disabled after decisive negative Δ_info. "
            "Do not use Q_i output for decisions. Rails remain observe_only_diagnostics."
        ),
        "policy": policy_stamp(),
        "note": (
            "Scaffold retained. Behavior change forbidden. "
            "Telemetry is diagnostic, not predictive."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "advisory_route_latest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact"] = str(path).replace("\\", "/")
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", default=True)
    p.parse_args()
    out = advise_once()
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
