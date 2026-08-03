#!/usr/bin/env python3
"""Observe-only CPU↔GPU electrical inventory — never mutates Master RID.

Reads only meters that foundation already exposes. Incomplete channels fail
closed (available=false, s_electrical=null). Does not invent V/I from watts.

  L:/Continue/.venv/Scripts/python.exe scripts/rid_electrical_observe.py --once
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
from lib.rid_electrical import FLAG_NAME, triad_availability  # noqa: E402

OUT_DIR = AUTO_ARTIFACTS / "rid_electrical"
LATEST = OUT_DIR / "observe_latest.json"


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _inventory_foundation_meters() -> dict[str, Any]:
    """Probe only existing foundation APIs + inventory wired_candidates. No fills."""
    meters: dict[str, Any] = {
        "w_cpu": None,
        "w_gpu": None,
        "v_cpu": None,
        "v_gpu": None,
        "i_cpu": None,
        "i_gpu": None,
        "sources": {},
        "errors": [],
    }

    # Prefer last meter inventory wired_candidates (discovery proved numeric sample)
    inv_path = OUT_DIR / "meter_inventory_latest.json"
    if inv_path.is_file():
        try:
            inv = json.loads(inv_path.read_text(encoding="utf-8"))
            wired = inv.get("wired_candidates") or {}
            for key in ("w_cpu", "w_gpu", "v_cpu", "v_gpu", "i_cpu", "i_gpu"):
                row = wired.get(key)
                if isinstance(row, dict) and row.get("admitted_to_observe") and row.get("sample") is not None:
                    meters[key] = float(row["sample"])
                    meters["sources"][key] = str(row.get("source") or "meter_inventory")
            meters["sources"]["inventory"] = str(inv_path).replace("\\", "/")
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            meters["errors"].append(f"inventory_load:{exc}")

    # Always refresh live GPU watts when NVML works (fresher than inventory snapshot)
    try:
        from lib.gpu_plant import read_gpu

        g = read_gpu(0)
        meters["w_gpu"] = float(g.power_w)
        meters["sources"]["w_gpu"] = "lib.gpu_plant.read_gpu.power_w"
    except Exception as exc:  # noqa: BLE001 — inventory must fail closed
        meters["errors"].append(f"gpu_power:{exc}")
        if meters["sources"].get("w_gpu") is None:
            meters["sources"]["w_gpu"] = None

    # Refresh HWiNFO CSV channels live (incl. software Ohm i_gpu when stamped)
    meters["origins"] = {}
    meters["independent_axes"] = {}
    try:
        from lib.hwinfo_telemetry import I_GPU_ORIGIN_OHM, read_electrical
        from lib.rid_electrical import reject_derived_live_axes

        hw = read_electrical()
        if hw.get("ok"):
            meters["sources"]["hwinfo_csv"] = hw.get("path")
            for key in ("w_cpu", "v_cpu", "i_cpu", "v_gpu", "i_gpu"):
                sample = hw.get(key)
                src = (hw.get("sources") or {}).get(key)
                if sample is not None and src:
                    meters[key] = float(sample)
                    meters["sources"][key] = str(src)
                    meters["origins"][key] = (hw.get("origins") or {}).get(key)
                    meters["independent_axes"][key] = bool(
                        (hw.get("independent_axes") or {}).get(key, True)
                    )
            if hw.get("i_gpu_rails"):
                meters["sources"]["i_gpu_rails"] = hw["i_gpu_rails"]
            # Honesty stamp: Ohm-reconstructed i_gpu is not an independent axis
            if meters.get("i_gpu") is not None and meters["origins"].get("i_gpu") == I_GPU_ORIGIN_OHM:
                guard = reject_derived_live_axes(
                    w=hw.get("w_gpu"),
                    v=None,  # multi-rail; independence denied by origin stamp
                    i=meters["i_gpu"],
                    i_was_derived_from_w_over_v=True,
                )
                meters["sources"]["i_gpu_independence"] = guard
            # w_gpu: NVML wins; HWiNFO is cross-check only when NVML already set
            if meters.get("w_gpu") is None and hw.get("w_gpu") is not None:
                meters["w_gpu"] = float(hw["w_gpu"])
                meters["sources"]["w_gpu"] = str((hw.get("sources") or {}).get("w_gpu"))
            elif hw.get("w_gpu") is not None:
                meters["sources"]["w_gpu_hwinfo_crosscheck"] = {
                    "source": (hw.get("sources") or {}).get("w_gpu"),
                    "sample": float(hw["w_gpu"]),
                }
        else:
            meters["errors"].append(f"hwinfo:{hw.get('error')}")
    except Exception as exc:  # noqa: BLE001
        meters["errors"].append(f"hwinfo:{exc}")

    # Channels still None remain unwired — never invent assumed 12 V.
    for key in ("w_cpu", "v_cpu", "v_gpu", "i_cpu", "i_gpu"):
        meters["sources"].setdefault(key, None)
    meters["sources"]["note"] = (
        "Observe admits live NVML GPU power and HWiNFO preferred columns. "
        "i_gpu may be software Ohm sum of measured PCIe+8-pin P/V (stamped, "
        "not independent). Assumed 12 V forbidden."
    )
    return meters


def _read_master_readonly() -> dict[str, Any]:
    """Juxtaposition only — never write Master or supervisor."""
    from lib.master_rid import MASTER_RID_PATH, load_master_rid

    before_text: str | None = None
    if MASTER_RID_PATH.is_file():
        try:
            before_text = MASTER_RID_PATH.read_text(encoding="utf-8")
        except OSError:
            before_text = None

    master = load_master_rid()
    if master is not None:
        master_dict: dict[str, Any] = {
            "master_s_n": master.master_s_n,
            "status": master.status,
            "n_subsystems": master.n_subsystems,
            "timestamp": master.timestamp,
            "subsystems": sorted(master.subsystems.keys()),
            "source": "load_master_rid_readonly",
        }
    else:
        master_dict = {
            "master_s_n": None,
            "status": None,
            "subsystems": [],
            "source": "unavailable",
            "note": "No master_rid snapshot; observe does not publish one.",
        }

    after_text: str | None = None
    if MASTER_RID_PATH.is_file():
        try:
            after_text = MASTER_RID_PATH.read_text(encoding="utf-8")
        except OSError:
            after_text = None

    return {
        "master": master_dict,
        "master_rid_path": str(MASTER_RID_PATH).replace("\\", "/"),
        "disk_unchanged": before_text == after_text,
        "authority": "observe_only_no_write",
    }


def observe_once() -> dict[str, Any]:
    meters = _inventory_foundation_meters()
    triad = triad_availability(
        w_cpu=meters["w_cpu"],
        w_gpu=meters["w_gpu"],
        v_cpu=meters["v_cpu"],
        v_gpu=meters["v_gpu"],
        i_cpu=meters["i_cpu"],
        i_gpu=meters["i_gpu"],
    )
    master_view = _read_master_readonly()
    # Diagnostic rail summary (not predictive)
    from lib.rid_electrical_policy import DIAGNOSTIC_ALLOWED, LIFECYCLE, RAIL_ROLE, policy_stamp

    diagnostics = {
        "board_power_w": {"cpu": meters["w_cpu"], "gpu": meters["w_gpu"]},
        "voltages_v": {"cpu": meters["v_cpu"], "gpu": meters["v_gpu"]},
        "currents_a": {
            "cpu": meters["i_cpu"],
            "gpu": meters["i_gpu"],
            "gpu_derived_ohm": (meters.get("origins") or {}).get("i_gpu")
            == "software_ohm_from_measured_hwinfo_rails",
        },
        "missing_channels": [
            k
            for k in ("w_cpu", "w_gpu", "v_cpu", "v_gpu", "i_cpu", "i_gpu")
            if meters.get(k) is None
        ],
        "allowed_diagnostic_uses": list(DIAGNOSTIC_ALLOWED),
        "predictive_claim": False,
    }
    payload = {
        "ok": True,
        "at": _utc(),
        "flag": FLAG_NAME,
        "authority": "observe_only_diagnostics",
        "lifecycle": LIFECYCLE,
        "rail_role": RAIL_ROLE,
        "predictor_operational": False,
        "electrical_in_A_t": False,
        "admission_granted": False,
        "experiment": "rid_electrical_observe_v1",
        "maps_to_rsr_ltp_rle": False,
        "meters": {
            "w_cpu": meters["w_cpu"],
            "w_gpu": meters["w_gpu"],
            "v_cpu": meters["v_cpu"],
            "v_gpu": meters["v_gpu"],
            "i_cpu": meters["i_cpu"],
            "i_gpu": meters["i_gpu"],
            "sources": meters["sources"],
            "origins": meters.get("origins") or {},
            "independent_axes": meters.get("independent_axes") or {},
            "errors": meters["errors"],
        },
        "electrical": triad,
        "diagnostics": diagnostics,
        "master_readonly": master_view,
        "master_authority_changed": False,
        "policy": policy_stamp(),
        "note": (
            "Observe-only diagnostics. Not a prediction feature. "
            "i_gpu may be Ohm-derived (non-independent). "
            "Lifecycle rejected_operational_use for Master/prediction/routing."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _utc().replace(":", "").replace("+", "p")
    stamped = OUT_DIR / f"observe_{stamp}.json"
    text = json.dumps(payload, indent=2)
    stamped.write_text(text, encoding="utf-8")
    LATEST.write_text(text, encoding="utf-8")
    payload["artifact"] = str(stamped).replace("\\", "/")
    payload["latest"] = str(LATEST).replace("\\", "/")
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", default=True, help="Single observe (default)")
    args = p.parse_args()
    # Refuse authority mutation paths — none implemented.
    _ = args
    out = observe_once()
    print(json.dumps(out, indent=2), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
