#!/usr/bin/env python3
"""Master electrical canary — PERMANENTLY DISABLED after negative decisive evidence.

Scaffold retained as evidence of what was examined. Apply always fail-closed.
Lifecycle: rejected_operational_use. Rails: observe_only_diagnostics.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_master_canary.py --dry-run
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

from lib.master_rid import MASTER_RID_PATH, load_master_rid  # noqa: E402
from lib.paths import AUTO_ARTIFACTS  # noqa: E402
from lib.rid_electrical_capture import collect_sample  # noqa: E402
from lib.rid_electrical_policy import (  # noqa: E402
    LIFECYCLE,
    RAIL_ROLE,
    ElectricalAuthorityDenied,
    assert_master_write_forbidden,
    gate_canary_apply,
    policy_stamp,
)

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
FLAG_NAME = "rid_electrical_master_canary_v1"
FLAG_FILE = OUT_DIR / "CANARY_ENABLE.json"
DEFAULT_W_E = 0.05  # archival formula only; never applied


def _flag_enabled() -> bool:
    """Canary cannot be enabled after closed prediction branch."""
    return False


def canary_master(master_s_n: float, s_electrical: float, w_e: float) -> float:
    """Archival formula only — output is non-operational."""
    m = max(1e-6, min(1.0, float(master_s_n)))
    s = max(1e-6, min(1.0, float(s_electrical)))
    w = float(w_e)
    if w <= 0.0:
        return m
    return max(0.0, min(1.0, (m * (s**w)) ** (1.0 / (1.0 + w))))


def run(*, apply: bool = False, w_e: float = DEFAULT_W_E) -> dict[str, Any]:
    sample = collect_sample(
        session_id="canary_once",
        workload="canary",
        phase="observe",
        sample_i=0,
        cadence_s=1.0,
        t0_mono=0.0,
    )
    master = load_master_rid()
    master_s = None if master is None else float(master.master_s_n)
    s_el = sample.get("S_electrical")
    gate = gate_canary_apply(apply=apply, context="master_canary")
    shadow_m = None
    if master_s is not None and s_el is not None:
        shadow_m = canary_master(master_s, float(s_el), w_e)

    applied = False
    reason = gate["reason"]
    if apply:
        try:
            assert_master_write_forbidden(context="master_canary_apply")
        except ElectricalAuthorityDenied as exc:
            reason = str(exc)

    payload = {
        "ok": True,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "flag": FLAG_NAME,
        "flag_file": str(FLAG_FILE).replace("\\", "/"),
        "flag_enabled": _flag_enabled(),
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "predictor_operational": False,
        "w_e": w_e,
        "master_s_n": master_s,
        "S_electrical": s_el,
        "canary_master_s_n": shadow_m,
        "canary_output_operational": False,
        "lane_advancement_eligible": False,
        "applied": applied,
        "recommend_rollback": True,
        "reason": reason,
        "formula": "Master'=(Master * S_electrical^w_e)^(1/(1+w_e)) [archival non-operational]",
        "policy": policy_stamp(),
        "note": (
            "Canary permanently disabled after decisive negative Δ_info. "
            "Scaffold retained; Master write fail-closed."
        ),
        "master_path": str(MASTER_RID_PATH).replace("\\", "/"),
        "master_disk_mutated": False,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "master_canary_latest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["artifact"] = str(path).replace("\\", "/")
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--apply", action="store_true", help="Always fail-closed after closed branch")
    p.add_argument("--w-e", type=float, default=DEFAULT_W_E)
    args = p.parse_args()
    out = run(apply=bool(args.apply), w_e=float(args.w_e))
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
